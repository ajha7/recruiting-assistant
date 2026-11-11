"""Build data/recruiting.db: 12 hand-written planted candidates (planted.py) plus 38 seeded fillers.

This script stands in for the production ingest job (ATS webhooks + backfill), so it writes with
sqlite3 directly. The read path (db.py) never writes. Output is deterministic: fixed seed, fixed
insert order.

Filler rules that keep the ground truth in planted.py exact:
  - fillers never create a task: all feedback is submitted within a day of the interview, every
    email thread ends with an outbound message, and no filler sits at the offer stage
  - no filler rating is 4 (so the planted top-3 are unambiguous)
  - R1 fillers dwell 9-16 days at onsite and their onsite notes cite system design
"""
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import planted
from db import AS_OF, DEFAULT_DB

SEED = 42
STAGES = ["applied", "recruiter_screen", "hiring_manager", "technical", "onsite"]
INTERVIEW_STAGES = STAGES[1:]
SCHEMA = Path(__file__).parent / "schema.sql"

# (final stage, status, reason_code) for each filler. Counts per role are from PLAN.md section 5.
def _spec(rows):
    out = []
    for stage, status, reason, n in rows:
        out += [(stage, status, reason)] * n
    return out


FILLER_SPECS = {
    "R1": _spec([
        ("applied", "active", None, 2), ("recruiter_screen", "active", None, 1),
        ("applied", "rejected", "rejected_skills", 3),
        ("recruiter_screen", "rejected", "rejected_skills", 2),
        ("recruiter_screen", "withdrew", "withdrew_other_offer", 1),
        ("hiring_manager", "rejected", "rejected_skills", 2),
        ("technical", "rejected", "rejected_skills", 2),
        ("onsite", "rejected", "rejected_skills", 2),
    ]),
    "R2": _spec([
        ("applied", "active", None, 1), ("hiring_manager", "active", None, 1),
        ("technical", "active", None, 1),
        ("applied", "rejected", "rejected_skills", 2),
        ("recruiter_screen", "rejected", "rejected_skills", 1),
        ("recruiter_screen", "withdrew", "no_response", 1),
        ("hiring_manager", "rejected", "rejected_skills", 1),
        ("technical", "rejected", "rejected_skills", 2),
        ("onsite", "rejected", "rejected_skills", 1),
    ]),
    "R3": _spec([
        ("applied", "active", None, 4), ("recruiter_screen", "active", None, 4),
        ("hiring_manager", "active", None, 2),
        ("applied", "rejected", "rejected_skills", 1),
        ("recruiter_screen", "rejected", "rejected_skills", 1),
    ]),
}

FIRST = ["Aiden", "Beatriz", "Callum", "Dalia", "Emeka", "Farah", "Gideon", "Hye-jin", "Ivo", "Jasmine",
         "Kenji", "Leila", "Mateus", "Nadia", "Oskar", "Parisa", "Quinn", "Rohan", "Saoirse", "Tariq",
         "Uma", "Vikram", "Willa", "Xavier", "Yara", "Zane", "Alma", "Bruno", "Cleo", "Dmitri",
         "Elsa", "Felix", "Greta", "Hugo", "Ines", "Jonas", "Kira", "Luca", "Maren", "Nico"]
LAST = ["Abara", "Brennan", "Castillo", "Dvorak", "Eriksen", "Fontaine", "Grover", "Haddad", "Ivanov", "Jansen",
        "Kowalski", "Lindgren", "Moreau", "Nakamura", "Oyelaran", "Pereira", "Quist", "Rahman", "Sorensen", "Tanaka",
        "Ueda", "Voss", "Whitlock", "Xu", "Yilmaz", "Zielinski", "Amato", "Bianchi", "Carvalho", "Delgado",
        "Engel", "Farouk", "Gallo", "Hartmann", "Iyer", "Jovanovic", "Kessler", "Laurent", "Mbeki", "Novak"]
SOURCES = ["referral", "linkedin", "job_board", "careers_page", "agency"]

CV_SKILLS = {
    "R1": ["Python", "Go", "Java", "PostgreSQL", "Redis", "RabbitMQ", "Kafka", "Docker", "AWS"],
    "R2": ["Python", "PyTorch", "scikit-learn", "SQL", "Airflow", "MLflow", "Spark", "pandas"],
    "R3": ["Figma", "prototyping", "user research", "design systems", "accessibility", "Sketch"],
}
CV_TITLES = {"R1": "Backend Engineer", "R2": "Data Scientist", "R3": "Product Designer"}

INTERVIEWERS = {
    "recruiter_screen": [planted.RECRUITER],
    "hiring_manager": None,  # filled with the role's hiring manager
    "technical": ["Julia Brandt", "Sam Whitfield", "Priti Rao"],
    "onsite": ["Julia Brandt", "Sam Whitfield", "Priti Rao", "Chen Wei"],
}

# Neutral notes, keyed by rating. R1 onsite rejections use SYSTEM_DESIGN_NOTES instead.
NOTES = {
    3: ["Solid fundamentals and clear communication. Some gaps on follow-up questions.",
        "Good answers overall, would be fine on the team. Not standout."],
    2: ["Struggled with the main exercise and needed several hints.",
        "Answers were shallow and did not show hands-on depth."],
    1: ["Could not complete the exercise. Concerns about core skills."],
}
SYSTEM_DESIGN_NOTES = [
    "System design: good on code but the design did not scale past a single node.",
    "System design: weak on partitioning and failure modes. Coding was fine.",
]


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def make_names(rng):
    firsts, lasts = FIRST[:], LAST[:]
    rng.shuffle(firsts)
    rng.shuffle(lasts)
    return list(zip(firsts, lasts))


def make_filler(rng, n, role, spec, name, hm_name):
    """Return one filler as a dict shaped like a planted.PLANTED entry (plus role_id, no emails ids)."""
    final_stage, status, reason = spec
    first, last = name
    full = f"{first} {last}"
    # Stage dwell times in days. R1 onsite is the slow stage (9-16 days).
    n_stages = STAGES.index(final_stage) + 1
    dwell = []
    for stage in STAGES[:n_stages]:
        dwell.append(rng.randint(9, 16) if role["id"] == "R1" and stage == "onsite" else rng.randint(2, 6))
    # Active fillers stay in their last stage; exited fillers leave it after its dwell time.
    span = sum(dwell[:-1]) + (dwell[-1] if status != "active" else 0)
    earliest = datetime.fromisoformat(role["opened_at"]) + timedelta(days=1)
    latest = datetime.fromisoformat(AS_OF) - timedelta(days=4 + span)
    assert latest >= earliest, f"filler {n} on {role['id']} does not fit before AS_OF"
    applied = earliest + timedelta(minutes=rng.randint(0, int((latest - earliest).total_seconds() // 60)))
    applied = applied.replace(second=0)

    events, t = [("applied", iso(applied), "system", None)], applied
    for i in range(1, n_stages):
        t = t + timedelta(days=dwell[i - 1])
        events.append((STAGES[i], iso(t), planted.RECRUITER, None))
    entry_times = {STAGES[i]: events[i][1] for i in range(n_stages)}
    if status != "active":
        t = t + timedelta(days=dwell[-1])
        actor = full if status == "withdrew" else hm_name
        events.append((status, iso(t), actor, reason))

    # Feedback: one row per completed (or rejected-at) interview stage. Withdrawals get none.
    feedback = []
    for stage in INTERVIEW_STAGES:
        if stage not in entry_times or (stage == final_stage and status in ("active", "withdrew")):
            continue
        rejected_here = stage == final_stage  # only possible when status == "rejected"
        for k in range(2 if stage == "onsite" else 1):
            interviewer = hm_name if stage == "hiring_manager" else rng.choice(INTERVIEWERS[stage])
            day = 5 if stage == "onsite" and role["id"] == "R1" else 1
            sched = datetime.fromisoformat(entry_times[stage]) + timedelta(days=day, hours=rng.randint(2, 7))
            sub = sched + timedelta(hours=rng.randint(2, 20))
            rating = rng.choice([1, 2]) if rejected_here else 3
            if rejected_here and role["id"] == "R1" and stage == "onsite":
                note = SYSTEM_DESIGN_NOTES[k]
            else:
                note = rng.choice(NOTES[rating])
            rec = "no_hire" if rating <= 2 else "hire"
            feedback.append((stage, interviewer, iso(sched), rating, rec, note, iso(sub)))

    # One scheduling thread: out, in, out. Always ends outbound.
    t0 = applied + timedelta(days=1, hours=rng.randint(0, 4))
    t1 = t0 + timedelta(hours=rng.randint(4, 20))
    t2 = t1 + timedelta(hours=rng.randint(2, 20))
    subject = f"Scheduling: {role['title']} interview"
    emails = [
        ("out", iso(t0), subject, f"Hi {first}, thanks for applying. Do you have time this week for a call?"),
        ("in", iso(t1), subject, "Thanks for reaching out. Thursday afternoon works for me."),
        ("out", iso(t2), subject, "Great, I have sent a calendar invite for Thursday."),
    ]
    skills = ", ".join(rng.sample(CV_SKILLS[role["id"]], 4))
    cv = (f"{full} - {CV_TITLES[role['id']]}\n"
          f"{rng.randint(2, 9)} years of experience in the field. Recent work on internal tools "
          f"and customer-facing features.\nSkills: {skills}.")
    return dict(
        candidate_id=f"C-{101 + n}", app_id=f"APP-{101 + n}", name=full,
        email=f"{first.lower()}.{last.lower()}@example.com", source=rng.choice(SOURCES),
        role_id=role["id"], cv_text=cv, events=events, feedback=feedback, emails=emails,
    )


def derive_state(events):
    """current_stage and status from the event log (last event wins; exits keep the prior stage)."""
    last = events[-1][0]
    if last in ("rejected", "withdrew"):
        return events[-2][0], last
    return last, "hired" if last == "hired" else "active"


def build(db_path):
    """Create a fresh database at db_path."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)

    rng = random.Random(SEED)
    roles = {r["id"]: r for r in planted.ROLES}
    names = iter(make_names(rng))
    candidates = [(c, True) for c in planted.PLANTED]
    n = 0
    for role_id, specs in FILLER_SPECS.items():
        for spec in specs:
            candidates.append((make_filler(rng, n, roles[role_id], spec, next(names),
                                           roles[role_id]["hiring_manager"]), False))
            n += 1

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA.read_text())
    for r in planted.ROLES:
        conn.execute("INSERT INTO roles VALUES (?,?,?,?,?,?,?)",
                     (r["id"], r["title"], r["team"], r["hiring_manager"], r["opened_at"],
                      r["status"], r["requirements"]))
    ev_n, fb_n, em_n, th_n = 0, 100, 100, 100  # filler feedback/email/thread ids start at 101
    for c, is_planted in candidates:
        stage, status = derive_state(c["events"])
        conn.execute("INSERT INTO candidates VALUES (?,?,?,?,?)",
                     (c["candidate_id"], c["name"], c["email"], c["cv_text"], c["source"]))
        conn.execute("INSERT INTO applications VALUES (?,?,?,?,?,?)",
                     (c["app_id"], c["candidate_id"], c["role_id"], c["events"][0][1], stage, status))
        prev = None
        for to_stage, at, actor, reason in c["events"]:
            ev_n += 1
            conn.execute("INSERT INTO stage_events VALUES (?,?,?,?,?,?,?)",
                         (f"EV-{ev_n:04d}", c["app_id"], prev, to_stage, at, actor, reason))
            prev = to_stage
        for fb in c["feedback"]:
            if is_planted:
                fb_id, stage_, who, sched, rating, rec, notes, sub = fb
            else:
                fb_n += 1
                (stage_, who, sched, rating, rec, notes, sub), fb_id = fb, f"FB-{fb_n}"
            conn.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?,?,?,?)",
                         (fb_id, c["app_id"], stage_, who, sched, rating, rec, notes, sub))
        if not is_planted:
            th_n += 1
        for em in c["emails"]:
            if is_planted:
                em_id, thread, direction, sent, subject, body = em
            else:
                em_n += 1
                (direction, sent, subject, body), em_id, thread = em, f"EM-{em_n}", f"TH-{th_n}"
            mine, theirs = planted.RECRUITER_EMAIL, c["email"]
            sender, recipient = (mine, theirs) if direction == "out" else (theirs, mine)
            conn.execute("INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?)",
                         (em_id, thread, c["app_id"], direction, sender, recipient, sent, subject, body))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    build(out)
    conn = sqlite3.connect(out)
    counts = conn.execute("SELECT role_id, COUNT(*) FROM applications GROUP BY 1").fetchall()
    print(f"wrote {out}: {dict(counts)}")
