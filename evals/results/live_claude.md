# Eval report: live / claude

- Models: claude-haiku-4-5-20251001, claude-sonnet-4-6
- Runs: 3, incidents: 50, graph 2.0.0, dataset sha256 `3f53bba25abd`, scenarios `83ba789a789d`
- Prompts: proposer.md `04003ff2b144`, critic.md `7ed1ddfea4e4`

## Read this first

- Dataset: 50 synthetic incidents written and labeled by the project author; not production data.
- Tool results come from simulators driven by a declared fault per record (data/scenarios.json), with seeded confounders. Graph accuracy therefore measures whether the diagnosis logic finds the declared fault through noise; it is not an estimate of real-world accuracy.
- All rates carry 95% Wilson intervals; with n=50 an interval is roughly +/-10 points or wider.
- live: real LLM calls
- no OPENAI_API_KEY: embeddings faked, retrieval not measured

## Diagnosis (hypothesis graph)

| Metric | Value |
|---|---|
| Root-cause accuracy | 100% (50/50; 95% CI 93-100%) |
| &nbsp;&nbsp;DUPLICATE_DOWNSTREAM | 100% (3/3; 95% CI 44-100%) |
| &nbsp;&nbsp;MISSING_RECORD | 100% (2/2; 95% CI 34-100%) |
| &nbsp;&nbsp;NULL_DOWNSTREAM | 100% (20/20; 95% CI 84-100%) |
| &nbsp;&nbsp;STALE_VALUE | 100% (4/4; 95% CI 51-100%) |
| &nbsp;&nbsp;VALUE_MISMATCH | 100% (21/21; 95% CI 85-100%) |
| Within labeled minimum checks | 100% (50/50; 95% CI 93-100%) |
| Deciding check matches label (correct only) | 94% (47/50; 95% CI 84-98%) |
| Mean checks run | 2.06 |
| Errors | 0 |

## Safety routing

| Metric | Value |
|---|---|
| **Unsafe auto-clear** (wrong and not sent to review) | 0% (0/50; 95% CI 0-7%) |
| Sent to review | 6% (3/50; 95% CI 2-16%) |
| Review precision vs labels | 33% (1/3; 95% CI 6-79%) |
| Review recall vs labels | 5% (1/22; 95% CI 1-22%) |
| ECE, graph confidence | 0.1350 |
| ECE, final confidence | 0.0722 |

Review labels (`should_require_human_review`) were written for the original design; disagreement with them is reported, not optimized for.

## Explanation (proposer / critic / judge)

- Judge decisions: {'accept': 49, 'escalate': 1}
- Revised once: 12% (6/50; 95% CI 6-24%)
- Grounded when accepted: 100% (49/49; 95% CI 93-100%)

### Critic on planted claims

25 incidents; draft set sha256 `23aedc042817`.

| Draft | Expected stage | Caught | By deterministic | By LLM | Critic unavailable |
|---|---|---|---|---|---|
| clean (false rejection) | - | 8% (2/25; 95% CI 2-25%) | - | - | 0 |
| fabricated_evidence | deterministic | 100% (25/25; 95% CI 87-100%) | 100% (25/25; 95% CI 87-100%) | 0% (0/25; 95% CI 0-13%) | 0 |
| fabricated_past_incident | deterministic | 100% (25/25; 95% CI 87-100%) | 100% (25/25; 95% CI 87-100%) | 0% (0/25; 95% CI 0-13%) | 0 |
| wrong_category | deterministic | 100% (25/25; 95% CI 87-100%) | 100% (25/25; 95% CI 87-100%) | 0% (0/25; 95% CI 0-13%) | 0 |
| contradicts_refuted | deterministic | 100% (25/25; 95% CI 87-100%) | 100% (25/25; 95% CI 87-100%) | 0% (0/25; 95% CI 0-13%) | 0 |
| placeholder_text | deterministic | 100% (25/25; 95% CI 87-100%) | 100% (25/25; 95% CI 87-100%) | 4% (1/25; 95% CI 1-20%) | 0 |
| unsupported_mechanism | llm | 100% (25/25; 95% CI 87-100%) | 0% (0/25; 95% CI 0-13%) | 100% (25/25; 95% CI 87-100%) | 0 |

## Consistency across runs

- root_cause_category: 100% (50/50; 95% CI 93-100%)
- review_decision: 92% (46/50; 95% CI 81-97%)
- judge_decision: 92% (46/50; 95% CI 81-97%)

## Retrieval

Not measured: needs real embeddings (OPENAI_API_KEY) in live mode.

## Cost and latency (per incident)

- Cost: median $0.0304, p95 $0.0613, total $1.6835; planted-claim critic $0.8691
- Tokens: median 4893; LLM calls: median 3
- End-to-end: median 25448 ms, p95 51435 ms; LLM time: median 25376 ms

## Failure patterns

- **correct diagnosis, explanation escalated** (critic_rejected): 1: BM-023
