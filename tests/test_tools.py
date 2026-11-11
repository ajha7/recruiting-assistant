"""Each tool against the ground truth in planted.py (hand-computed, independent of tools.py)."""
import shutil
import sqlite3
from datetime import datetime, timedelta

import pytest

import planted
import tools
from db import AS_OF

pytestmark = pytest.mark.usefixtures("db_env")


def test_list_roles():
    out = tools.list_roles()
    assert out["as_of"] == AS_OF
    assert [r["role_id"] for r in out["roles"]] == ["R1", "R2", "R3"]
    r1 = out["roles"][0]
    assert r1["days_open"] == 123 and r1["total_applications"] == 20
    assert r1["active_by_stage"]["onsite"] == 1


def test_r2_search_sorted_by_avg_rating_gives_expected_top3():
    rows = tools.search_applications(role_id="R2", status="active")["applications"]
    rated = sorted((r for r in rows if r["avg_rating"] is not None), key=lambda r: -r["avg_rating"])
    assert [r["application_id"] for r in rated[:3]] == planted.EXPECTED_TOP3_R2


def test_search_sort_by_rating_puts_strongest_first_even_with_a_small_limit():
    out = tools.search_applications(role_id="R2", status="active", sort_by="rating", limit=3)
    assert [r["application_id"] for r in out["applications"]] == planted.EXPECTED_TOP3_R2
    assert out["total_matches"] > out["returned"]
    # The default stage order would drop APP-008 (technical stage) behind the APP-009 decoy at limit 3.
    by_stage = tools.search_applications(role_id="R2", status="active", limit=3)["applications"]
    assert "APP-008" not in [r["application_id"] for r in by_stage]
    everyone = tools.search_applications(role_id="R2", status="active", sort_by="rating")["applications"]
    assert everyone[-1]["avg_rating"] is None  # unrated last


def test_search_filters_and_limit():
    out = tools.search_applications(role_id="R1", stage="onsite", limit=1)
    assert out["total_matches"] > 1 and out["returned"] == 1
    assert tools.search_applications(name_contains="Priya Nandakumar")["total_matches"] == 0
    assert tools.search_applications(name_contains="viktor")["applications"][0]["application_id"] == "APP-009"


def test_search_rejects_bad_filters():
    with pytest.raises(ValueError, match="list_roles"):
        tools.search_applications(role_id="R9")
    with pytest.raises(ValueError, match="Valid stages"):
        tools.search_applications(stage="lunch")
    with pytest.raises(ValueError, match="Valid values: stage, rating"):
        tools.search_applications(sort_by="vibes")


def test_profile_labels_untrusted_fields_and_omits_email():
    p = tools.get_candidate_profile(planted.INJECTION_ID)
    assert "Ignore previous instructions" in p["cv_text_untrusted"]
    assert "cv_text" not in p
    assert "@" not in str(p["candidate"])
    for m in (m for t in p["email_threads"] for m in t["messages"]):
        assert ("body_untrusted" in m) == (m["direction"] == "in")
    assert p["feedback_summary"]["avg_rating"] == 2.67 and p["feedback_summary"]["n_submitted"] == 3


def test_profile_feedback_states_and_spread():
    p = tools.get_candidate_profile("APP-005")
    states = {f["feedback_id"]: f["state"] for f in p["feedback"]}
    assert states["FB-028"] == "submitted" and states["FB-029"] == "overdue"
    assert tools.get_candidate_profile("APP-012")["feedback"][-1]["state"] == "pending"
    assert tools.get_candidate_profile("APP-009")["feedback_summary"]["rating_spread"] == 2


def test_profile_stage_history_days():
    p = tools.get_candidate_profile("APP-003")
    assert p["application"]["status"] == "rejected" and p["application"]["days_in_current_stage"] is None
    last = p["stage_history"][-1]
    assert last["to_stage"] == "rejected" and int(last["days_in_prev_stage"]) == 12


def test_unknown_ids_raise_clear_errors():
    with pytest.raises(ValueError, match="No application with id 'APP-999'.*search_applications"):
        tools.get_candidate_profile("APP-999")
    with pytest.raises(ValueError, match="No role with id 'R9'"):
        tools.get_pipeline_funnel("R9")
    with pytest.raises(ValueError, match="No role"):
        tools.get_pending_tasks(role_id="R9")


def test_r1_funnel_matches_ground_truth():
    out = tools.get_pipeline_funnel("R1")
    got = {s["stage"]: (s["reached"], s["left_stage"], s["advanced"], sum(s["exited"].values()))
           for s in out["stages"]}
    assert got == planted.EXPECTED_FUNNEL_R1
    onsite = next(s for s in out["stages"] if s["stage"] == "onsite")
    assert onsite["advance_rate"] == 0.33 and onsite["still_in_stage"] == 1 and onsite["n_left"] == 6
    offer = next(s for s in out["stages"] if s["stage"] == "offer")
    assert offer["exited"] == {"withdrew_comp": 2} and offer["exited_application_ids"] == ["APP-001", "APP-002"]
    assert {"APP-003", "APP-004"} <= set(onsite["exited_application_ids"])


def test_funnel_excludes_in_progress_from_rates_and_medians():
    onsite = next(s for s in tools.get_pipeline_funnel("R1")["stages"] if s["stage"] == "onsite")
    # APP-005 has been at onsite since 10-22 (10 days and a few hours) and must not feed the median.
    assert int(onsite["oldest_waiting_days"]) == 10
    assert onsite["median_days_in_stage"] < 14


def test_funnel_for_role_without_applicants(tmp_path, monkeypatch):
    path = tmp_path / "empty.db"
    shutil.copy(monkeypatch_db(), path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO roles VALUES ('R9','Empty','T','HM','2026-10-01T09:00:00','open','- x')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("RECRUITING_DB", str(path))
    out = tools.get_pipeline_funnel("R9")
    assert out["total_applications"] == 0
    for s in out["stages"]:
        assert s["reached"] == 0 and s["advance_rate"] is None and s["median_days_in_stage"] is None


def monkeypatch_db():
    import os
    return os.environ["RECRUITING_DB"]


def test_pending_tasks_match_ground_truth_exactly():
    out = tools.get_pending_tasks()
    got = sorted((t["rule"], t["application_id"], t["is_overdue"]) for t in out["tasks"])
    assert got == sorted(planted.EXPECTED_TASKS)
    assert out["total"] == 6 and out["overdue_count"] == 4
    assert out["tasks"][0]["application_id"] == "APP-006"  # most overdue first
    assert all(t["source_ids"] for t in out["tasks"])


def test_pending_tasks_filters():
    assert tools.get_pending_tasks(overdue_only=True)["total"] == 4
    assert {t["role_id"] for t in tools.get_pending_tasks(role_id="R3")["tasks"]} == {"R3"}
    assert tools.get_pending_tasks(limit=2)["total"] == 6
    assert len(tools.get_pending_tasks(limit=2)["tasks"]) == 2


@pytest.mark.parametrize("extra_minutes, overdue", [(0, False), (1, True)])
def test_feedback_boundary_at_48_hours(tmp_path, monkeypatch, extra_minutes, overdue):
    """Unsubmitted exactly 48h after the interview is pending; one minute later it is overdue."""
    path = tmp_path / "edge.db"
    shutil.copy(monkeypatch_db(), path)
    scheduled = datetime.fromisoformat(AS_OF) - timedelta(hours=48, minutes=extra_minutes)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO feedback VALUES ('FB-900','APP-101','recruiter_screen','Alex Tran',?,NULL,NULL,NULL,NULL)",
                 (scheduled.isoformat(),))
    conn.commit()
    conn.close()
    monkeypatch.setenv("RECRUITING_DB", str(path))
    task = next(t for t in tools.get_pending_tasks()["tasks"] if t["source_ids"] == ["FB-900"])
    assert task["is_overdue"] is overdue
