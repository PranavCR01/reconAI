# ReconAI — Full Project Context

Use this document to onboard a new Claude session to the complete state of this project.
Everything here is current as of 2026-05-08.

---

## What This Is

AI-powered Salesforce FSC integration reconciliation and root cause analysis tool.
Replaces a manual Excel decision tree used by Recon teams to diagnose data discrepancies
between Salesforce FSC and downstream systems (DB2, Snowflake).

**Pitch:** "Datadog Bits AI SRE for Salesforce integration pipelines, with the Excel decision
tree encoded as a deterministic hypothesis graph."

**Audience:** Deloitte colleagues and Salesforce engineers. Every architectural choice must
be defensible.

**Live demo:** https://recon-ai-iota.vercel.app
**GitHub:** https://github.com/PranavCR01/reconAI

---

## Tech Stack

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph |
| Output validation | Pydantic v2 |
| LLM — classification | Claude Haiku |
| LLM — reasoning | Claude Sonnet |
| LLM — comparison | Groq Llama 3.3 70B |
| Embedding | OpenAI text-embedding-3-small (1536 dims) |
| Vector + structured store | Supabase (pgvector + Postgres) |
| Backend | FastAPI on Render |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui (New York) |
| State management | Zustand |
| Charts | Recharts |
| Animation | Framer Motion |
| Streaming | Native SSE (EventSource, no library) |

---

## Repo Structure

```
reconAI/
├── backend/
│   ├── agents/         ingestion.py, hypothesis.py, evidence.py, synthesis.py
│   ├── tools/          splunk_sim.py, salesforce_sim.py, db2_sim.py, rag_tools.py
│   ├── graph/          recon_graph.py (LangGraph state machine)
│   ├── models/         state.py, entities.py, outputs.py
│   ├── storage/        adapter.py, supabase_adapter.py, sf_adapter.py
│   ├── cache/          rca_cache.py
│   ├── seed/           fsc_incidents.py, analytics_seed.py
│   ├── scripts/        clear_cache.py
│   ├── config.py       AgentConfig — LLM routing per agent
│   └── main.py         FastAPI app + all endpoints
├── frontend/src/
│   ├── views/          Landing, Upload, LiveAnalysis, IncidentDetail, RunSummary,
│   │                   Analytics, Benchmark
│   ├── components/
│   │   ├── analytics/  StatCard, IncidentsOverTime, RootCauseDonut, ByObjectChart,
│   │   │               AIAccuracyChart, DeploymentTable
│   │   ├── layout/     Shell, TopBar
│   │   └── ui/         Badge, BrandMark, Button, Card, ConfidenceBar, EvidenceChip,
│   │                   HypothesisPills, Panel, ProgressBar, SegmentedControl,
│   │                   Spinner, StatusPill, Tag, Tooltip
│   ├── store/          reconStore.ts (Zustand)
│   ├── lib/            api.ts, sse.ts, format.ts, utils.ts
│   ├── types/          index.ts
│   ├── data/           benchmark_data.json
│   └── App.tsx
├── data/
│   ├── sample_fsc_recon.csv
│   ├── benchmark_incidents.csv
│   ├── benchmark_incidents_fixed.csv
│   └── benchmark_ground_truth.json
├── docs/
│   ├── design/         Analytics.html, Home.html, Live Analysis.html,
│   │                   Incident Detail.html, Run Summary.html
│   ├── slices/         slice-8.md, slice-8-handoff.md
│   └── slides/         linkedin_slides.html
├── scripts/
│   ├── health_check.py   40-point E2E health check
│   └── health_report.md
├── vercel.json           SPA rewrite (all paths → /index.html)
├── README.md
└── requirements.txt
```

---

## Four Agents — Boundaries Are Hard

| Agent | Model | Tool calls | Responsibility |
|---|---|---|---|
| Ingestion | Haiku | None | Classify discrepancy type and severity |
| Hypothesis | Sonnet | None | Walk graph, decide next hypothesis to test |
| Evidence | Sonnet | All of them | Execute tool calls, return cited EvidenceResult |
| Synthesis | Sonnet | None | Assemble final RCA from complete state |

**Critical rule:** Hypothesis decides *what* to check. Evidence *executes* the check.
These two agents must never be merged.

---

## Hypothesis Graph (H1 → H5)

Each discrepancy enters at H1. The graph terminates at the first confirmed hypothesis
(early termination). A NULL_DOWNSTREAM incident confirmed at H3a never runs H3b, H3c, H4, H5.

**H1 — DB2 History Check**
Query downstream DB2 field history over 30 days. Determines if discrepancy is new or
recurring. Recurring with no DB2 writes → delivery gap.

**H2 — Splunk Triage**
Query CDC pipeline logs. Confirms whether events fired and were dropped, or never fired.
Early termination if delivery gap confirmed here.

**H3a — FLS Check**
Query Salesforce FieldPermissions for integration user on the specific object+field.
Most common root cause for NULL_DOWNSTREAM. Runs before CDC config check.

**H3b — CDC Channel Configuration**
Check whether field is in ChangeEvent tracked field list. Long text fields and certain
custom fields are excluded from CDC payloads by platform default.

**H3c — Apex Trigger Logic**
Check for conditional publish suppression in Apex triggers. Common pattern: trigger skips
CDC event when field transitions from populated → null.

**H4 — DataWeave Transform Deep Dive**
Analyze MuleSoft DataWeave layer for picklist label/code mismatches, timezone errors,
null-suppression conditionals.

**H5 — RAG Fallback**
If no deterministic hypothesis confirms, retrieve top-5 similar past incidents from
pgvector store (cosine similarity, 1536 dims). Claude Sonnet synthesizes from context.

---

## RAG Pipeline

- Embeddings: OpenAI text-embedding-3-small, 1536 dims
- Store: `recon_artifacts` table in Supabase with pgvector HNSW index
- Seed: 23 FSC artifacts covering known failure patterns (backend/seed/fsc_incidents.py)
- Retrieval: Postgres pre-filter by discrepancy_type → ANN search → LLM reranker
- Temporal weighting: artifacts from last 6 hours treated as ground truth
- Memory loop: confirmed resolutions are embedded and written back to artifact store

---

## Supabase Tables

| Table | Purpose |
|---|---|
| recon_runs | One reconciliation execution |
| recon_rows | One CSV row / discrepancy (has embedding vector(1536)) |
| rca_incidents | One RCA result per discrepancy |
| rca_evidence | Cited artifacts per incident (anti-hallucination enforcement) |
| resolutions | Human-confirmed fixes; feeds RAG memory loop |
| recon_artifacts | pgvector HNSW store for RAG retrieval |
| rca_cache | 24hr TTL cache keyed on field+value combination |
| deployment_events | Analytics: deployment timeline for correlation |
| page_views | Tracking |
| demo_requests | Gate: name, email, company, requested_at, code_sent, notes |

---

## Backend — All Endpoints (backend/main.py)

### Core

```
POST   /api/v1/runs                       create run, embed rows, return run_id
GET    /api/v1/runs/{run_id}              get run status + rows_scanned (len(recon_rows), NOT len(incidents))
GET    /api/v1/runs/{run_id}/stream       SSE stream (see SSE section)
GET    /api/v1/incidents/{incident_id}    get incident + resolution if exists
POST   /api/v1/incidents/{incident_id}/resolve   save resolution
GET    /api/v1/recall                     recall@k metrics (1hr TTL cache, cold start 20s+)
GET    /api/v1/health                     health check (polled by HealthBanner every 60s)
```

### Analytics (all have 5-min in-memory cache, key = f"{endpoint}:{days}")

```
GET    /api/v1/analytics/summary?days=30
GET    /api/v1/analytics/incidents-over-time?days=30
GET    /api/v1/analytics/by-object?days=30
GET    /api/v1/analytics/root-cause-distribution?days=30
GET    /api/v1/analytics/deployment-correlation?days=30
GET    /api/v1/analytics/ai-accuracy?weeks=12
```

### Tracking (always return 200, Supabase errors go to Sentry only)

```
POST   /api/v1/track/pageview
POST   /api/v1/track/demo-request
```

---

## SSE Streaming (critical implementation details)

The SSE stream is at `GET /api/v1/runs/{run_id}/stream?bypass_cache=false`.

**Two code paths:**
- `_stream_existing`: fires when `not bypass_cache and len(existing_incidents) >= len(rows)`. Streams cached results.
- `_generate`: fires for fresh LangGraph runs.

**Critical rule:** `await` and `yield` must be INSIDE the async generator body. A `yield` in the outer endpoint scope turns the endpoint into a generator itself, making `return StreamingResponse(...)` a SyntaxError.

**SSE event format:**
```
id: {incident_id}
event: incident
data: {json}

id: done
event: done
data: {"run_id": "...", "total": N}
```

**Reconnect:** Uses `Last-Event-ID` header. Backend resumes from that incident_id on reconnect.

**`update_run_status`** is called inside both `_generate` and `_stream_existing` before the `done` yield — not outside.

**Frontend (`sse.ts`):** Uses `getStreamUrl` with `URLSearchParams` to build the URL (handles `bypass_cache=true` flag properly).

**Cache hit % cap:** `Math.min(100, ...)` — cacheHits can accumulate across reconnects but denominator is deduplicated.

**`_stream_existing` condition:** `not bypass_cache and len(existing_incidents) >= len(rows)`. Partial runs fall through to full re-analysis.

---

## Zustand Store (frontend/src/store/reconStore.ts)

Key state: `runs`, `currentRunId`, `incidents` (Map keyed by incident_id), `runHistory` (localStorage).

**`upsertIncident`:** Skips update if incoming incident has no improvement over stored entry — same/fewer hypotheses_tested, same/lower confidence, same status. This prevents stale SSE events from overwriting better data on reconnect.

**`needsReviewCount`:** `requires_human_review && status !== 'complete'`.
`IncidentStatus` values: `'running' | 'complete' | 'needs_review' | 'escalated'`. There is NO `'resolved'` status.

**`updateRunInHistory(runId, { status: 'complete' })`** called in SSE `onDone` to keep localStorage run history in sync without page reload.

---

## Frontend Routes (App.tsx)

```
/              Landing (public, standalone nav, no Shell wrapper needed)
/upload        Upload (app entry, access-gated)
/runs/:runId   LiveAnalysis (SSE streaming)
/runs/:runId/summary          RunSummary
/runs/:runId/incidents/:id    IncidentDetail
/analytics     Analytics dashboard
/benchmark     Benchmark results
*              → redirect to /
```

**SPA rewrite:** `vercel.json` rewrites all paths to `/index.html`. Required for direct-URL navigation on Vercel.

---

## Views — Key Details

### Landing (/)
- Standalone page with its own nav — brand mark + "Open app →" CTA + scroll indicator
- Does NOT use Shell/TopBar
- Has dot-grid background via CSS radial-gradient
- Hero CTAs: "Run your first recon →" (primary), "View analytics →" (ghost), "Benchmark results →" (ghost)
- Sections: Hero, The Problem, How It Works, Architecture, Built By, Footer

### Upload (/upload)
- Access gate: checks `localStorage.recon_access === 'granted'`
- Gate submits to `POST /api/v1/track/demo-request`
- Bypass: code input checks `VITE_DEMO_CODE` env var (default `reconai2025`)
- Gate is fail-open — always shows success, backend insert is best-effort
- After gate: CSV upload → POST /runs → navigate to /runs/:runId

### LiveAnalysis (/runs/:runId)
- SSE connection via `sse.ts`, retries on connection drop
- `sseError` state set when SSE closes before `done` fires; "Retry" button visible
- P1 incidents always first (sort by severity before render)
- LIVE dot in TopBar
- Cache hit % display (capped at 100%)
- Breadcrumb navigates to /upload

### IncidentDetail (/runs/:runId/incidents/:id)
- Shows full hypothesis chain, all evidence with citations
- Resolution workflow: shows read-only view with Edit toggle if resolution exists
- Edit pre-populates form fields; Cancel button discards changes
- `fix_applied` field on resolution is optional

### Analytics (/analytics)
- All 5 API calls fire in parallel on mount via Promise.all
- Days toggle (7d/30d/90d) re-fetches all endpoints with new `?days=` param (no client-side slicing)
- Pure local state (useState + useEffect), no Zustand
- ByObjectChart and StatCard use CSS bars, not Recharts
- Recharts components use hex colors (not CSS vars — they don't resolve inside SVG)

### Benchmark (/benchmark)
- Standalone page with own sticky nav (← Home + Open app →)
- All data from `frontend/src/data/benchmark_data.json`
- 4 Recharts charts: 3-way accuracy (grouped bars), latency (per-config bars),
  cost (per-config bars), human review rate (per-config bars), failure patterns (colored bars)
- 5 written sections: Why / Methodology / Key Findings / Failure Patterns / Recommendation
- Key Findings: `borderLeft: '2px solid var(--info)'`, paddingLeft 12px, no numbers

---

## Design System

The app uses a dark design system. CSS variables defined in `frontend/src/index.css`.

**Key colour tokens:**
```css
--bg:    oklch(0.16 0.006 250)   /* #0f1117 approx */
--bg-1:  oklch(0.19 0.006 250)
--bg-2:  oklch(0.22 0.007 250)
--bg-3:  oklch(0.26 0.008 250)
--line:  oklch(0.30 0.008 250)
--fg:    oklch(0.96 0.005 250)
--fg-1:  oklch(0.82 0.006 250)
--fg-2:  oklch(0.66 0.008 250)
--fg-3:  oklch(0.50 0.008 250)
--ok:    oklch(0.74 0.16 155)    /* green */
--info:  oklch(0.74 0.12 220)    /* blue */
--warn:  oklch(0.78 0.15 75)     /* amber */
--err:   oklch(0.65 0.20 25)     /* red */
```

**Fonts:** Inter (body), JetBrains Mono (monospace). Loaded from Google Fonts.

**shadcn/ui:** New York style. Components in `frontend/src/components/ui/`.

---

## Critical Implementation Rules (learned from bugs)

### Recharts
- CSS vars do NOT resolve inside Recharts SVG/canvas. Use hex colors everywhere.
- Tooltip: use `contentStyle` + `itemStyle` + `labelStyle` props with hex values.
- `formatter` return is `[displayValue, displayName]` — second element replaces the dataKey label.
- `Tooltip formatter` type: `(value: number | string, name: string) => [string, string]`

### CSS
- `gap: 10` in a `<style>` block is invalid CSS — must be `gap: 10px`. Use React inline styles (`gap: 10` → React converts to `gap: 10px`) or explicit `gap: '10px'` strings.

### Analytics endpoints
- Use date-range queries (`get_recon_rows_since`) — never `.in_()` on large ID lists (PostgREST URL limit exceeded).
- Analytics cache key format: `f"{endpoint}:{days}"`, TTL 300s.

### SSE
- `await`/`yield` must be inside the async generator body. A yield in the outer endpoint scope causes a SyntaxError when `return StreamingResponse(...)` is encountered.

### Supabase
- `demo_requests` columns: `id, name, email, company, requested_at, code_sent, notes`
  (NOT `full_name`/`work_email`/`submitted_at`)
- `deployment_events` table already exists — do not run DDL.
- HNSW index on `recon_artifacts` — do not drop/recreate.

### Backend
- `get_run` returns `rows_scanned: len(rows)` (from `recon_rows` table) — NOT `len(incidents)` which inflates on duplicates.
- `get_incident` returns `resolution` field from `resolutions` table if it exists.
- `/recall` cold start takes 20s+. Uses `_recall_cache` dict with 1hr TTL. Always serve cached.
- Synthesis graceful degradation: `anthropic.APIError` / `groq.APIError` caught in `_call_llm` → returns degraded RCAOutput (confidence 0.0, `requires_human_review=True`, `final_hypothesis="API_UNAVAILABLE"`). SSE stream never crashes.

### Env var gates
- Sentry: gated on `SENTRY_DSN` — no-op if unset.
- Resend email: gated on `RESEND_API_KEY` + `NOTIFY_EMAIL` — no-op if either unset.
- Demo code: `VITE_DEMO_CODE` (default `reconai2025`).

### Non-negotiables (never violate)
1. Every `RCAIncident` must have ≥1 `rca_evidence` row per hypothesis tested. No evidence → retry (max 2), never surface.
2. `propose_replay` is ALWAYS gated behind human approval. Never auto-execute.
3. Confidence < 0.75 → `requires_human_review = True`.
4. Every LLM call logs: model, version, token count, latency.
5. P1 incidents display first regardless of SSE arrival order.
6. Pydantic on every agent boundary. Schema violation → retry with error context.
7. Mock tools must vary responses based on input — no static returns.

---

## Analytics Dashboard (Slice 8)

### Seed script
```bash
python -m backend.seed.analytics_seed
```
Inserts 25 synthetic runs + ~375 incidents + ~225 resolutions + 8 deployment events
spanning April 6 – May 4, 2026. Idempotent: skips if >10 runs already exist.

### Deployment correlation sigma
- Baseline: daily incident counts for 14 days before `deployed_at`
- `incidents_24h`: incidents in `[deployed_at, deployed_at + 24h]`
- σ = (incidents_24h − mean) / stddev; 0 if stddev < 0.01
- Status: "investigating" if σ ≥ 3.0 and no resolution, else "resolved"

### Spike deployments (seeded)
- Apr 22: db2-DDL-2026-04-22 → σ ≈ 3.8
- Apr 26: mule-acct-out@v3.4.1 → σ ≈ 3.1
- Apr 29: SEC-4432 (profile PII tightening) → σ ≈ 4.7 (largest)

### Chart colours (hex — for Recharts)
```
NULL_DOWNSTREAM:      #e06040
VALUE_MISMATCH:       #c8a030
STALE_VALUE:          #8060d8
MISSING_RECORD:       #4090d8
DUPLICATE_DOWNSTREAM: #30b0a8
P1: #e06040  P2: #c8a030  P3: #7070a0
recall@1: #40b875  recall@3: #30b0a8  ai_was_correct: #4090d8
```

---

## Benchmark Results

50 synthetic FSC incidents, 10 objects, 5 discrepancy types.
Ground truth: manually labeled. Run date: May 7, 2026.

| Config | Accuracy | Human Review | Avg Confidence | Latency | Cost/incident |
|---|---|---|---|---|---|
| Claude Sonnet | 70% | 56% | 80% | 12.5s | $0.006 |
| Groq Llama 3.3 70B | 62% | 50% | 85% | 1.4s | $0.001 |
| Hybrid (recommended) | 67% | 65% | 81% | ~9s | $0.004 |

**Failure patterns (all three configs):**

| Pattern | Incidents |
|---|---|
| H2/H3a Confusion — Splunk terminates before FLS on complex NULL_DOWNSTREAM | 5 |
| STALE_VALUE RAG Fallback — HSV branch exhausts, falls to H5 instead of H2 | 3 |
| CDC Exclusion Fallback — H3b fails to confirm, falls to H5 | 3 |

These are graph-level issues, not model-specific. Improvements are model-agnostic.

**Recommendation:** Hybrid default (Groq classifies, Sonnet synthesizes).
Use Sonnet-only for P1 incidents and SCHEMA_DRIFT type.
Use Groq-only for high-volume P3 NULL_DOWNSTREAM at scale.

---

## Infrastructure

**Backend (Render):**
- FastAPI app via `uvicorn backend.main:app`
- Required env vars: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`,
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- Optional: `SENTRY_DSN`, `RESEND_API_KEY`, `NOTIFY_EMAIL`

**Frontend (Vercel):**
- Vite build, SPA rewrite in `vercel.json`
- Required: `VITE_API_URL` pointing to Render backend
- Optional: `VITE_DEMO_CODE` (default `reconai2025`)

**Health monitoring:**
- `GET /api/v1/health` polled by HealthBanner every 60s
- Fixed top banner when down, auto-hides on recovery, dismissible
- `python scripts/health_check.py` runs 40 E2E checks

---

## Local Development

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# Check port: netstat -ano | findstr :8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
# Set VITE_API_URL=http://localhost:8000/api/v1 in frontend/.env.local

# Seed analytics (once)
python -m backend.seed.analytics_seed

# Health check
python scripts/health_check.py
```

---

## Session Log

| Date | What shipped |
|---|---|
| Pre-project | Architecture, ADR, CLAUDE.md |
| 2026-05-02 | Slice 1: models, storage adapter, FastAPI skeleton, sample CSV |
| 2026-05-03 | Slices 2–5: all 4 agents, LangGraph, RAG, all 8 endpoints, SSE streaming, RCA cache |
| 2026-05-04 | Slice 6: all 4 views, SSE client, Zustand, Framer Motion, CORS fix |
| 2026-05-05 | Debug: evidence/hypothesis bug, H4 dedup guard, evidence retry. All 5 discrepancy types verified. |
| 2026-05-06 | Slice 8: analytics dashboard (6 endpoints, 6 components, analytics_seed.py) |
| 2026-05-06 | Landing page, vercel.json SPA rewrite, tracking endpoints, access gate, Sentry, HealthBanner |
| 2026-05-06 | Bugfix: SSE dedup, upsertIncident, needsReviewCount, rows_scanned, resolution UX, cache hit % cap |
| 2026-05-07 | SSE event IDs, Last-Event-ID reconnect, fix_applied optional on resolutions |
| 2026-05-07 | UI: LIVE dot in TopBar, P1 count fix, Edit resolution pre-populate + Cancel, Upload showAll button |
| 2026-05-07 | Backend: update_run_status in SSE generators. Hotfix: await/yield SyntaxError. |
| 2026-05-07 | Tooling: health_check.py (40 checks), /recall 1hr TTL cache, bypass_cache param |
| 2026-05-08 | Benchmark page: benchmark_data.json, Benchmark.tsx, Landing arrow fix + benchmark button, /benchmark route |
| 2026-05-08 | Benchmark UI fixes: Key Findings layout (left-border accent style), meta row cleanup |
| 2026-05-08 | docs/slides/linkedin_slides.html (5 slides, 1200×675, dark design, CSS only) |
| 2026-05-08 | README.md (325 lines: badges, architecture, benchmark table, local dev, directory tree) |

---

## Known Issues / Risk Flags

- Splunk simulator realism is the highest demo risk — responses are probabilistic, not sourced from a real Splunk instance.
- `llm_model` is stored inside the `rca_output` JSONB column (not as a top-level column).
- Evidence retry no-ops when `tool_calls` are cleared — mitigation is the max-2-retry limit.
- `/recall` cold start takes 20s+; first caller after deploy will see slow response. Always cached after that.
- `resolutions` table needs a UNIQUE constraint on `incident_id` and a `fix_verified` column (flagged, not yet added).
- Analytics deployment correlation sigma requires sufficient historical variance — seed uses `random.gauss()` not uniform distribution.
- CSS vars do not resolve inside Recharts SVG — all chart colors must be hex literals.
- `gap: 10` without `px` is invalid in `<style>` blocks — use React inline styles or `gap: '10px'`.

---

## Workflow Rules for New Sessions

1. Read this document and CLAUDE.md before implementing anything.
2. Read the relevant slice brief before implementing that slice.
3. Plan before any implementation — resolve ambiguities first.
4. Never break the seven non-negotiables listed above.
5. Before debugging port issues: `netstat -ano | findstr :8000`
6. Analytics queries must use date-range (`get_recon_rows_since`) — never `.in_()` on large ID lists.
7. Recharts: hex colors only, `contentStyle`/`itemStyle`/`labelStyle` on tooltips.
8. `formatter` return is `[displayValue, displayName]`.
9. `IncidentStatus` has no `'resolved'` — use `'complete'`.
10. `rows_scanned` comes from `len(recon_rows)`, not `len(incidents)`.
11. `await`/`yield` must be inside the async generator body in SSE endpoints.
12. `propose_replay` is always human-gated — never auto-execute under any circumstances.
