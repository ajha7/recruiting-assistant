"""Read-path access to the recruiting database. The only read-path module that touches sqlite3.

In production this is the file you swap: a read-only repository over Postgres or the ATS API,
scoped to the calling user's tenant. Writes happen elsewhere (generate_data.py stands in for
the ingest job), so nothing here can modify data.
"""
import os
import sqlite3
from pathlib import Path

# "Today" for the whole system: the moment the data was last synced.
AS_OF = "2026-11-01T12:00:00"

DEFAULT_DB = Path(__file__).parent / "data" / "recruiting.db"


def db_path() -> Path:
    return Path(os.environ.get("RECRUITING_DB", DEFAULT_DB))


def connect() -> sqlite3.Connection:
    """Open the database read-only. Rows come back as sqlite3.Row (dict-like)."""
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `make data` first.")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------- queries
# Plain SQL, one function per question the tools ask. Every function returns dicts.

def _rows(sql, args=()):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def get_roles():
    return _rows("SELECT * FROM roles ORDER BY id")


def get_role(role_id):
    rows = _rows("SELECT * FROM roles WHERE id = ?", (role_id,))
    return rows[0] if rows else None


def count_applications_by_stage(role_id=None):
    """Active applications per (role, stage), plus all applications per role (stage None)."""
    return _rows("""SELECT role_id, CASE WHEN status = 'active' THEN current_stage END AS stage, COUNT(*) AS n
                    FROM applications WHERE (? IS NULL OR role_id = ?) GROUP BY 1, 2""", (role_id, role_id))


_SEARCH_WHERE = """FROM applications a JOIN candidates c ON c.id = a.candidate_id
  WHERE (:role_id IS NULL OR a.role_id = :role_id) AND (:stage IS NULL OR a.current_stage = :stage)
    AND (:status IS NULL OR a.status = :status) AND (:name IS NULL OR c.name LIKE '%' || :name || '%')"""


def search_application_rows(role_id, stage, status, name_contains, limit):
    """Returns (total_matches, rows). Furthest stage first, then id. This ordering is NOT a ranking."""
    p = dict(role_id=role_id, stage=stage, status=status, name=name_contains, as_of=AS_OF, limit=limit)
    total = _rows("SELECT COUNT(*) AS n " + _SEARCH_WHERE, p)[0]["n"]
    rows = _rows(f"""
        SELECT a.id AS application_id, c.name AS candidate_name, a.role_id, a.current_stage AS stage,
               a.status, a.applied_at,
               (SELECT ROUND(AVG(rating), 2) FROM feedback f WHERE f.application_id = a.id) AS avg_rating,
               (SELECT COUNT(rating) FROM feedback f WHERE f.application_id = a.id) AS n_ratings,
               (SELECT COUNT(*) FROM feedback f WHERE f.application_id = a.id
                  AND f.submitted_at IS NULL AND f.scheduled_at <= :as_of) AS n_feedback_owed,
               MAX((SELECT MAX(at) FROM stage_events e WHERE e.application_id = a.id),
                   COALESCE((SELECT MAX(sent_at) FROM emails m WHERE m.application_id = a.id), '')
               ) AS last_activity_at
        {_SEARCH_WHERE}
        ORDER BY CASE a.current_stage WHEN 'hired' THEN 6 WHEN 'offer' THEN 5 WHEN 'onsite' THEN 4
                 WHEN 'technical' THEN 3 WHEN 'hiring_manager' THEN 2 WHEN 'recruiter_screen' THEN 1
                 ELSE 0 END DESC, a.id
        LIMIT :limit""", p)
    return total, rows


def get_application(application_id):
    rows = _rows("""SELECT a.id AS application_id, a.role_id, r.title AS role_title, a.current_stage AS stage,
                           a.status, a.applied_at, c.id AS candidate_id, c.name, c.source, c.cv_text
                    FROM applications a JOIN candidates c ON c.id = a.candidate_id
                    JOIN roles r ON r.id = a.role_id WHERE a.id = ?""", (application_id,))
    return rows[0] if rows else None


def get_events(application_id):
    return _rows("SELECT * FROM stage_events WHERE application_id = ? ORDER BY at, id", (application_id,))


def get_events_for_role(role_id):
    return _rows("""SELECT e.* FROM stage_events e JOIN applications a ON a.id = e.application_id
                    WHERE a.role_id = ? ORDER BY e.application_id, e.at, e.id""", (role_id,))


def get_feedback(application_id):
    return _rows("SELECT * FROM feedback WHERE application_id = ? ORDER BY scheduled_at, id", (application_id,))


def get_unsubmitted_feedback(role_id=None):
    """Feedback owed by interviews that already happened, on active applications."""
    return _rows("""SELECT f.*, a.role_id, c.name AS candidate_name
                    FROM feedback f JOIN applications a ON a.id = f.application_id
                    JOIN candidates c ON c.id = a.candidate_id
                    WHERE f.submitted_at IS NULL AND f.scheduled_at <= ? AND a.status = 'active'
                      AND (? IS NULL OR a.role_id = ?)""", (AS_OF, role_id, role_id))


def get_emails(application_id):
    return _rows("SELECT * FROM emails WHERE application_id = ? ORDER BY sent_at, id", (application_id,))


def get_latest_email_per_thread(role_id=None):
    """The newest email in each thread, for active applications."""
    return _rows("""SELECT m.*, a.role_id, c.name AS candidate_name
                    FROM emails m JOIN applications a ON a.id = m.application_id
                    JOIN candidates c ON c.id = a.candidate_id
                    WHERE a.status = 'active' AND (? IS NULL OR a.role_id = ?)
                      AND m.sent_at = (SELECT MAX(sent_at) FROM emails WHERE thread_id = m.thread_id)""",
                 (role_id, role_id))


def get_offer_entries(role_id=None):
    """When each active application at the offer stage entered it."""
    return _rows("""SELECT a.id AS application_id, a.role_id, c.name AS candidate_name,
                           e.id AS event_id, e.at AS entered_at
                    FROM applications a JOIN candidates c ON c.id = a.candidate_id
                    JOIN stage_events e ON e.application_id = a.id AND e.to_stage = 'offer'
                    WHERE a.current_stage = 'offer' AND a.status = 'active'
                      AND (? IS NULL OR a.role_id = ?)""", (role_id, role_id))
