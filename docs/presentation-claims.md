# Presentation claims checklist

Apply to the external deck and speaker notes before presenting. Every number in the
"Use instead" column is tagged and checked against `evals/results/offline_claude.json`
by `scripts/check_docs.py`. Live-model numbers (cost, latency, explanation quality) are
**not available yet**: no live run is committed. Don't quote them until one is.

| # | Claim on the old slides / notes | Status | Use instead | Source |
|---|---|---|---|---|
| 1 | "70% root-cause accuracy" | Retired. Old simulators were random, so this was largely chance agreement; the script that produced it was never committed. | "On 50 synthetic labeled incidents, the graph finds the declared fault in <!--m:offline_claude/metrics.accuracy.overall:frac-->50/50 (95% CI <!--m:offline_claude/metrics.accuracy.overall:ci-->93-100%). That's logic correctness in a simulated world, not real-world accuracy." | `metrics.accuracy.overall` |
| 2 | (new) why the graph order matters | Verified | "Check delivery first, as the old graph did, and seeded noise drops accuracy to <!--m:offline_claude/ablations.delivery_first_all_confounders.accuracy:pct-->60%." | `ablations.delivery_first_all_confounders.accuracy` |
| 3 | (new) safety | Verified | "Wrong answers cleared without review: <!--m:offline_claude/metrics.routing.unsafe_auto_clear:frac-->0/50, also <!--m:offline_claude/ablations.delivery_first_all_confounders.unsafe_auto_clear:frac-->0/50 in the noisiest ablation, because weak evidence routes to a person." | `metrics.routing.unsafe_auto_clear` |
| 4 | Proposer → critic → judge pipeline | Now true (built in this redesign) | "A model drafts cited claims; a critic checks each one (code first, then a model); a judge in code accepts, revises once, or escalates." | `backend/agents/explanation.py` |
| 5 | "Each statement points to a record" | Now true | "Every claim cites evidence records by ID; citations that don't resolve are rejected. Planted fabricated citations caught: <!--m:offline_claude/critic_planted.by_draft.fabricated_evidence.caught:frac-->50/50; clean drafts wrongly rejected: <!--m:offline_claude/critic_planted.by_draft.clean.false_rejection:frac-->0/50." | `critic_planted.by_draft` |
| 6 | Model critic catches unsupported mechanisms | Not measured | Don't claim. Offline the model critic is scripted (<!--m:offline_claude/critic_planted.by_draft.unsupported_mechanism.caught:frac-->0/50 is the script, not a model). Needs a live run. | `critic_planted.by_draft.unsupported_mechanism` |
| 7 | "Six systems incl. Snowflake" | False | "Three simulated sources (Salesforce, Splunk, DB2) plus a 25-incident knowledge base." | `backend/tools/`, `backend/seed/fsc_incidents.py` |
| 8 | "Replaying a failed event needs sign-off" | False: no replay action exists | "The system never changes data; people record the confirmed cause and fix." | `docs/ADR.md` §8 |
| 9 | "$0.006 per incident" | False: below the pricing floor for the tokens used | Omit until a live run. If asked: earlier live spot checks cost roughly $0.02–0.06 per incident depending on whether a revision ran (not a committed measurement). | none committed |
| 10 | "Under 15 seconds" / "12.5 s per incident" | Misleading: LLM time only | Omit until a live run reports end-to-end median and p95 (`cost_latency.e2e_latency_ms_*`). | none committed |
| 11 | "Access code reconai2026" | False: gate removed in May 2026 | "Open the app: no sign-up." | `frontend/src/views/Upload.tsx` |
| 12 | Jira export | False | "Copy Jira summaries to the clipboard, P1 first." | `frontend/src/views/RunSummary.tsx` |
| 13 | "Agreement with human-review labels" / "human review accuracy 56%" | Retired | "Agreement with the labels' review flag is low (recall <!--m:offline_claude/metrics.routing.review_vs_label.recall:frac-->0/22): the labels assume ambiguity the simulated world doesn't reproduce. Reported, not tuned." | `metrics.routing.review_vs_label` |
| 14 | "Hybrid config is optimal" | Unsupported | Omit. No current comparison across configs exists. | none |
| 15 | Resolutions feed back into retrieval ("memory loop") | False | "Resolutions are stored; feeding them back into retrieval is planned." | `docs/ADR.md` §8 |

## Before you present

- [ ] Every slide number appears in the table above with status Verified, or is removed.
- [ ] Re-run `python scripts/check_docs.py` after any re-run of the evals.
- [ ] If a live run is committed, add its cost and latency rows here with tags pointing at `live_claude`.
