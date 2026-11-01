# ReconAI

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-1C3A5E?style=flat&logo=langchain&logoColor=white)
![Claude API](https://img.shields.io/badge/Claude%20API-Sonnet%20%2B%20Haiku-D97757?style=flat&logo=anthropic&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Llama%203.3%2070B-F55036?style=flat&logo=groq&logoColor=white)
![OpenAI Embeddings](https://img.shields.io/badge/OpenAI-text--embedding--3--small-412991?style=flat&logo=openai&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?style=flat&logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-3-06B6D4?style=flat&logo=tailwindcss&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?style=flat&logo=supabase&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-HNSW-4169E1?style=flat&logo=postgresql&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-Frontend-000000?style=flat&logo=vercel&logoColor=white)
![Render](https://img.shields.io/badge/Render-Backend-46E3B7?style=flat&logo=render&logoColor=black)
![Framer Motion](https://img.shields.io/badge/Framer%20Motion-11-BB4B96?style=flat&logo=framer&logoColor=white)
![Recharts](https://img.shields.io/badge/Recharts-2.12-22B5BF?style=flat)
![Zustand](https://img.shields.io/badge/Zustand-4-443E38?style=flat)

AI-assisted root cause analysis for Salesforce FSC integration discrepancies. A deterministic hypothesis graph decides the diagnosis from cited evidence; an LLM writes the explanation, a critic checks every claim against that evidence, and anything unconfirmed or unverifiable goes to a person.

> **Demo scope.** Salesforce, Splunk and DB2 are simulated, and the evaluation dataset is 50 synthetic, author-labeled incidents. See [Evaluation](#evaluation) for what the numbers do and don't show.

---

## Links

| | |
|---|---|
| App | https://recon-ai-iota.vercel.app |
| Demo Video | https://youtu.be/cEzxQ1xfltU |
| Architecture | [docs/ADR.md](docs/ADR.md) |
| GitHub | https://github.com/PranavCR01/reconAI |

---

## The Problem

Salesforce FSC integration teams begin each day correlating data discrepancies between Salesforce and downstream systems such as DB2. The process depends on an Excel decision tree that encodes years of tribal knowledge: which Splunk query to run first, which FSC fields are commonly stripped by FLS, which CDC channels silently exclude custom objects. When a discrepancy repeats, the analyst must trace it from scratch. There is no postmortem, no audit trail, and no accumulated memory — only the same failures recurring week after week.

---

## What ReconAI Does

**Upload.** The analyst uploads the reconciliation CSV (up to 200 rows): object and field, the downstream DB2 table and column, both values, the discrepancy type and a severity.

**Diagnose.** For each row, a LangGraph state machine walks a hypothesis graph: it picks the next check for the discrepancy type, runs the check's tool, records the result as evidence with an ID, and marks the hypothesis confirmed, refuted or inconclusive. It stops at the first confirmation.

**Explain and verify.** A model drafts the explanation as claims that cite the evidence and similar past incidents. A critic checks each claim (deterministic rules first, then a model), and a judge in code accepts it, asks for one revision, or sends the incident to review.

**Review.** Results stream to the browser as they finish, P1 first. Each incident shows the hypothesis timeline with its evidence, the critic's verdict per claim, similar past incidents, a full trace with per-call tokens, latency and cost, and why it needs review if it does. Analysts record the confirmed cause and fix; summaries copy to the clipboard for Jira.

---

## Architecture

```
ingestion ─► hypothesis ⇄ evidence ─► retrieval ─► proposer ─► critic ─► judge ─► review gate
```

| Step | What it does | Model |
|---|---|---|
| Ingestion | Classify discrepancy type and severity | Haiku, only for ambiguous rows |
| Hypothesis graph | Pick the next check; record each verdict | none (code) |
| Evidence | Run the check's tool; store result, outcome and ID | none (code) |
| Retrieval | Find and rerank similar past incidents (pgvector) | Haiku reranker |
| Proposer | Write the explanation as cited claims | Sonnet |
| Critic | Deterministic claim checks, then a model review | Sonnet |
| Judge | Accept, revise once, or escalate | none (code) |

Details, the check order per discrepancy type and the reasoning behind each decision: [docs/ADR.md](docs/ADR.md).

### Data sources

| Source | Simulated checks |
|---|---|
| Salesforce | Field-level security for the integration user, CDC field configuration, Apex publish suppression |
| Splunk | Delivery of published change events, transform errors, retries |
| DB2 | Field value history, duplicate rows |
| Knowledge base | 25 resolved past incidents (`backend/seed/fsc_incidents.py`), embedded with `text-embedding-3-small` |

Simulator results are driven by a declared fault per record (`data/scenarios.json`) plus seeded noise, so the same record always tells the same story.

---

## Data Model

| Table | Purpose |
|---|---|
| `recon_runs` | One reconciliation run |
| `recon_rows` | One discrepancy row from the CSV |
| `rca_incidents` | The analysis: verdicts, claims with critic verdicts, judge decision, review reasons, model calls, trace, cost |
| `rca_evidence` | Every tool result, linked to the hypothesis it tested, with outcome and raw result |
| `resolutions` | The analyst's confirmed cause and fix |
| `recon_artifacts` | Knowledge base of past incidents (pgvector, HNSW) |
| `rca_cache` | 30-day cache per session; degraded results are never cached |

Schema changes are in `docs/sql/` (apply 001–006 before deploying this version).

---

## Evaluation

```bash
python -m backend.evals.run --mode offline --config claude            # free, deterministic, runs in CI
python -m backend.evals.run --mode live --config claude --runs 3 --yes  # real models, prints a cost estimate first
```

Results are committed in `evals/results/` with a report; the `/benchmark` page reads them. All rates carry 95% Wilson intervals.

| Measure (offline, 50 incidents) | Result |
|---|---|
| Graph root-cause accuracy | <!--m:offline_claude/metrics.accuracy.overall:pct-->100% (<!--m:offline_claude/metrics.accuracy.overall:frac-->50/50, CI <!--m:offline_claude/metrics.accuracy.overall:ci-->93-100%) |
| Same, with delivery checked first and seeded noise (ablation) | <!--m:offline_claude/ablations.delivery_first_all_confounders.accuracy:pct-->60% (<!--m:offline_claude/ablations.delivery_first_all_confounders.accuracy:frac-->30/50) |
| Unsafe auto-clear (wrong and not sent to review) | <!--m:offline_claude/metrics.routing.unsafe_auto_clear:frac-->0/50 |
| Planted fabricated evidence caught by the critic | <!--m:offline_claude/critic_planted.by_draft.fabricated_evidence.caught:frac-->50/50 |
| Planted wrong root-cause category caught | <!--m:offline_claude/critic_planted.by_draft.wrong_category.caught:frac-->50/50 |
| Clean explanations wrongly rejected | <!--m:offline_claude/critic_planted.by_draft.clean.false_rejection:frac-->0/50 |
| Agreement with the labels' "needs review" flag (recall) | <!--m:offline_claude/metrics.routing.review_vs_label.recall:frac-->0/22 |
| **Live** (Sonnet 4.6, 3 runs): model critic catches a planted unsupported mechanism | <!--m:live_claude/critic_planted.by_draft.unsupported_mechanism.caught:frac-->25/25 |
| **Live**: correct drafts the critic wrongly rejects | <!--m:live_claude/critic_planted.by_draft.clean.false_rejection:frac-->2/25 |
| **Live**: explanations accepted / grounded when accepted | <!--m:live_claude/metrics.explanation.judge_decisions.accept:num-->49 of 50 / <!--m:live_claude/metrics.explanation.grounded_when_accepted:frac-->49/49 |
| **Live**: same review decision across 3 runs | <!--m:live_claude/metrics.consistency.review_decision:frac-->46/50 |
| **Live**: cost per incident, median / p95 | <!--m:live_claude/metrics.cost_latency.cost_usd_median:usd-->$0.030 / <!--m:live_claude/metrics.cost_latency.cost_usd_p95:usd-->$0.061 |
| **Live**: end-to-end per incident, median / p95 (ms) | <!--m:live_claude/metrics.cost_latency.e2e_latency_ms_median:num-->25448 / <!--m:live_claude/metrics.cost_latency.e2e_latency_ms_p95:num-->51435 |

How to read this:

- The simulated world contains each labeled fault by construction, so graph accuracy shows the logic finds the declared fault through noise. It is **not** a real-world accuracy estimate.
- The ablation is the informative result: check order matters once noise is present.
- The review labels assume ambiguity the simulated world doesn't reproduce, so agreement with them is low; this is reported, not tuned away.
- Live rows come from `evals/results/live_claude.json` (real models, fake embeddings, so retrieval quality is not measured).

---

## Design Constraints

1. Every tested hypothesis has at least one evidence record; otherwise the incident is flagged `missing_evidence` and sent to review.
2. The system never changes data in any connected system. People record resolutions.
3. Confidence below 0.75, an unconfirmed diagnosis, weak evidence, or any rejected or unverifiable claim sets `requires_human_review`, with the reasons shown.
4. Every model call is logged with model, attempt, tokens, latency and errors, and costed.
5. P1 incidents display first regardless of processing order.
6. Pydantic validation at every agent boundary; invalid model output is retried once with the error.
7. Simulator responses depend on their inputs; nothing is hardcoded.

---

## Local Development

**Clone and install backend dependencies**

```bash
git clone https://github.com/PranavCR01/reconAI.git
cd reconAI
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Environment variables**

Create a `.env` file in the project root with the following:

```
ANTHROPIC_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SENTRY_DSN=                  # optional, no-op if unset
TRUSTED_IP_HEADER=           # optional, header your host sets with the real client IP
TRUSTED_PROXY_HOPS=          # optional, proxies appending to X-Forwarded-For (default 1)
```

**Run the backend**

```bash
uvicorn backend.main:app --reload --port 8000
```

Before debugging port conflicts: `netstat -ano | findstr :8000`

**Install frontend dependencies and run the dev server**

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` by default. The dev server proxies `/api` to `localhost:8000`; for other setups set `VITE_API_URL` (for example in a `.env.local` file in `frontend/`).

**Seed analytics data (run once)**

```bash
python -m backend.seed.analytics_seed
```

This inserts synthetic runs, incidents, resolutions and deployment events covering the 29 days that end three days before the seed runs, so they fall inside the Analytics window. The script is idempotent and skips if more than 10 runs already exist.

**Run the tests**

```bash
pip install -r requirements-dev.txt && pytest          # backend, offline, no network
cd frontend && npm test && npm run lint && npm run build
python scripts/check_docs.py                          # doc numbers match evals/results, no stale claims
```

Browser journey against an in-memory backend: `python -m backend.tests.e2e_server`, `npm run dev`, then `node e2e/journey.mjs` (from `frontend/`). Add `E2E_REAL_LLM=1` to the server command to use real models from your `.env` (still an in-memory database; each row costs money).

**Run the health check**

```bash
python scripts/health_check.py
```

Executes 40 end-to-end checks across all API endpoints and reports pass/fail with latency.

---

## Project Structure

```
reconAI/
├── backend/
│   ├── agents/        ingestion.py, hypothesis.py (graph walker), evidence.py,
│   │                  explanation.py (proposer / critic / judge), llm.py
│   ├── graph/         hypotheses.py (catalogue + rules), recon_graph.py (LangGraph wiring, tracing)
│   ├── tools/         world.py (scenario registry), salesforce_sim.py, splunk_sim.py, db2_sim.py, rag_tools.py
│   ├── prompts/       proposer.md, critic.md, VERSIONS.json
│   ├── models/        state.py (ownership rules), entities.py, outputs.py
│   ├── evals/         run.py, metrics.py, planted.py, harness.py, report.py, schema.py, publish.py
│   ├── storage/       supabase_adapter.py
│   ├── cache/         rca_cache.py
│   ├── seed/          fsc_incidents.py (knowledge base), analytics_seed.py
│   ├── tests/         pytest suite with in-memory Supabase, scripted LLM and embeddings
│   ├── config.py      model routing per step, pricing
│   └── main.py        FastAPI app, SSE streaming, cost guards
├── frontend/src/
│   ├── views/         Landing, Upload, LiveAnalysis, IncidentDetail, RunSummary, Analytics, Benchmark
│   ├── components/    incident/ (timeline, critic, trace panels), analytics/, layout/, ui/
│   ├── lib/           api.ts, sse.ts, incident.ts, format.ts
│   └── data/          eval_results.json (published from evals/results)
├── data/              sample CSV, benchmark ground truth, scenarios.json
├── evals/results/     committed eval results and reports
├── docs/              ADR.md, presentation-claims.md, sql/ migrations, history/ and slices/ (historical)
└── scripts/           check_docs.py, build_scenarios.py, health_check.py
```

---

## Built By

**Pranav CR**
Graduate Researcher, UIUC Information Management
Former Deloitte Analyst — Financial Services Cloud integrations
ML Intern, Drongo AI

[LinkedIn](https://www.linkedin.com/in/pranav-c-r-852752202/) | [GitHub](https://github.com/PranavCR01) | [Portfolio](https://pranavcr01.github.io/)
