"""Checks on the generated database. Independent of tools.py: raw SQL against planted.py's ground truth."""
import sqlite3

import pytest

import generate_data
import planted
from db import AS_OF, connect

STAGES = ["applied", "recruiter_screen", "hiring_manager", "technical", "onsite", "offer"]


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "recruiting.db"
    generate_data.build(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def q(conn, sql, *args):
    return [tuple(r) for r in conn.execute(sql, args)]


def test_counts(conn):
    assert q(conn, "SELECT COUNT(*) FROM roles") == [(3,)]
    assert q(conn, "SELECT COUNT(*) FROM applications") == [(50,)]
    assert q(conn, "SELECT role_id, COUNT(*) FROM applications GROUP BY 1 ORDER BY 1") == [
        ("R1", 20), ("R2", 16), ("R3", 14)]


def test_deterministic(tmp_path):
    dumps = []
    for name in ("a.db", "b.db"):
        generate_data.build(tmp_path / name)
        dumps.append("\n".join(sqlite3.connect(tmp_path / name).iterdump()))
    assert dumps[0] == dumps[1]


def test_current_stage_and_status_match_event_log(conn):
    for app in conn.execute("SELECT id, current_stage, status FROM applications"):
        events = q(conn, "SELECT to_stage FROM stage_events WHERE application_id=? ORDER BY at, id", app["id"])
        stages = [e[0] for e in events]
        if stages[-1] in ("rejected", "withdrew"):
            expected = (stages[-2], stages[-1])
        else:
            expected = (stages[-1], "hired" if stages[-1] == "hired" else "active")
        assert (app["current_stage"], app["status"]) == expected, app["id"]


def test_event_ids_follow_time_order_within_each_application(conn):
    for (app_id,) in q(conn, "SELECT id FROM applications"):
        ats = [r[0] for r in q(conn, "SELECT at FROM stage_events WHERE application_id=? ORDER BY id", app_id)]
        assert ats == sorted(ats), app_id


def test_nothing_after_as_of(conn):
    for table, column in [("stage_events", "at"), ("feedback", "scheduled_at"), ("feedback", "submitted_at"),
                          ("emails", "sent_at"), ("applications", "applied_at")]:
        late = q(conn, f"SELECT id FROM {table} WHERE {column} > ?", AS_OF)
        assert late == [], (table, column, late)


def test_no_demographic_columns(conn):
    banned = {"age", "gender", "sex", "race", "ethnicity", "nationality", "religion", "disability",
              "birth", "dob", "marital", "graduation"}
    for (table,) in q(conn, "SELECT name FROM sqlite_master WHERE type='table'"):
        for col in conn.execute(f"PRAGMA table_info({table})"):
            assert not banned & set(col["name"].lower().split("_")), (table, col["name"])


def test_planted_average_ratings(conn):
    for app_id, expected in planted.EXPECTED_AVG_RATING.items():
        (avg,), = q(conn, "SELECT AVG(rating) FROM feedback WHERE application_id=?", app_id)
        assert round(avg, 2) == expected, app_id


def test_fillers_never_rate_4_or_beat_the_planted_top3(conn):
    assert q(conn, "SELECT id FROM feedback WHERE rating=4 AND id > 'FB-100'") == []
    rows = q(conn, """SELECT application_id, AVG(rating) FROM feedback
                      WHERE application_id > 'APP-100' GROUP BY 1 HAVING AVG(rating) > 3.0""")
    assert rows == []


def test_fillers_create_no_tasks(conn):
    # Only the planted records owe anything at AS_OF.
    owed = {r[0] for r in q(conn, "SELECT id FROM feedback WHERE submitted_at IS NULL")}
    assert owed == {"FB-029", "FB-030", "FB-055"}
    last_inbound = q(conn, """
        SELECT e.thread_id FROM emails e
        WHERE e.sent_at = (SELECT MAX(sent_at) FROM emails WHERE thread_id = e.thread_id)
          AND e.direction = 'in' ORDER BY 1""")
    planted_inbound = sorted(
        em[1] for c in planted.PLANTED for em in c["emails"] if em[0] in ("EM-018", "EM-022"))
    assert [r[0] for r in last_inbound] == planted_inbound
    at_offer = q(conn, "SELECT id FROM applications WHERE current_stage='offer' AND status='active'")
    assert at_offer == [("APP-006",)]


def test_r1_funnel_matches_planted_ground_truth(conn):
    """Raw-SQL funnel: reached / left / advanced / exited per stage for R1."""
    got = {}
    for stage in STAGES:
        reached = q(conn, """SELECT COUNT(DISTINCT e.application_id) FROM stage_events e
                             JOIN applications a ON a.id = e.application_id
                             WHERE a.role_id='R1' AND e.to_stage=?""", stage)[0][0]
        left = q(conn, """SELECT COUNT(DISTINCT e.application_id) FROM stage_events e
                          JOIN applications a ON a.id = e.application_id
                          WHERE a.role_id='R1' AND e.from_stage=?""", stage)[0][0]
        exited = q(conn, """SELECT COUNT(DISTINCT e.application_id) FROM stage_events e
                            JOIN applications a ON a.id = e.application_id
                            WHERE a.role_id='R1' AND e.from_stage=?
                              AND e.to_stage IN ('rejected','withdrew')""", stage)[0][0]
        got[stage] = (reached, left, left - exited, exited)
    assert got == planted.EXPECTED_FUNNEL_R1


def test_candidate_emails_are_example_com(conn):
    assert q(conn, "SELECT id FROM candidates WHERE email NOT LIKE '%@example.com'") == []


def test_connect_is_read_only(tmp_path, monkeypatch):
    path = tmp_path / "ro.db"
    generate_data.build(path)
    monkeypatch.setenv("RECRUITING_DB", str(path))
    ro = connect()
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM roles")
