# Recruiting Assistant

A chat assistant for a hiring team. It answers questions about open roles and applicants (top candidates,
where a pipeline leaks, what follow-ups are overdue) using five read-only tools exposed over MCP, and
shows every tool call behind each answer. Everything is fictional: the company (Northwind Freight), the
people and all `@example.com` addresses.

![The app answering "Who are the top 3 candidates for this role, and why?" for the ML Engineer role](docs/app-answer.png)

**No API key? See [`docs/sample-runs.md`](docs/sample-runs.md)** for recorded answers to the three brief questions
and a follow-up, with every tool call, token counts and timings.

## Setup (5 commands)

```bash
git clone https://github.com/ajha7/recruiting-assistant.git && cd recruiting-assistant
cp .env.example .env          # add OPENAI_API_KEY and OPENAI_MODEL (see Eval results)
make setup && make data       # uv sync; build data/recruiting.db (deterministic)
make test                     # 48 tests, no API key needed
make app                      # Streamlit UI;  also: make eval RUNS=3,  python agent.py "question" --role R2
```

Needs `uv` (it fetches Python 3.12). `OPENAI_MODEL` has no default on purpose, so the model is always an explicit choice.

## Architecture

```mermaid
flowchart LR
  UI["app.py<br/>Streamlit"] --> A["agent.py<br/>hand-written tool-use loop"]
  A <-->|Chat Completions| M[("OpenAI model")]
  A <-->|"MCP over stdio<br/>(only RECRUITING_DB in the child env)"| S["mcp_server.py<br/>no logic"]
  S --> T["tools.py<br/>all business logic"]
  T --> D["db.py<br/>read-only plain SQL"]
  D --> DB[("SQLite")]
  G["generate_data.py + planted.py<br/>(stand-in for the ingest job)"] --> DB
```

The agent reaches data only through MCP; the UI's role list also comes through MCP.

| File | Job |
|---|---|
| `schema.sql` | The data model: roles, candidates, applications, stage_events, feedback, emails |
| `db.py` | Read path only: read-only connection, plain-SQL queries, and `AS_OF` (the data's "today") |
| `tools.py` | The five tools and all logic (funnel, tasks, rating summaries) |
| `mcp_server.py` | Registers the tools over MCP. No logic |
| `agent.py` | The loop, the system prompt, a small CLI |
| `app.py` | Chat UI, role picker, sample questions, tool-call trace |
| `planted.py` / `generate_data.py` | 12 hand-written candidates with exact ground truth, plus 38 seeded fillers |

## Design decisions

Each entry gives the choice, why, and what it costs.

### Data

- **The application (candidate × role) is the core unit.** Progress, feedback and emails belong to one person in one
  role, so a person can apply to two roles without their histories mixing. *Cost:* one more join in most queries.
- **Stage history is an append-only event log, and leaving is an event with a reason code.** Time in stage, the
  funnel and why people leave (`withdrew_comp`, `rejected_skills`) all fall out of it; a CHECK makes the reason
  required on exits. `current_stage` and `status` are kept as a convenience copy, and a test checks they match the log.
- **IDs are prefixed text** (`APP-006`, `FB-014`, `EV-0037`). Citations are unambiguous, and "does this cited ID
  exist" is one regex in the evals.
- **No demographic columns.** There is nothing for the model to misuse.
- **One fixed "today".** `AS_OF = 2026-11-01T12:00` lives in `db.py`, so every tool output, test and eval is
  reproducible. *Cost:* no live clock; calendar days, not business days.
- **Ground truth is planted.** Twelve hand-written candidates make the right answers known before any model runs;
  38 seeded fillers add volume but can never create a task, score a 4 or beat the planted top 3. *Cost:* the data
  reads like a test fixture. Only the expected answers depend on it, not the tools.

### Tools

- **Five coarse, read-only tools shaped like the questions**, rather than a SQL tool or many small getters. Few
  calls per answer, no model-written SQL, each tool testable alone, and nothing an injection could change.
  *Cost:* a question outside these shapes can't be answered.
- **Code does the math.** Counts, averages, rates, medians, durations and overdue flags come back computed; the
  prompt forbids arithmetic and says to quote.
- **Funnel rates count only people who have left a stage.** Someone still at onsite is in progress, not lost, so
  each rate comes with `n_left`, and in-progress people are reported separately with the oldest wait. Each stage
  also lists `exited_application_ids`, so the model knows whose profiles explain a drop.
- **Tasks are derived, not stored.** Three rules: `feedback_owed` (48h after an interview), `email_unanswered`
  (3 days after a candidate writes), `offer_outstanding` (7 days after an offer). Always current, and each task
  cites the record that triggered it. Overdue is strictly `AS_OF > due`, tested at 48h and 48h + 1 minute.
- **Search can sort by rating.** In stage order, the 20-row limit could hide a strong early-stage candidate in a
  large role; `sort_by="rating"` (highest average first, unrated last) is what the prompt uses to shortlist, and
  `total_matches` tells the model when rows were left out.
- **Docstrings and errors are written for the model.** Each docstring says when to use the tool and what it won't
  do ("stage order is NOT a ranking"). Errors name the next step ("Use search_applications to find valid ids").
  MCP 2.x forwards only `ToolError` text, so the server converts the tools' `ValueError`s.
- **Every result is a dict with `as_of`**, and every row carries the IDs and dates needed to cite it.

### Agent

- **A hand-written loop, no framework.** About 50 lines on OpenAI Chat Completions: append the assistant turn
  unchanged, answer each tool call with its own `role: tool` message, prefix failures with `ERROR:` (the API has no
  error flag), handle refusals, and stop at 8 rounds with an explicit message. Every path has a test.
- **Data only through MCP.** The agent never imports `tools.py`; even the UI's role list comes over MCP. The server
  runs as a child process with only `RECRUITING_DB` in its environment, so the API key never reaches it.
  *Cost:* about a second to start a server per question.
- **Ranking is the model's judgment over a written rubric, not a score.** Interview evidence first, then stage
  progression, then CV fit; flag thin evidence (under 3 interviews) and disagreement (rating spread of 2+). A single
  number would hide exactly those. Rankings end with a `RANKING:` line so evals can check them. *Cost:* less
  deterministic than a formula; a human makes the decision either way.
- **Memory carries the latest turn forward in full.** The previous question's tool calls and results go into the
  next request, so a follow-up reuses what was fetched. Recorded: "why isn't Viktor Hale in the top 3?" fetched only
  Viktor's profile; the top three's were already in context. Older turns (up to 5) are text only, and each keeps the role it was
  asked under. The data doesn't change between questions, so earlier results stay valid. *Cost:* a follow-up to a
  top-3 question starts at about 10k input tokens.
- **Answers are written for a recruiter.** Each candidate's name with the application ID once, readable dates, short
  verbatim quotes, record IDs gathered in one `Sources:` line, and inferences labelled "Inference:". Every tool call
  (name, arguments, raw result) sits under the answer in the UI.
- **Live progress.** `ask()` takes an `on_event` callback that fires as each model round and tool call starts; the UI
  shows them ("Opening the profile for APP-006") instead of a silent 20-second spinner.
- **No sampling parameters; the model is a required setting.** Some models reject `temperature`, so reproducibility
  comes from deterministic tools, a fixed `AS_OF` and repeated eval runs. `OPENAI_MODEL` has no default, so every
  result is quoted with the model that produced it.

### Safety

- **Candidate-written text is labelled untrusted.** The CV and inbound emails come back as `cv_text_untrusted` and
  `body_untrusted`; the prompt treats them as data and requires a "Security note" naming any embedded instruction.
  Our recruiter's outbound emails are not labelled: labelling them caused a false alarm. *Cost:* a prompt-level
  defence; one planted injection is a demonstration, not coverage.
- **Protected characteristics.** No such data exists, requests to rank on them are declined without calling tools,
  and candidates are referred to by name or "they", never gendered from a name. Evals check both.
- **Data minimization.** The candidate's email address is never returned to the model.
- **Decision support only.** The prompt forbids saying someone must be hired or rejected.

### Verification

- **Tests need no API key.** A scripted fake model drives the real loop against the real MCP server, the UI runs
  under Streamlit's test harness, and tools are checked against ground truth written separately in `planted.py`.
- **Evals are mechanical and repeated.** Eight questions, N runs each, checked by regex and set comparison, plus
  checks on every answer: cited IDs must exist in that run's tool results, no false security notes, no gendered
  pronouns outside quotes. Failed answers are saved to `evals/failures/<model>/` (not committed) for review. *Cost:* a correct answer phrased oddly can fail.

### Not built, on purpose

Auth, Docker, a vector database, an ORM, a frontend framework and write actions. Each is in
[Production and scale](#production-and-scale) with how it would be added.

## Data model

Six tables in `schema.sql`. Tasks are not a table; `get_pending_tasks` derives them from these rows.

| Table | What it holds | Why it is shaped this way |
|---|---|---|
| `roles` | title, team, hiring manager, `opened_at`, requirements | `opened_at` gives "days open" |
| `candidates` | name, email, CV text, source | person-level data, kept apart from per-role progress |
| `applications` | candidate, role, `applied_at`, `current_stage`, `status` | stage and status are a convenience copy; a test checks they match the event log |
| `stage_events` | append-only `from_stage -> to_stage`, `at`, actor, `reason_code` | dated history gives time-in-stage; exits are events (`rejected`/`withdrew`) with a coded reason, enforced by a CHECK |
| `feedback` | one row per interview: rating 1-4, recommendation, notes, `submitted_at` | `submitted_at` NULL means feedback is owed, which is what drives tasks |
| `emails` | thread, direction in/out, sender, recipient, `sent_at`, body | the latest message's direction says who owes a reply |

## Tools

| Tool | Use it for |
|---|---|
| `list_roles()` | role IDs, requirements, days open, active applications by stage |
| `search_applications(role_id, stage, status, name_contains, limit, sort_by)` | shortlisting: one compact row per application with `avg_rating`, `n_ratings`, `n_feedback_owed`, last activity; `sort_by` is `"stage"` (default) or `"rating"` |
| `get_candidate_profile(application_id)` | everything about one application: CV, stage history with days per stage, every interview's feedback with its state, a rating summary (`avg`, `spread`, `n_submitted`), email threads |
| `get_pipeline_funnel(role_id)` | per stage: reached, left, advanced, exited by reason (with `exited_application_ids`), still in stage, advance rate and median days over candidates who have **left** the stage only |
| `get_pending_tasks(role_id, overdue_only, limit)` | the three task rules, each with `due_at`, `is_overdue`, `days_overdue`, the rule that fired and `source_ids` |

## The data and what it is built to test

50 applications over 3 roles (R1 20, R2 16, R3 14). Twelve are hand-written ("planted") so the right
answers are known in advance and tests do not depend on running the model:

| Planted case | Tests |
|---|---|
| APP-001, 002 (R1) decline offers over compensation; APP-003, 004, 005 show a repeated system-design gap and 11-12 day onsite waits | The R1 funnel diagnosis: two leaks. Onsite advances 33% (vs ~80% elsewhere) with an ~12-day median wait, and the offer stage converts 0 of 2 (both declined over compensation) |
| APP-006, 007, 008 (R2) | The correct top 3; APP-008 has only two interviews (thin evidence) |
| APP-009 (R2) | Decoy: impressive CV, weak interview feedback |
| APP-010 (R2) | Prompt injection in the CV |
| APP-005, 006, 011 overdue; APP-012 pending | Exactly 6 tasks: 4 overdue, 2 pending |

Fillers are generated with a fixed seed and can never create a task, rate 4, or beat the planted top 3.

## Testing and verification

`make test` runs 48 tests with no API key: data invariants (counts, determinism, event log vs stage/status, nothing
after `AS_OF`, no demographic columns), each tool against the hand-computed ground truth in `planted.py`
(funnel numbers, exact task list, edge cases), the real MCP server over stdio, the agent loop against a scripted
fake model, the UI with a stubbed agent, and the eval checkers on canned answers.

`make eval` (or `make eval RUNS=3`) runs 8 questions (top 3, funnel diagnosis, tasks, a nonexistent person, "rank by age", the injection
case, and rewordings of the first two) through the real model. Checks are mechanical: the `RANKING` set, required
terms, and a no-hallucinated-IDs check that every cited `APP-###` appears in a tool result of that run.

**Eval pass rate (3 runs per case, readable-answer prompt, 2026-11-10):**

| Case | `gpt-5.5` | `gpt-5.4-mini` |
|---|---|---|
| top 3 | 2/3 | 1/3 |
| top 3 reworded | 3/3 | 0/3 |
| funnel diagnosis | 3/3 | 3/3 |
| funnel reworded | 3/3 | 2/3 |
| tasks | 3/3 | 3/3 |
| nonexistent person | 3/3 | 3/3 |
| rank by age | 3/3 | 3/3 |
| injection | 3/3 | 1/3 |
| **Total** | **23/24** | **16/24** |

**`gpt-5.5` scored highest.** Its one failure: a "Gaps" line called a candidate "her" right after quoting an interviewer's note
that did ("owns her pipeline end to end"). All 8 mini failures were gendered pronouns, several guessing gender from
first names. The mini column was run just before two small prompt tweaks (cap the Sources line at 8 IDs, omit it when
empty); every failure was a pronoun, which those tweaks don't touch. `gpt-5.5` takes about 7 minutes for 24 runs.

Earlier rounds on `gpt-5.5`: 23/24 before the pronoun rule, 24/24 after it with the original citation style (raw
timestamps and record IDs inline), then 23/24 with the readable style above. So readability cost no accuracy.

**Latest changes, partly re-evaluated.** The table above was measured before the rating sort and carried-forward
memory. A `gpt-5.5` rerun after them passed 14 of the 15 runs it completed (top 3 2/3; top 3 reworded, both funnel
cases and tasks 3/3) before the API account ran out of credits; nonexistent person, rank by age and injection were
not rerun. The one failure is the same pronoun pattern: the model introduced a quoted note with "she". The planted
interviewer notes use gendered pronouns, and the model sometimes carries them outside the quote marks.

What the evals caught along the way (first run was 6/8 with one run per case):
- **A false injection warning, caused by my own labelling.** The model flagged APP-006 as containing an "embedded
  instruction". The culprit was our recruiter's *outbound* offer email ("We would love an answer within a week or
  two"), which the profile had labelled `body_untrusted` along with every other email. Only candidate-written
  (inbound) bodies are untrusted now, and the eval fails any security note that names a candidate other than APP-010.
- **The model silently ignored the injection** instead of telling the user, so the prompt now requires a
  "Security note" line naming the application.
- **Funnel answers sometimes stopped at the numbers.** The funnel tool now lists `exited_application_ids` per stage
  so the model can open the profiles that explain the drop.
- **The `RANKING:` line was sometimes missing**; the rule is now repeated in the FORMAT section. Still intermittent
  on the mini model.
- **Gender guessed from names.** Answers called a nonexistent "Priya Nandakumar" "her". The prompt now says to use names
  or "they", and a universal check fails any gendered pronoun outside a verbatim quote (interviewers' own notes, such as
  "owns her pipeline end to end", may still be quoted).
- **Answers read like database dumps.** Citations put raw timestamps (`2026-10-20T10:00:00`) and record IDs
  (`EV-0037`) in the middle of sentences. The prompt now asks for names with the application ID once ("Mei-Lin Zhao
  (APP-006)"), readable dates ("Oct 20"), and the record IDs in one "Sources:" line at the end. The first run of
  the new style failed 3 of 24 runs on checks that were too literal ("I don't find any application", "system-design
  gap" with a hyphen); the checks were widened and each gained a test.

## Limitations

- Tested on two models only (`gpt-5.5`, `gpt-5.4-mini`), three runs per case. The pronoun check is a regex and
  only covers English he/she forms.
- Eval checks are regexes, so a correct answer phrased unexpectedly can fail. Three runs per case is still a small sample.
- Prompt-injection defense is prompt-level plus read-only tools. One planted case is a demonstration, not coverage.
- Ranking is judgment, not a score. This is decision support for a human; hiring AI is high-risk under the EU AI Act and
  covered by rules such as NYC Local Law 144, which a real deployment would need to address (audits, notices).
- A fresh MCP server process starts per question (about a second).
- Carrying the latest turn forward costs tokens: a follow-up to a top-3 question starts at about 10k input tokens.
  Fine here; at scale, profiles should return a summary first, with emails and CV on request.
- Shortlisting by rating means the model may never open a low-rated candidate. That follows the rubric, but the
  planted decoy (APP-009) now usually goes unopened in a top-3 answer; asking about it directly still works.
- Calendar days and hours, not business days. SQLite and synthetic data only.

## Production and scale

| Concern | This prototype | With real candidates at scale |
|---|---|---|
| Data source | Seeded SQLite | ATS API (Greenhouse, Lever, Ashby) synced to Postgres via webhooks + backfill; only `db.py` changes |
| Volume | ~50 applicants | Thousands per role: server-side filtering, aggregates, pagination (limit + cursor); never dump a pipeline into the model's context |
| Skill search | Not needed | One semantic-search tool over CVs; numbers still come from the structured tools |
| Who's asking | Anyone | Tools enforce the signed-in user's scopes server-side; MCP over HTTP with OAuth |
| Personal data | Fictional | Data minimization, zero-retention provider terms (confirm the chosen model and endpoint are eligible), redacted logs, deletion and retention, audit log |
| Fairness and law | No demographic fields | A human makes every decision; bias audits where required (e.g. NYC Local Law 144); EU AI Act high-risk duties |
| Untrusted text | One planted injection | Regression suite of injection cases; tools stay read-only until writes need human confirmation |
| Latency and cost | No caching; a new MCP server per question | Prompt caching, nightly precomputed funnel metrics, a smaller model for routine questions |
| Freshness | Fixed `AS_OF` | Real clock, "data as of last sync" |
| Correctness | 8 planted evals, 3 runs each | Recruiter-labelled set in CI, automatic check that every cited ID exists, user feedback |
| Actions | None | Agent drafts, a human confirms, everything logged |
| Tenancy | One company | Every query scoped by tenant |
| Reproducibility | No sampling parameters set; deterministic tools | Pinned model versions; eval regression gate before any prompt or model change |

**Seams already in the code** that make these changes cheap: `db.py` is the only read-path module that touches the
database; list tools take a `limit`; every result carries IDs and dates; `AS_OF` is one constant; the agent talks to
data only through MCP; tools are read-only; untrusted text is labelled; the candidate's email address is never returned;
`tools.py` takes no user identity yet, so a user/tenant argument goes in at one layer.

## AI usage

Built with Claude Code (Claude Sonnet) in a plan-then-build workflow: I wrote a brief, made design decisions,
then approved a written plan. Claude drafted the code, the synthetic data and the tests, and ran
them.