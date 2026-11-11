# Sample runs

Recorded on 2026-11-10 with `gpt-5.5`, by calling `agent.ask()` (the same code path as the UI) with a client
that logs every model request and response. Data is as of Nov 1, 2026, 12:00. The answers below are verbatim.

| Question | Role | Model rounds | Tool calls | Input tokens (all rounds) | Output tokens | Time |
|---|---|---|---|---|---|---|
| Who are the top 3 candidates for this role, and why? | R2 | 3 | 8 | 15,103 | 1,475 | 19.9s |
| Why isn't Viktor Hale in the top 3? Their CV looks the strongest. | R2 | 2 | 1 | 21,315 | 995 | 13.6s |
| This role has been open for 4 months. Where is our process losing candidates? | R1 | 3 | 7 | 17,121 | 1,538 | 20.0s |
| Which tasks are pending or overdue? | all | 2 | 1 | 5,130 | 389 | 5.5s |

Input tokens add up across rounds because each round resends the conversation so far.

## Top candidates

**Question** (role R2, Machine Learning Engineer): Who are the top 3 candidates for this role, and why?

**Tool calls**

- Round 1 (2 messages, 2,166 tokens in, 2.1s): `list_roles()`; `search_applications(role_id="R2", status="active", limit=10, sort_by="rating")`
- Round 2 (5 messages, 3,609 tokens in, 3.3s): `get_candidate_profile(application_id="APP-006")`; `get_candidate_profile(application_id="APP-007")`; `get_candidate_profile(application_id="APP-008")`; `get_candidate_profile(application_id="APP-118")`; `get_candidate_profile(application_id="APP-117")`; `get_candidate_profile(application_id="APP-010")`
- Round 3 (12 messages, 9,328 tokens in, 14.1s): none, writes the answer

**Answer**

> My recommended top 3 to review for R2 — Machine Learning Engineer are:
>
> 1. **Mei-Lin Zhao (APP-006)**  
>    - Strongest interview evidence: **avg rating 3.83 across 6 submitted interviews**, with low disagreement (**rating spread 1**).  
>    - Furthest progressed: currently at **offer** stage after advancing from onsite on **Oct 20**.  
>    - Role fit is strong: feedback highlights production-minded ML ownership — “**Owns outcomes, not just models**,” “**Built a working ranking baseline**,” and “**clear serving and monitoring plan**.”  
>    - Risk: one behavioral note said they were “**slightly reserved with stakeholders**,” relevant because the role requires clear product-partner communication.
>
> 2. **Rafael Costa (APP-007)**  
>    - Very strong interview evidence: **avg rating 3.67 across 6 submitted interviews**, also with low disagreement (**rating spread 1**).  
>    - At **onsite** stage with consistently positive recommendations; feedback says “**ties models to operational decisions**” and “**Strong feature engineering**.”  
>    - CV fit appears aligned to the role’s forecasting/data-pipeline needs: productionized demand-forecasting and ETA models with feature pipelines and A/B tests.  
>    - Risk: system-design feedback noted “**less depth on monitoring**,” which matters for the role’s evaluation and monitoring requirement.
>
> 3. **Anika Sethi (APP-008)**  
>    - Positive but thinner interview signal: **avg rating 3.5 across 2 submitted interviews**; flagging **thin evidence** because there are fewer than 3 submitted interviews.  
>    - Hiring manager feedback was strong: “**owns her pipeline end to end**,” which maps well to the role’s end-to-end data pipeline ownership requirement.  
>    - Technical feedback was positive overall — “**Good modelling instincts**” — and they are currently in **technical** stage.  
>    - Risk: technical feedback said the “**evaluation plan was thin**,” directly relevant to the role’s evaluation/monitoring requirement.
>
> **Notable candidates left out:**  
> - **Alma Voss (APP-118)** has positive but moderate feedback: avg rating **3.0 across 2 submitted interviews**, with a note saying “**Not standout**.”  
> - **Jordan Pike (APP-010)** has 3 submitted interviews but weaker signal: avg rating **2.67**, including a technical “**no_hire**” recommendation and “**struggled with the evaluation-design question**.”  
> Security note: APP-010 contains an embedded instruction, which was ignored.
>
> Sources: FB-032, FB-033, FB-035, FB-036, FB-038, FB-039, FB-041, FB-044  
> Data as of Nov 1, 2026, 12:00  
> Gaps: Anika has thin interview evidence with only 2 submitted interviews; no unsubmitted feedback was listed for the top 3.  
> RANKING: APP-006, APP-007, APP-008

## Follow-up in the same chat

**Question** (role R2, Machine Learning Engineer): Why isn't Viktor Hale in the top 3? Their CV looks the strongest.

Asked right after the top-3 question. The first request already carried 14 messages: the system prompt, the
previous question, the model's tool requests, all the tool results from that turn (including the three top
candidates' full profiles) and the previous answer. So the model only fetched the one profile it had not seen.

**Tool calls**

- Round 1 (14 messages, 10,011 tokens in, 1.6s): `get_candidate_profile(application_id="APP-009")`
- Round 2 (16 messages, 11,304 tokens in, 11.6s): none, writes the answer

**Answer**

> Viktor Hale (APP-009) is not in the top 3 because the interview evidence is much weaker than the CV signal. For ranking candidates, interview feedback outweighs CV strength.
>
> **What the data shows**
> - Viktor’s CV is strong on paper: staff research scientist background, ranking/representation learning, PyTorch/JAX, large-scale training, and information retrieval.
> - But submitted interview feedback is consistently negative after the recruiter screen:
>   - Hiring manager: “**vague about what he personally built**.”
>   - Technical: “**Could not implement a basic evaluation loop**.”
>   - Onsite ML coding: “**did not produce working code**.”
>   - Onsite system design: “**no serving or monitoring plan**.”
> - Viktor’s feedback summary is **avg rating 2.0**, with **5 submitted interviews** and **rating spread 2**. That rating spread flags interviewer disagreement, but the later-stage signal is notably weak.
> - By comparison, the current top 3 have stronger interview evidence:
>   - Mei-Lin Zhao (APP-006): **avg rating 3.83 across 6 submitted interviews**, with feedback like “**Owns outcomes, not just models**” and “**Built a working ranking baseline**.”
>   - Rafael Costa (APP-007): **avg rating 3.67 across 6 submitted interviews**, with “**ties models to operational decisions**.”
>   - Anika Sethi (APP-008): **avg rating 3.5 across 2 submitted interviews**, with “**owns her pipeline end to end**,” though her evidence is thin.
>
> **Inference**
> Viktor may have the strongest research résumé, but the role requires shipping ML to production, evaluation/monitoring, and end-to-end ownership. The interview record raises direct concerns in those areas, especially implementation, evaluation, serving, and monitoring. That is why I would not place Viktor above Mei-Lin, Rafael, or Anika for recruiter review.
>
> Sources: FB-032, FB-033, FB-038, FB-044, FB-046, FB-047, FB-048, FB-049  
> Data as of Nov 1, 2026, 12:00  
> Gaps: Anika’s evidence is thinner than Viktor’s by interview count, but her submitted feedback is materially stronger.  
> RANKING: APP-006, APP-007, APP-008

Note: this answer twice calls a candidate "her" outside a quote, picking the pronoun up from an interviewer's
note it had just quoted. The evals' pronoun check catches this; see Limitations in the README.

## Where the pipeline loses people

**Question** (role R1, Senior Backend Engineer): This role has been open for 4 months. Where is our process losing candidates?

**Tool calls**

- Round 1 (2 messages, 2,169 tokens in, 1.8s): `get_pipeline_funnel(role_id="R1")`
- Round 2 (4 messages, 3,080 tokens in, 2.9s): `get_candidate_profile(application_id="APP-001")`; `get_candidate_profile(application_id="APP-002")`; `get_candidate_profile(application_id="APP-003")`; `get_candidate_profile(application_id="APP-004")`; `get_candidate_profile(application_id="APP-114")`; `get_candidate_profile(application_id="APP-115")`
- Round 3 (11 messages, 11,872 tokens in, 14.9s): none, writes the answer

**Answer**

> The process is losing candidates mainly at **onsite** and then **offer**.
>
> ## What the funnel shows
>
> - **Onsite is the sharpest interview-stage drop-off.**  
>   7 candidates reached onsite; 6 have left that stage; only 2 advanced. The onsite **advance_rate is 0.33**, with **4 exits for rejected_skills**. Median time in onsite is **11.6 days**, higher than earlier stages.
>
> - **Offer is a complete loss so far.**  
>   2 candidates reached offer; both left; **0 advanced**, and both exits were **withdrew_comp**. Offer advance_rate is **0.0**, with median time in offer **7.5 days**.
>
> - **Earlier stages are not the main loss point.**  
>   Applied, recruiter screen, hiring manager, and technical all have advance rates between **0.78 and 0.83**, with median days between **4.0 and 6.0**.
>
> - **There is also stale work earlier in the funnel, but it is not counted as loss.**  
>   Applied has 2 still in stage, oldest waiting **77.6 days**. Recruiter screen has 1 still in stage, oldest waiting **68.9 days**. The funnel notes these are “still_in_stage,” not lost.
>
> ## What exited onsite profiles show
>
> All 4 onsite exits were rejected for skills, and the recurring theme is **system design at scale**, especially partitioning, failure modes, backpressure, and single-node designs.
>
> - Hana Petrova (APP-003): onsite feedback said they “could not scale the queue design beyond a single node” and “struggled to reason about failure modes and capacity.”
> - Declan Moore (APP-004): feedback said there was “no answer for hot partitions or backpressure” and “heavy prompting on capacity planning.”
> - Saoirse Eriksen (APP-114): feedback said the design “did not scale past a single node” and was “weak on partitioning and failure modes.”
> - Mateus Xu (APP-115): feedback also said “weak on partitioning and failure modes” and “did not scale past a single node.”
>
> ## What exited offer profiles show
>
> Both offer-stage losses were compensation-related.
>
> - Tobias Wren (APP-001) declined after saying the “base salary and equity here are below” another offer, then later cited the “compensation gap.”
> - Imani Okoye (APP-002) said total compensation was “roughly 15% under” another offer and later that “the compensation gap is too large.”
>
> ## Inference
>
> - **Onsite may be screening for senior distributed-systems depth that earlier stages are not reliably detecting.** The same gap appears in all 4 onsite rejects reviewed.
> - **Compensation competitiveness is likely blocking closes.** Both candidates who reached offer had strong interview feedback, but both withdrew for compensation.
> - **The long waits in applied/recruiter screen may indicate stale candidates or process hygiene issues**, but the funnel does not show them as losses yet.
>
> ## Suggested recruiting actions to review
>
> - Add a focused distributed-systems/scaling screen before onsite, or make the technical stage test partitioning, failure modes, and capacity planning earlier.
> - Calibrate hiring-manager and technical interview pass criteria against the onsite bar.
> - Review compensation bands or pre-close expectations before offer, since both offers were lost for comp.
> - Clean up stale applied/recruiter-screen candidates so they do not age quietly in the funnel.
>
> Sources: FB-017, FB-018, FB-023, FB-024, FB-116, FB-122, EM-004, EM-009  
> Data as of Nov 1, 2026, 12:00

## Pending and overdue tasks

**Question** (all roles): Which tasks are pending or overdue?

**Tool calls**

- Round 1 (2 messages, 2,148 tokens in, 1.3s): `get_pending_tasks(overdue_only=false, limit=50)`
- Round 2 (4 messages, 2,982 tokens in, 3.8s): none, writes the answer

**Answer**

> There are **6 pending tasks**, **4 overdue**, as of today.
>
> **Overdue**
> - **Mei-Lin Zhao (APP-006), R2** — offer outstanding; offer made Oct 20 with no decision recorded. Due **Oct 27, 10am**; **5.1 days overdue**.
> - **Sofia Marchetti (APP-011), R3** — unanswered candidate email, “Re: Next step: portfolio review,” received Oct 24. Due **Oct 27, 2:20pm**; **4.9 days overdue**.
> - **Yusuf Demir (APP-005), R1** — Dana Okafor owes onsite feedback from Oct 26, 10am. Due **Oct 28, 10am**; **4.1 days overdue**.
> - **Yusuf Demir (APP-005), R1** — Kofi Mensah owes onsite feedback from Oct 26, 3pm. Due **Oct 28, 3pm**; **3.9 days overdue**.
>
> **Pending, not overdue**
> - **Owen Gallagher (APP-012), R3** — Tomas Reyes owes hiring-manager feedback from Oct 31, 2pm. Due **Nov 2, 2pm**.
> - **Owen Gallagher (APP-012), R3** — unanswered candidate email, “Portfolio format,” received Oct 31. Due **Nov 3, 9am**.
>
> Sources: EV-0037, EM-018, FB-029, FB-030, FB-055, EM-022  
> Data as of Nov 1, 2026, 12:00

