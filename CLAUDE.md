# ReconAI — CLAUDE.md

## What This Is
AI-powered Salesforce integration reconciliation and RCA tool. Replaces a manual Excel decision tree used by Recon teams to diagnose data discrepancies between Salesforce FSC and downstream systems (DB2). Salesforce, Splunk and DB2 are simulated.

**Pitch:** "Datadog Bits AI SRE for Salesforce integration pipelines, with the Excel decision tree encoded as a deterministic hypothesis graph."  
**Audience:** Deloitte colleagues + Salesforce engineers. Every architectural choice must be defensible.  
**Full architecture:** see `docs/ADR.md`

---

## Stack
| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph |
| Output validation | Pydantic v2 |
| LLM default | Claude Haiku (classification) + Sonnet (reasoning) |
| LLM comparison | Groq Llama 3.3 70B |
| Embedding | OpenAI text-embedding-3-small (1536 dims) |
| Vector + structured store | Supabase (pgvector + Postgres) |
| Backend | FastAPI on Render |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui (New York) |
| State management | Zustand |
| Charts | Recharts |
| Streaming | Native SSE (EventSource, no library) |

---

## Repo Structure
```
reconai/
├── backend/
│   ├── agents/       # ingestion.py, hypothesis.py, evidence.py, synthesis.py
│   ├── tools/        # splunk_sim.py, salesforce_sim.py, db2_sim.py, rag_tools.py
│   ├── graph/        # recon_graph.py (LangGraph state machine)
│   ├── models/       # state.py, entities.py, outputs.py
│   ├── storage/      # adapter.py, supabase_adapter.py
│   ├── cache/        # rca_cache.py
│   ├── seed/         # fsc_incidents.py, analytics_seed.py
│   ├── config.py     # AgentConfig — LLM routing per agent
│   └── main.py       # FastAPI app + all endpoints
├── frontend/src/
│   ├── views/        # Landing, Upload, LiveAnalysis, IncidentDetail, RunSummary, Analytics
│   ├── components/analytics/  # StatCard, IncidentsOverTime, RootCauseDonut,
│   │                          # ByObjectChart, AIAccuracyChart, DeploymentTable
│   ├── store/        # reconStore.ts (Zustand)
│   └── lib/          # api.ts, sse.ts
├── data/sample_fsc_recon.csv
├── vercel.json       # SPA rewrite rule (all paths → /index.html)
└── docs/ADR.md + slices/slice-1.md … slice-8.md
```

---

## Pipeline — Boundaries Are Hard
`ingestion → hypothesis ⇄ evidence → rag_retrieval → proposer → critic → judge` (see `docs/ADR.md`).
- **Ingestion:** classify discrepancy type + severity. Haiku only for ambiguous rows. No tool calls.
- **Hypothesis:** walk the catalogue in `backend/graph/hypotheses.py`, record confirmed / refuted / inconclusive per check. Deterministic — no LLM.
- **Evidence:** execute ALL tool calls; every result is an evidence record with an ID, hypothesis key, outcome and raw result. Deterministic — no LLM.
- **Proposer:** writes the explanation as claims citing evidence (E#) and past incidents (P#). Sonnet. No tool calls.
- **Critic:** deterministic claim checks, then an LLM review. **Judge:** code only — accept / revise once / escalate.

Hypothesis decides *what* to check. Evidence *executes* the check. The graph decides the diagnosis; proposer/critic/judge only govern its explanation. Never merge these.
Each node may only write the state keys it owns (`OWNERS` in `backend/models/state.py`). Every LLM call appends `{agent, model, attempt, input_tokens, output_tokens, latency_ms, error?}` to `state.llm_calls`; every node appends a `trace` step.

---

## Non-Negotiables
1. Every tested hypothesis has ≥1 evidence record (tool errors included, as `error` outcome). Missing coverage → retry (max 2), then `missing_evidence` review reason.
2. The system never changes data in any connected system. Humans record resolutions; nothing is replayed automatically.
3. `requires_human_review` is derived from `review_reasons` only. Confidence < 0.75, an unconfirmed graph, weak evidence, or a rejected/unverifiable claim each add a reason.
4. Every LLM call logs model, attempt, tokens, latency and error, and is costed (`PRICING_PER_MTOK` in `config.py`; unknown model → cost None + warning, never $0).
5. P1 incidents display first in UI regardless of processing order.
6. Pydantic on every agent boundary. Schema violation → retry with error context.
7. Mock tools must vary responses based on input — no hardcoded strings.
8. Every number shown in docs or on `/benchmark` comes from a committed file in `evals/results/`.

---

## Supabase Tables
`recon_runs`, `recon_rows` (embedding vector(1536)), `rca_incidents`, `rca_evidence`, `resolutions`, `recon_artifacts` (pgvector + HNSW), `rca_cache`, `deployment_events`, `page_views`, `demo_requests`

---

## Workflow Rules
- Read CLAUDE.md at the start of every session
- Slice briefs in `docs/slices/` and `docs/history/` are historical; `docs/ADR.md` is the current design
- `/plan` before any implementation — resolve ambiguities first
- Never break the non-negotiables above
- Always verify only one Python process on port 8000 before debugging: `netstat -ano | findstr :8000`
- Analytics adapter methods use date-range queries (`get_recon_rows_since`) — never `.in_()` on large ID lists (PostgREST URL limit).
- CSS vars don't resolve in Recharts tooltips — use hex colors. Use `contentStyle` + `itemStyle` + `labelStyle` props directly; custom `content` prop is an alternative but `contentStyle` is reliable when all colors are hex.
- Recharts Tooltip `formatter` return is `[displayValue, displayName]` — the second element replaces the dataKey label, not the segment name.
- Analytics endpoints have 5-min in-memory cache (`_analytics_cache` in main.py). Cache key format: `f"{endpoint}:{days}"`. TTL = 300s.
- Routing: `/` = Landing (public), `/upload` = Upload (app entry). Vercel SPA rewrite in `vercel.json` required for direct-URL navigation to work on Vercel deployment.
- Landing page is standalone (no Shell/TopBar wrapper) — has its own nav with brand mark and "Open app →" CTA.
- No access gate on `/upload` (removed in May 2026). The `/track/demo-request` endpoint still exists but the UI no longer calls it.
- Tracking endpoints (`/track/pageview`, `/track/demo-request`) always return 200 — Supabase errors are caught and sent to Sentry, never surfaced to the client.
- `demo_requests` table columns: `id, name, email, company, requested_at, code_sent, notes`. Insert payload uses these exact keys (not `full_name`/`work_email`/`submitted_at`).
- Resend email notification on demo request: gated on `RESEND_API_KEY` + `NOTIFY_EMAIL` env vars. No-op if either is unset. Render env vars needed.
- Sentry init in `main.py` gated on `SENTRY_DSN` env var — no-op if unset. `sentry_sdk.capture_exception()` used in synthesis and tracking endpoints.
- Proposer/critic graceful degradation: API errors are caught → degraded explanation (confidence 0.0, `llm_unavailable` / `critic_unavailable` review reason, final_hypothesis "API_UNAVAILABLE"). SSE stream never crashes. Degraded results (any API error, tool error, retrieval error) are never written to `rca_cache`.
- `HealthBanner` in App.tsx: first check at 10s, then every 90s; "down" after 2 consecutive failures, "degraded" when `/health` says so (DB unreachable, empty knowledge base, missing migrations). Dismissible, auto-hides on recovery.
- SSE error banner in LiveAnalysis: `sseError` state set when SSE closes before `done` fires; "Retry" button increments `retryKey` to reconnect.
- `upsertIncident` in Zustand: skips update if incoming incident has no improvement (same/fewer hypotheses_tested, same/lower confidence, same status) over stored entry.
- `needsReviewCount` uses `requires_human_review && status !== 'complete'` — `IncidentStatus` is `'running' | 'complete' | 'needs_review' | 'escalated'`, no `'resolved'`.
- `get_run` endpoint returns `rows_scanned: len(rows)` (from `recon_rows` table) as authoritative row count — not `len(incidents)` which can be inflated by duplicates.
- `get_incident` endpoint returns `resolution` field (from `resolutions` table) if one exists. IncidentDetail shows read-only resolution view with Edit toggle when already resolved.
- Cache hit % in LiveAnalysis capped at `Math.min(100, ...)` — cacheHits accumulates across SSE reconnects but total is deduplicated.
- SSE `_stream_existing` fires when `not bypass_cache and len(existing_incidents) >= len(rows)` — partial runs fall through to full re-analysis. Pass `?bypass_cache=true` to force fresh LangGraph run.
- `updateRunInHistory(runId, { status: 'complete' })` called in SSE `onDone` — keeps localStorage run history in sync without page reload.
- SSE async generators (`_generate`, `_stream_existing`): `await`/`yield` must be inside the generator body — a `yield` in the outer endpoint scope turns it into a generator, making `return StreamingResponse(...)` a SyntaxError.
- Cost guards in `main.py` (public app, every row costs LLM calls): max 200 rows / 256 KB per upload (413); uploads 20/hour per IP, 300/day total; 5,000 analyzed rows/day total (uploads + `bypass_cache` re-runs + benchmarks); `bypass_cache` 5/hour per IP (SSE error event); benchmark 3/hour per IP (429). In-memory — resets on restart/deploy. Upload.tsx mirrors the 200-row cap and shows server errors inline.
- `/recall` uses `_recall_cache` dict with 1hr TTL (not the old bare `_recall_metrics_cache`). Cold start takes 20s+; always serve from cache on subsequent requests.

- Evals: `python -m backend.evals.run --mode offline` regenerates `evals/results/offline_claude.{json,md}` and `frontend/src/data/eval_results.json`. A golden test fails if results change without being regenerated. Live runs need `--yes`, refuse a real database, and never touch production Supabase.
- Prompts are versioned by content hash in `backend/prompts/VERSIONS.json`; update it in the same change as a prompt edit.
- Schema migrations live in `docs/sql/` (001–006). Apply them before deploying code that writes new columns; startup logs + Sentry flag missing columns.
- Docs: `python scripts/check_docs.py` (also a pytest) checks tagged metrics (`<!--m:stem/path:fmt-->value`) against `evals/results`, bans stale claims, and checks links/paths.
- Rate-limit client IP: rightmost `X-Forwarded-For` entry (`TRUSTED_PROXY_HOPS`, default 1) or `TRUSTED_IP_HEADER`. Verify against the host's real headers.

---

## Slice Plan
| Slice | What | Brief |
|---|---|---|
| 1 | Foundation — schema, models, storage adapter, FastAPI skeleton, sample CSV | `docs/slices/slice-1.md` |
| 2 | Ingestion + Hypothesis Agents, LangGraph state machine, basic tool sims | `docs/slices/slice-2.md` |
| 3 | Evidence Agent, Splunk simulator, parallel fan-out, early termination | `docs/slices/slice-3.md` |
| 4 | RAG pipeline, synthetic FSC seed data, Synthesis Agent, citation enforcement | `docs/slices/slice-4.md` |
| 5 | All 8 API endpoints, SSE streaming, RCA cache, batch embedding | `docs/slices/slice-5.md` |
| 6 | Frontend — all 4 views, SSE client, Zustand, sample data escape hatch | `docs/slices/slice-6.md` |
| 7 | Groq benchmarking, LLM config switcher, recall@k display | `docs/slices/slice-7.md` |
| 8 | Analytics dashboard — 6 endpoints, 6 components, deployment correlation, seed | `docs/slices/slice-8.md` |

---

## Session Log
| Date | Slice | What shipped | Risk flag |
|---|---|---|---|
| — | — | Architecture + ADR + CLAUDE.md complete | Splunk simulator realism is highest demo risk |
| 2026-05-02 | 1 | Models, storage adapter, FastAPI skeleton, sample CSV | supabase-py sync→async upgrade risk on v3 |
| 2026-05-03 | 2–5 | Ingestion/Hypothesis/Evidence agents, LangGraph, RAG pipeline, Synthesis Agent, all 8 endpoints, SSE streaming, RCA cache | llm_model stored inside rca_output JSONB; Evidence retry no-ops when tool_calls cleared |
| 2026-05-04 | 6 | All 4 views, SSE client, Zustand, Framer Motion, 0 TS errors. CORS fix. | Evidence empty on new discrepancy types |
| 2026-05-05 | debug | Fixed evidence/hypothesis bug, H4 dedup guard, evidence retry. All 5 discrepancy types verified. | — |
| 2026-05-06 | 8 | Analytics dashboard — 6 endpoints, 6 components, analytics_seed.py. 0 TS errors. | .in_() hits PostgREST URL limit — use date-range. CSS vars fail in Recharts — use hex. |
| 2026-05-06 | landing/tracking/infra | Landing at `/`, Upload at `/upload`, vercel.json SPA rewrite. Tracking endpoints, access gate, Sentry, HealthBanner, SSE retry banner. | demo_requests cols: name/email/company/requested_at |
| 2026-05-06 | bugfix | SSE dedup, upsertIncident, needsReviewCount, rows_scanned, resolution UX, cache hit % cap, ANALYZING count. | IncidentStatus has no 'resolved' — use 'complete' |
| 2026-05-07 | sse | SSE event IDs (id: header, Last-Event-ID reconnect). sseOpenedRef/retryKey removed. fix_applied optional. | resolutions needs fix_verified + UNIQUE on incident_id |
| 2026-05-07 | ui | Topbar → LIVE dot. P1 count fix. Runs breadcrumb → /upload (LiveAnalysis + RunSummary). Edit resolution pre-populates + Cancel + guard fix. Upload view-all → showAll button. | — |
| 2026-05-07 | backend | update_run_status in SSE _generate + _stream_existing before done yield. Hotfix: SyntaxError (await/yield outside generator body). | await/yield must be inside async generator, not outer endpoint |
| 2026-05-07 | tooling/perf | scripts/health_check.py — 40 E2E checks. /recall 1hr TTL cache. bypass_cache=bool on SSE stream; getStreamUrl uses URLSearchParams. | Run: python scripts/health_check.py |
| 2026-05-08 | benchmark | frontend/src/data/benchmark_data.json. Benchmark.tsx (standalone page: 4 Recharts charts + 5 written sections, data from JSON). Landing.tsx arrow fix + 3rd hero button. App.tsx route /benchmark. | CSS gap: 10 invalid — use gap: 10px or inline styles |
| 2026-05-08 | docs | docs/slides/linkedin_slides.html — 5 slides 1200x675 dark design system, CSS only, no images. README.md — 325 lines, badges, full architecture, benchmark table, local dev, project tree. | — |
| 2026-11-01 | redesign (#7–#16) | Test infra with fakes + CI; node-owned state + review reasons; evidence IDs/linkage; declarative hypothesis catalogue 2.0.0 + scenario simulators; proposer/critic/judge; tracing + cost; eval suite with committed results; honest incident UI; reliability fixes; docs rewrite. | Live evals not yet run (API credits); migrations 001–006 must be applied before deploy |
