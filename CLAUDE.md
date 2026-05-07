# ReconAI — CLAUDE.md

## What This Is
AI-powered Salesforce integration reconciliation and RCA tool. Replaces a manual Excel decision tree used by Recon teams to diagnose data discrepancies between Salesforce FSC and downstream systems (DB2, Snowflake).

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

## Four Agents — Boundaries Are Hard
- **Ingestion:** classify discrepancy type + severity. Haiku only. No tool calls.
- **Hypothesis:** walk graph, decide next step. Sonnet. Routes to Evidence Agent.
- **Evidence:** execute ALL tool calls. Sonnet. Returns cited EvidenceResult.
- **Synthesis:** assemble RCA from complete state. Sonnet. No tool calls.

Hypothesis decides *what* to check. Evidence *executes* the check. Never merge these.

---

## Non-Negotiables
1. Every `RCAIncident` must have ≥1 `Evidence` row per hypothesis tested. Orchestrator validates before Synthesis runs. No evidence → retry (max 2), not surface.
2. `propose_replay` tool is ALWAYS gated behind human approval. Never auto-execute.
3. Confidence < 0.75 → `requires_human_review = True`. Surfaces separately in UI.
4. Every LLM call logs: model, version, token count, latency.
5. P1 incidents display first in UI regardless of processing order.
6. Pydantic on every agent boundary. Schema violation → retry with error context.
7. Mock tools must vary responses based on input — no hardcoded strings.

---

## Supabase Tables
`recon_runs`, `recon_rows` (embedding vector(1536)), `rca_incidents`, `rca_evidence`, `resolutions`, `recon_artifacts` (pgvector + HNSW), `rca_cache`, `deployment_events`, `page_views`, `demo_requests`

---

## Workflow Rules
- Read CLAUDE.md at the start of every session
- Read the relevant slice brief before implementing that slice
- `/plan` before any implementation — resolve ambiguities first
- Never break the non-negotiables above
- Always verify only one Python process on port 8000 before debugging: `netstat -ano | findstr :8000`
- Analytics adapter methods use date-range queries (`get_recon_rows_since`) — never `.in_()` on large ID lists (PostgREST URL limit).
- CSS vars don't resolve in Recharts tooltips — use hex colors. Use `contentStyle` + `itemStyle` + `labelStyle` props directly; custom `content` prop is an alternative but `contentStyle` is reliable when all colors are hex.
- Recharts Tooltip `formatter` return is `[displayValue, displayName]` — the second element replaces the dataKey label, not the segment name.
- Analytics endpoints have 5-min in-memory cache (`_analytics_cache` in main.py). Cache key format: `f"{endpoint}:{days}"`. TTL = 300s.
- Routing: `/` = Landing (public), `/upload` = Upload (app entry). Vercel SPA rewrite in `vercel.json` required for direct-URL navigation to work on Vercel deployment.
- Landing page is standalone (no Shell/TopBar wrapper) — has its own nav with brand mark and "Open app →" CTA.
- Access gate on `/upload`: checks `localStorage.recon_access === 'granted'`. Gate submits to `POST /api/v1/track/demo-request`. Bypass via code input checking `VITE_DEMO_CODE` env var (default `reconai2025`). Gate always shows success (fail-open) — backend insert is best-effort.
- Tracking endpoints (`/track/pageview`, `/track/demo-request`) always return 200 — Supabase errors are caught and sent to Sentry, never surfaced to the client.
- `demo_requests` table columns: `id, name, email, company, requested_at, code_sent, notes`. Insert payload uses these exact keys (not `full_name`/`work_email`/`submitted_at`).
- Resend email notification on demo request: gated on `RESEND_API_KEY` + `NOTIFY_EMAIL` env vars. No-op if either is unset. Render env vars needed.
- Sentry init in `main.py` gated on `SENTRY_DSN` env var — no-op if unset. `sentry_sdk.capture_exception()` used in synthesis and tracking endpoints.
- Synthesis graceful degradation: `anthropic.APIError`/`APIStatusError` (and `groq.APIError`) caught in `_call_llm` → returns degraded RCAOutput (confidence 0.0, requires_human_review True, final_hypothesis "API_UNAVAILABLE"). SSE stream never crashes.
- `HealthBanner` in App.tsx polls `GET /api/v1/health` every 60s — fixed top banner when down, auto-hides on recovery, dismissible.
- SSE error banner in LiveAnalysis: `sseError` state set when SSE closes before `done` fires; "Retry" button increments `retryKey` to reconnect.
- SSE connection guard: `sseOpenedRef` prevents duplicate connections on re-render. Reset in cleanup so retry works. `[runId, retryKey]` deps.
- `upsertIncident` in Zustand: skips update if incoming incident has no improvement (same/fewer hypotheses_tested, same/lower confidence, same status) over stored entry.
- `needsReviewCount` uses `requires_human_review && status !== 'complete'` — `IncidentStatus` is `'running' | 'complete' | 'needs_review' | 'escalated'`, no `'resolved'`.
- `get_run` endpoint returns `rows_scanned: len(rows)` (from `recon_rows` table) as authoritative row count — not `len(incidents)` which can be inflated by duplicates.
- `get_incident` endpoint returns `resolution` field (from `resolutions` table) if one exists. IncidentDetail shows read-only resolution view with Edit toggle when already resolved.
- Cache hit % in LiveAnalysis capped at `Math.min(100, ...)` — cacheHits accumulates across SSE reconnects but total is deduplicated.
- SSE `_stream_existing` only fires when `len(existing_incidents) >= len(rows)` — partial runs (some rows unprocessed) fall through to full analysis.
- `updateRunInHistory(runId, { status: 'complete' })` called in SSE `onDone` — keeps localStorage run history in sync without page reload.

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
| 2026-05-03 | 2 | Ingestion, Hypothesis, Evidence agents, LangGraph graph, /analyze endpoint | Evidence retry no-ops when tool_calls cleared |
| 2026-05-03 | 3 | splunk_sim.py, evidence.py parallel fan-out, H2 early-exit + H3 fan-out verified | Citations not RAG-grounded until Slice 4 |
| 2026-05-03 | 4 | RAG pipeline, 23 artifacts embedded, Synthesis Agent, full pipeline verified | RAG threshold too high; llm_model not persisted — fix in Slice 5 |
| 2026-05-03 | 5 | All 8 endpoints, SSE streaming, resolution→Supabase, cache (10 cache_hits verified) | llm_model stored inside rca_output JSONB to avoid ALTER TABLE schema cache issues |
| 2026-05-04 | 6 | All 4 views, SSE client, Zustand, Framer Motion, 0 TS errors. CORS fix: Vite proxy + relative API_URL | Evidence empty on sample runs — hypothesis branches missing for new discrepancy types |
| 2026-05-05 | debug | Fixed evidence/hypothesis bug (stale uvicorn), H4 dedup guard, evidence retry counter, cache path evidence re-save. All 5 discrepancy types verified. | — |
| 2026-05-06 | 8 | Analytics dashboard — 6 backend endpoints, analytics_seed.py, 6 frontend components, /analytics route. 0 TS errors. | `.in_()` on 2000 IDs hits PostgREST URL limit — use date-range queries for analytics. CSS vars fail in Recharts tooltips — use hex. |
| 2026-05-06 | polish | RootCauseDonut tooltip fixed (contentStyle hex colors, removed custom DonutTooltip). Skeleton loading states in Analytics (shimmer-pulse keyframe). 5-min in-memory cache on all 6 analytics endpoints. | — |
| 2026-05-06 | landing | Landing page at `/` (hero, problem, how-it-works, arch, built-by). Upload moved to `/upload`. vercel.json SPA rewrite added. 0 TS errors. | — |
| 2026-05-06 | tracking | Page view tracking (trackPageView + RouteTracker). Access gate on /upload with demo-request form + code bypass. POST /track/pageview + /track/demo-request endpoints. | demo_requests table columns must match exactly: name/email/company/requested_at |
| 2026-05-06 | infra | Sentry init (SENTRY_DSN gated). Synthesis graceful degradation on API errors. HealthBanner polls /health every 60s. SSE error banner + Retry button. resend>=2.0 for demo request notifications. | RESEND_API_KEY + NOTIFY_EMAIL needed in Render |
| 2026-05-06 | bugfix | SSE guard (sseOpenedRef), upsertIncident dedup, needsReviewCount fix, rows_scanned source of truth, resolution dedup in IncidentDetail, activity log "Resolution recorded", cache hit % capped at 100%, partial-run SSE fix, run status sync to localStorage. 0 TS errors. | IncidentStatus has no 'resolved' — use 'complete' |
