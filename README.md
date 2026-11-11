# Recruiting Assistant

A chat assistant for a hiring team. It answers questions about open roles and applicants (top candidates,
where a pipeline leaks, what follow-ups are overdue) using five read-only tools exposed over MCP, and
shows every tool call behind each answer. Everything is fictional: the company (Northwind Freight), the
people and all `@example.com` addresses.

## Setup (5 commands)

```bash
git clone https://github.com/ajha7/recruiting-assistant.git && cd recruiting-assistant
cp .env.example .env          # add OPENAI_API_KEY and OPENAI_MODEL (the model id you want)
make setup && make data       # uv sync; build data/recruiting.db (deterministic)
make test                     # 42 tests, no API key needed
make app                      # Streamlit UI;  also: make eval,  python agent.py "question" --role R2
```

Needs `uv` (it fetches Python 3.12). `OPENAI_MODEL` has no default on purpose, so the model is always an explicit choice.

## Architecture

```
Streamlit app.py ──► agent.py ──(OpenAI API)──► model
                        │  hand-written tool-use loop
                        ▼  MCP over stdio (only RECRUITING_DB in the child env)
                   mcp_server.py ──► tools.py (all business logic) ──► db.py ──► SQLite (read-only)
generate_data.py + planted.py ──► data/recruiting.db   (stand-in for the production ingest job)
```

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

- **The model never calculates.** Averages, funnel rates, medians and overdue flags are computed in `tools.py`
  and quoted. Funnel rates count only candidates who have *left* a stage (`n_left` is returned), so people
  still in a stage are not counted as lost.
- **Tasks are derived, not stored.** Three rules over the raw records (`feedback_owed`, `email_unanswered`,
  `offer_outstanding`): feedback unsubmitted 48h after an interview, a candidate email with no reply after 3 days, an offer with no decision after 7 days. Overdue is
  strictly `AS_OF > due`; there is a boundary test at exactly 48h and 48h + 1 minute.
- **One fixed "today".** `AS_OF = 2026-11-01T12:00:00` lives in `db.py`, so every answer and test is reproducible.
- **Ranking is model judgment over a rubric** (interview evidence, then stage progression, then CV fit). Tools supply
  `avg_rating`, `n_submitted` and `rating_spread`; the prompt tells the model to flag thin evidence and disagreement.
  Answers end with a `RANKING:` line so evals can check them mechanically.
- **Untrusted text.** CVs and email bodies are returned under `*_untrusted` keys, and the prompt says they are
  data, never instructions. One planted CV contains an injection. Candidate email addresses are not returned.
- **No demographic data exists** in the schema, so there is nothing to misuse; the prompt also refuses
  protected-characteristic requests, and an eval checks it.
- **No framework, no ORM.** Plain functions, plain SQL, a plain loop. The loop uses OpenAI Chat Completions with function tools: it appends the assistant message back
  unchanged, answers every tool call with its own `role: tool` message, handles refusals and content-filter stops,
  and caps at 8 iterations with an explicit message instead of silently truncating. The API has no error flag on
  tool results, so failed calls are prefixed `ERROR:` in the text the model reads.
- **No sampling parameters are set** (some models reject them), so reproducibility comes from deterministic tools,
  a fixed `AS_OF`, strict prompt rules and the evals.
- **MCP 2.x note:** the installed SDK renamed `FastMCP` to `MCPServer`, and only `ToolError` text reaches the
  model, so `mcp_server.py` converts the tools' `ValueError`s (e.g. "No application with id 'APP-999'...").

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

`make test` runs 42 tests with no API key: data invariants (counts, determinism, event log vs stage/status, nothing
after `AS_OF`, no demographic columns), each tool against the hand-computed ground truth in `planted.py`
(funnel numbers, exact task list, edge cases), the real MCP server over stdio, the agent loop against a scripted
fake model, the UI with a stubbed agent, and the eval checkers on canned answers.

`make eval` runs 8 questions (top 3, funnel diagnosis, tasks, a nonexistent person, "rank by age", the injection
case, and rewordings of the first two) through the real model. Checks are mechanical: the `RANKING` set, required
terms, and a no-hallucinated-IDs check that every cited `APP-###` appears in a tool result of that run.

**Eval pass rate: not yet recorded.** The environment this was built in had no API key, so the live model path
(`agent.py` against OpenAI, `make eval`, the UI end to end) has *not* been run. Everything below it is tested.
After your first `make eval`, put the result here with the date and model ID.

## Limitations

- The live model path is untested as noted above; expect to tune the prompt after the first eval run.
- Eval checks are regexes, so a correct answer phrased unexpectedly can fail. One run per case; the model is non-deterministic.
- Prompt-injection defense is prompt-level plus read-only tools. One planted case is a demonstration, not coverage.
- Ranking is judgment, not a score. This is decision support for a human; hiring AI is high-risk under the EU AI Act and
  covered by rules such as NYC Local Law 144, which a real deployment would need to address (audits, notices).
- A fresh MCP server process starts per question (about a second). Chat memory is prior question/answer text only.
- Calendar days and hours, not business days. SQLite and synthetic data only.

## Production and scale

| Concern | What this prototype does | What production would need |
|---|---|---|
| Data source | SQLite file, loaded by a script | ATS webhooks plus backfill into Postgres; `db.py` becomes a read-only repository (the one file that changes) |
| Auth and tenancy | None | SSO, per-user and per-tenant scoping; `tools.py` gets a user/tenant argument |
| Scale | ~50 rows | Indexes, pagination (`limit` already on list tools), pre-aggregated funnel tables |
| Latency and cost | New server process and no caching per question | Long-lived MCP server, prompt caching, a cheaper model for simple lookups, streaming |
| Data protection | Fake data; emails omitted from profiles | PII minimization, retention limits, audit logs; confirm retention terms and zero-data-retention eligibility for the chosen model and endpoint |
| Security | Read-only tools, `_untrusted` labels | Injection testing at scale, output filtering, rate limits |
| Fairness and compliance | No demographic fields, refusal rule | Bias audits, candidate notices, human review of every decision |
| Quality | 8 evals, one run each | Larger eval set, repeated runs, LLM-judge plus human review, tracing in production |
| Reproducibility | Fixed `AS_OF`, deterministic tools | Model version pinning and eval regression gates in CI |

## AI usage

Built with Claude Code (Claude Sonnet) in a plan-then-build workflow: I wrote the brief and made the design decisions
and approved the written plan (`PLAN.md`); Claude drafted the code, the planted data and the tests, and ran
them. The planted candidates in `planted.py` are the most review-worthy file; its ground-truth numbers were
hand-computed and then cross-checked by tests that do not use the code under test. Claude also caught one of its
own errors in a test (a substring match flagging `hiring_manager`) and a SDK change (MCP 2.x). The agent was first written against Anthropic's API and then switched to OpenAI Chat Completions.
