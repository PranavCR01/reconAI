# ReconAI architecture and decisions

Current as of graph version 2.0.0. Earlier designs are in [docs/history/](history/) and [docs/slices/](slices/).

## 1. What runs for each discrepancy row

```
ingestion ─► hypothesis ⇄ evidence ─► retrieval ─► proposer ─► critic ─► judge ─► review gate
 (Haiku if     (code: pick next      (embed +     (Sonnet:    (code      (code:     (review_reasons
  ambiguous)    check, record         rerank,      cited       checks,    accept /   decide
                verdict) / (code:     Haiku)       claims)     then       revise     requires_human_
                run the check's tool)                          Sonnet)    once /     review)
                                                                          escalate)
```

`backend/graph/recon_graph.py` wires the nodes. A run's rows are analyzed concurrently (`ROW_CONCURRENCY`, default 4) and streamed as each finishes. Every node is wrapped to append one trace step
(start time, duration, a readable summary and the model calls it made).

| Node | Decides | LLM? | Owns these state keys |
|---|---|---|---|
| ingestion | discrepancy type and severity | only when the rules are ambiguous | `recon_row` |
| hypothesis | which check runs next; the verdict of each finished check | no | verdicts, graph status, root-cause category, tool calls |
| evidence | nothing: runs the queued tool and records the result with an ID | no | `evidence_collected` |
| rag_retrieval | which past incidents are relevant | reranker | candidates, reranked, `retrieval_error` |
| proposer | the wording of the explanation, as claims that cite evidence | yes | `proposal` |
| critic | whether each claim is supported | deterministic checks, then LLM | `critic_verdicts` |
| judge | accept, one revision, or escalate | no | final RCA, confidence |

Ownership is enforced: a node returning a key it doesn't own raises `StateOwnershipError`
(`backend/models/state.py`). `llm_calls`, `review_reasons`, `trace` and latency are append-only.

## 2. The hypothesis graph (`backend/graph/hypotheses.py`)

A declarative catalogue: one ordered plan per discrepancy type, one check per hypothesis. A rule
turns the check's tool result into **confirmed**, **refuted** or **inconclusive** (a check that
could not run is inconclusive, never refuted). The graph stops at the first confirmation.

| Discrepancy | Order |
|---|---|
| NULL_DOWNSTREAM | H1 cleared downstream → H3a FLS → H3b CDC exclusion → H3c Apex suppression → H2 delivery |
| VALUE_MISMATCH | HVM1 FLS → HVM2 DataWeave → HVM3 CDC → HVM4 Apex |
| STALE_VALUE | HSV1 CDC → HSV2 delivery |
| MISSING_RECORD | HMR1 Apex → HMR2 delivery |
| DUPLICATE_DOWNSTREAM | HDD1 retries → HDD2 duplicate rows |

**Decision: configuration checks before delivery checks.** A single missed event is common noise
(timeouts unrelated to the field). Checking delivery first let that noise mask FLS/CDC causes. The
ablation in the eval suite measures this directly: with seeded noise, delivery-first ordering drops
accuracy to <!--m:offline_claude/ablations.delivery_first_all_confounders.accuracy:pct-->60%
(<!--m:offline_claude/ablations.delivery_first_all_confounders.accuracy:frac-->30/50) against
<!--m:offline_claude/ablations.all_confounders.accuracy:pct-->100% as built.

**Decision: weak evidence routes to review.** A delivery confirmation resting on one missed event
gets confidence 0.70, below the 0.75 review threshold.

**Decision: no confirmation means no claimed root cause.** If every check is refuted or
inconclusive, the graph status is `exhausted`, the explanation may only state a hypothesis, and
the incident goes to review (`no_hypothesis_confirmed`).

## 3. Evidence

Every tool result becomes an evidence record with an ID, the hypothesis it tested, the tool and
arguments, the raw result and an outcome (supports / refutes / neutral / error / skipped). Tool
failures are recorded as `error` evidence, not dropped. Every tested hypothesis must have evidence
(coverage invariant); otherwise the incident gets `missing_evidence`.

Similar-incident retrieval searches with the row's object, field and type plus, when a cause was
confirmed, that cause in words. Refuted hypotheses are left out: they are what past incidents
should not be about.

Tool results come from simulators (`backend/tools/`) driven by a declared fault per record
(`data/scenarios.json`) plus seeded confounders. Unknown records get input-seeded random signals.

## 4. The explanation: proposer → critic → judge (`backend/agents/explanation.py`)

The graph decides the diagnosis; these steps only govern the explanation, which is where a model
can overstate or contradict the evidence.

- **Proposer** writes structured claims (root cause, mechanism, impact, fix, context). Each claim
  cites evidence and past incidents by short aliases (E1, P2) which are resolved to real IDs;
  unknown aliases are kept visibly as `UNKNOWN:` so they can be caught.
- **Critic**, deterministic stage: unknown citations, template placeholders, reliance on a refuted
  hypothesis, a category that conflicts with the confirmed one, an uncited root cause, an
  "established" cause on an unconfirmed graph, a cause backed only by refuting/failed evidence.
  LLM stage: meaning-level review of the claims that passed.
- **Judge** (code only): accept when every claim is supported and the graph confirmed a cause;
  otherwise one revision with the critic's feedback, then escalate.
- **Confidence cap:** when no hypothesis is confirmed, stored confidence is capped at 0.5 (the
  model's own figure is kept as `model_confidence`). A guess can't be more certain than its evidence.

Prompts live in `backend/prompts/` and are versioned by content hash (`VERSIONS.json`); a test
fails if a prompt changes without a version bump. Incidents store the prompt versions used.

## 5. Review gate

`requires_human_review` is derived from `review_reasons` (never set independently). Reasons:
unknown type, no hypothesis confirmed, weak graph evidence, missing evidence, confidence below
0.75, model unavailable, invalid model output, critic rejected or unavailable, step limit.

## 6. Reliability

- Degraded results (model or critic outage, tool error, retrieval error) are not cached, so the
  row is re-analyzed after recovery. Healthy results are cached for 30 days per session.
- `/api/v1/health` returns `ok` or `degraded` (database unreachable, empty knowledge base,
  missing migrations). Knowledge-base seeding failures go to logs and Sentry.
- Retrieval failure is recorded on the incident (`retrieval_error`), distinct from no matches.

## 7. Evaluation (`backend/evals/`)

One command reproduces the committed results: `python -m backend.evals.run --mode offline`.
Every incident goes through the production analysis path against an in-memory database.

What the offline numbers mean: the simulated world contains each labeled fault by construction,
so graph accuracy (<!--m:offline_claude/metrics.accuracy.overall:pct-->100%,
95% CI <!--m:offline_claude/metrics.accuracy.overall:ci-->93-100%) shows the diagnosis logic finds
the declared fault through noise. It is not an estimate of real-world accuracy. The informative
results are the ablations, the safety routing (unsafe auto-clear
<!--m:offline_claude/metrics.routing.unsafe_auto_clear:frac-->0/50) and the critic's planted-error
set. Model-dependent metrics (explanation quality, LLM critic, consistency, cost, latency) need a
live run: `python -m backend.evals.run --mode live --config claude --runs 3 --yes`.

## 8. Things that are deliberately not here

- No action changes data in any system. People record resolutions; nothing is replayed.
- No live Salesforce, Splunk or DB2 connections; all three are simulators.
- No Jira integration; summaries can be copied to the clipboard.
- Resolutions are stored but not yet written back into the retrieval knowledge base.
