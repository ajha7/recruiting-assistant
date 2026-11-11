PRAGMA foreign_keys = ON;

CREATE TABLE roles (
  id TEXT PRIMARY KEY,                       -- 'R1'
  title TEXT NOT NULL, team TEXT NOT NULL, hiring_manager TEXT NOT NULL,
  opened_at TEXT NOT NULL,                   -- ISO 8601 UTC, 'YYYY-MM-DDTHH:MM:SS'
  status TEXT NOT NULL CHECK (status IN ('open','closed')),
  requirements TEXT NOT NULL                 -- 4-5 short bullet lines
);

CREATE TABLE candidates (
  id TEXT PRIMARY KEY,                       -- 'C-001'
  name TEXT NOT NULL, email TEXT NOT NULL,   -- @example.com only
  cv_text TEXT NOT NULL, source TEXT NOT NULL
);

CREATE TABLE applications (                  -- candidate x role: the core unit
  id TEXT PRIMARY KEY,                       -- 'APP-001'
  candidate_id TEXT NOT NULL REFERENCES candidates(id),
  role_id TEXT NOT NULL REFERENCES roles(id),
  applied_at TEXT NOT NULL,
  current_stage TEXT NOT NULL CHECK (current_stage IN
    ('applied','recruiter_screen','hiring_manager','technical','onsite','offer','hired')),
  status TEXT NOT NULL CHECK (status IN ('active','rejected','withdrew','hired')),
  UNIQUE (candidate_id, role_id)
);

CREATE TABLE stage_events (                  -- append-only
  id TEXT PRIMARY KEY,                       -- 'EV-0001'
  application_id TEXT NOT NULL REFERENCES applications(id),
  from_stage TEXT,                           -- NULL only for the initial 'applied' event
  to_stage TEXT NOT NULL CHECK (to_stage IN
    ('applied','recruiter_screen','hiring_manager','technical','onsite','offer','hired',
     'rejected','withdrew')),                -- rejected/withdrew are exit pseudo-stages
  at TEXT NOT NULL, actor TEXT NOT NULL,
  reason_code TEXT CHECK (reason_code IN
    ('rejected_skills','withdrew_comp','withdrew_other_offer','no_response')),
  CHECK ((to_stage IN ('rejected','withdrew')) = (reason_code IS NOT NULL))
);

CREATE TABLE feedback (                      -- one row per interview
  id TEXT PRIMARY KEY,                       -- 'FB-001'
  application_id TEXT NOT NULL REFERENCES applications(id),
  stage TEXT NOT NULL, interviewer TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  rating INTEGER CHECK (rating BETWEEN 1 AND 4),
  recommendation TEXT CHECK (recommendation IN ('strong_hire','hire','no_hire','strong_no_hire')),
  notes TEXT,
  submitted_at TEXT,                         -- NULL = feedback owed
  CHECK ((submitted_at IS NULL) = (rating IS NULL))
);

CREATE TABLE emails (
  id TEXT PRIMARY KEY,                       -- 'EM-001'
  thread_id TEXT NOT NULL,                   -- 'TH-001'
  application_id TEXT NOT NULL REFERENCES applications(id),
  direction TEXT NOT NULL CHECK (direction IN ('in','out')),
  sender TEXT NOT NULL, recipient TEXT NOT NULL,
  sent_at TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL
);

CREATE INDEX ix_app_role   ON applications(role_id);
CREATE INDEX ix_ev_app     ON stage_events(application_id);
CREATE INDEX ix_fb_app     ON feedback(application_id);
CREATE INDEX ix_em_app     ON emails(application_id);
