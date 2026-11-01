# Eval report: offline / claude

- Models: claude-haiku-4-5-20251001, claude-sonnet-4-6
- Runs: 1, incidents: 50, graph 2.0.0, dataset sha256 `3f53bba25abd`, scenarios `83ba789a789d`
- Prompts: proposer.md `04003ff2b144`, critic.md `7ed1ddfea4e4`

## Read this first

- Dataset: 50 synthetic incidents written and labeled by the project author; not production data.
- Tool results come from simulators driven by a declared fault per record (data/scenarios.json), with seeded confounders. Graph accuracy therefore measures whether the diagnosis logic finds the declared fault through noise; it is not an estimate of real-world accuracy.
- All rates carry 95% Wilson intervals; with n=50 an interval is roughly +/-10 points or wider.
- Offline mode uses a scripted LLM: explanation, critic-LLM, consistency, final-confidence, token and cost numbers describe that script, not a model. Only graph metrics, the deterministic critic stage and the ablations are meaningful offline.
- offline: scripted fake LLM and fake embeddings

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
| Sent to review | 4% (2/50; 95% CI 1-13%) |
| Review precision vs labels | 0% (0/2; 95% CI 0-66%) |
| Review recall vs labels | 0% (0/22; 95% CI 0-15%) |
| ECE, graph confidence | 0.1350 |
| ECE, final confidence | 0.1000 |

Review labels (`should_require_human_review`) were written for the original design; disagreement with them is reported, not optimized for.

## Explanation (proposer / critic / judge)

- Judge decisions: {'accept': 50}
- Revised once: 0% (0/50; 95% CI 0-7%)
- Grounded when accepted: 100% (50/50; 95% CI 93-100%)

### Critic on planted claims

50 incidents; draft set sha256 `f66c2dcee844`.

| Draft | Expected stage | Caught | By deterministic | By LLM | Critic unavailable |
|---|---|---|---|---|---|
| clean (false rejection) | - | 0% (0/50; 95% CI 0-7%) | - | - | 0 |
| fabricated_evidence | deterministic | 100% (50/50; 95% CI 93-100%) | 100% (50/50; 95% CI 93-100%) | 0% (0/50; 95% CI 0-7%) | 0 |
| fabricated_past_incident | deterministic | 100% (50/50; 95% CI 93-100%) | 100% (50/50; 95% CI 93-100%) | 0% (0/50; 95% CI 0-7%) | 0 |
| wrong_category | deterministic | 100% (50/50; 95% CI 93-100%) | 100% (50/50; 95% CI 93-100%) | 0% (0/50; 95% CI 0-7%) | 0 |
| contradicts_refuted | deterministic | 100% (47/47; 95% CI 92-100%) | 100% (47/47; 95% CI 92-100%) | 0% (0/47; 95% CI 0-8%) | 0 |
| placeholder_text | deterministic | 100% (50/50; 95% CI 93-100%) | 100% (50/50; 95% CI 93-100%) | 0% (0/50; 95% CI 0-7%) | 0 |
| unsupported_mechanism | llm | 0% (0/50; 95% CI 0-7%) | 0% (0/50; 95% CI 0-7%) | 0% (0/50; 95% CI 0-7%) | 0 |

## Consistency across runs

Single run; not measured.

## Retrieval

Not measured: needs real embeddings (OPENAI_API_KEY) in live mode.

## Cost and latency (per incident)

- Cost: median $0.0153, p95 $0.0153, total $0.7663; planted-claim critic $1.5615
- Tokens: median 3228; LLM calls: median 3
- End-to-end: median n/a, p95 n/a; LLM time: median n/a

## Ablations (graph only)

| Variant | Accuracy | Sent to review | Unsafe auto-clear |
|---|---|---|---|
| as_built: the graph and scenario world as committed | 100% (50/50; 95% CI 93-100%) | 4% (2/50; 95% CI 1-13%) | 0% (0/50; 95% CI 0-7%) |
| no_confounders: every benchmark record has only its declared fault | 100% (50/50; 95% CI 93-100%) | 4% (2/50; 95% CI 1-13%) | 0% (0/50; 95% CI 0-7%) |
| all_confounders: every benchmark record also carries both confounders (where they don't fake its fault) | 100% (50/50; 95% CI 93-100%) | 4% (2/50; 95% CI 1-13%) | 0% (0/50; 95% CI 0-7%) |
| delivery_first: the delivery check moved to the front of every plan (the pre-2.0 ordering) | 92% (46/50; 95% CI 81-97%) | 12% (6/50; 95% CI 6-24%) | 0% (0/50; 95% CI 0-7%) |
| delivery_first_all_confounders: delivery-first ordering in the all-confounders world | 60% (30/50; 95% CI 46-72%) | 44% (22/50; 95% CI 31-58%) | 0% (0/50; 95% CI 0-7%) |

## Failure patterns

None.
