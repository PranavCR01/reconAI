# Presentation claims checklist

Apply to the external deck and speaker notes before presenting. Every number in the
"Use instead" column is tagged and checked against `evals/results/offline_claude.json`
and `evals/results/live_claude.json` by `scripts/check_docs.py`. The live run used Claude
Sonnet 4.6 (proposer, critic) and Haiku 4.5 (reranker), 3 runs over the 50 incidents, with
fake embeddings (retrieval quality is not measured).

| # | Claim on the old slides / notes | Status | Use instead | Source |
|---|---|---|---|---|
| 1 | "70% root-cause accuracy" | Retired. Old simulators were random, so this was largely chance agreement; the script that produced it was never committed. | "On 50 synthetic labeled incidents, the graph finds the declared fault in <!--m:offline_claude/metrics.accuracy.overall:frac-->50/50 (95% CI <!--m:offline_claude/metrics.accuracy.overall:ci-->93-100%). That's logic correctness in a simulated world, not real-world accuracy." | `metrics.accuracy.overall` |
| 2 | (new) why the graph order matters | Verified | "Check delivery first, as the old graph did, and seeded noise drops accuracy to <!--m:offline_claude/ablations.delivery_first_all_confounders.accuracy:pct-->60%." | `ablations.delivery_first_all_confounders.accuracy` |
| 3 | (new) safety | Verified | "Wrong answers cleared without review: <!--m:offline_claude/metrics.routing.unsafe_auto_clear:frac-->0/50, also <!--m:offline_claude/ablations.delivery_first_all_confounders.unsafe_auto_clear:frac-->0/50 in the noisiest ablation, because weak evidence routes to a person." | `metrics.routing.unsafe_auto_clear` |
| 4 | Proposer → critic → judge pipeline | Now true (built in this redesign) | "A model drafts cited claims; a critic checks each one (code first, then a model); a judge in code accepts, revises once, or escalates." | `backend/agents/explanation.py` |
| 5 | "Each statement points to a record" | Now true | "Every claim cites evidence records by ID; citations that don't resolve are rejected. Planted fabricated citations caught: <!--m:offline_claude/critic_planted.by_draft.fabricated_evidence.caught:frac-->50/50; clean drafts wrongly rejected: <!--m:offline_claude/critic_planted.by_draft.clean.false_rejection:frac-->0/50." | `critic_planted.by_draft` |
| 6 | Model critic catches unsupported mechanisms | Verified (live, n=25) | "Planted a plausible mechanism no evidence supports: the model critic caught <!--m:live_claude/critic_planted.by_draft.unsupported_mechanism.caught:frac-->25/25. It also wrongly rejected <!--m:live_claude/critic_planted.by_draft.clean.false_rejection:frac-->2/25 correct drafts." | `live_claude: critic_planted.by_draft` |
| 7 | "Six systems incl. Snowflake" | False | "Three simulated sources (Salesforce, Splunk, DB2) plus a 25-incident knowledge base." | `backend/tools/`, `backend/seed/fsc_incidents.py` |
| 8 | "Replaying a failed event needs sign-off" | False: no replay action exists | "The system never changes data; people record the confirmed cause and fix." | `docs/ADR.md` §8 |
| 9 | "$0.006 per incident" | False: below the pricing floor for the tokens used | "About <!--m:live_claude/metrics.cost_latency.cost_usd_median:usd-->$0.030 per incident (median), <!--m:live_claude/metrics.cost_latency.cost_usd_p95:usd-->$0.061 at p95 when a revision runs." | `live_claude: metrics.cost_latency` |
| 10 | "Under 15 seconds" / "12.5 s per incident" | Misleading: LLM time only | "Median <!--m:live_claude/metrics.cost_latency.e2e_latency_ms_median:num-->25448 ms end to end per incident, p95 <!--m:live_claude/metrics.cost_latency.e2e_latency_ms_p95:num-->51435 ms; a run analyzes 4 rows at a time." | `live_claude: metrics.cost_latency` |
| 11 | "Access code reconai2026" | False: gate removed in May 2026 | "Open the app: no sign-up." | `frontend/src/views/Upload.tsx` |
| 12 | Jira export | False | "Copy Jira summaries to the clipboard, P1 first." | `frontend/src/views/RunSummary.tsx` |
| 13 | "Agreement with human-review labels" / "human review accuracy 56%" | Retired | "Agreement with the labels' review flag is low (recall <!--m:offline_claude/metrics.routing.review_vs_label.recall:frac-->0/22): the labels assume ambiguity the simulated world doesn't reproduce. Reported, not tuned." | `metrics.routing.review_vs_label` |
| 14 | "Hybrid config is optimal" | Unsupported | Omit. No current comparison across configs exists. | none |
| 16 | (new) explanation quality | Verified (live) | "With real models the judge accepted <!--m:live_claude/metrics.explanation.judge_decisions.accept:num-->49 of 50 explanations; every accepted one passed the grounding check (<!--m:live_claude/metrics.explanation.grounded_when_accepted:frac-->49/49); <!--m:live_claude/metrics.explanation.revised:frac-->6/50 needed one revision." | `live_claude: metrics.explanation` |
| 17 | (new) run-to-run consistency | Verified (live, 3 runs) | "Same root cause in all 3 runs for <!--m:live_claude/metrics.consistency.root_cause_category:frac-->50/50 incidents (the graph is deterministic); same review decision for <!--m:live_claude/metrics.consistency.review_decision:frac-->46/50." | `live_claude: metrics.consistency` |
| 15 | Resolutions feed back into retrieval ("memory loop") | False | "Resolutions are stored; feeding them back into retrieval is planned." | `docs/ADR.md` §8 |

## Before you present

- [ ] Every slide number appears in the table above with status Verified, or is removed.
- [ ] Re-run `python scripts/check_docs.py` after any re-run of the evals.
