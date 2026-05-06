# Slice 8 Handoff — Analytics Dashboard

**Status: Nothing built yet. Plan complete, all ambiguities resolved.**

---

## Resolved Ambiguities

1. **slice-8.md location** — file is at `docs/slices/slice-8.md` (moved from project root)
2. **deployment_events schema** — see below
3. **Root cause donut** — Option A: use `discrepancy_type` from `recon_rows` as donut segments (5 known enum values, exact counts). Do NOT keyword-match `root_cause_summary` free text.
4. **AI Accuracy Trend** — Option A: return current recall@k (from `compute_recall_at_k`) as a flat line across all weeks; real weekly `ai_was_correct` from `resolutions` grouped by ISO week. No fabricated trend data.
5. **Date range filter** — re-fetch all 5 endpoints with updated `?days=` param on each toggle (7d/30d/90d). Do not slice client-side.

---

## deployment_events Schema

```sql
CREATE TABLE deployment_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deploy_name TEXT NOT NULL,
    deployed_at TIMESTAMPTZ NOT NULL,
    deploy_type TEXT NOT NULL,        -- mulesoft | salesforce | db2 | infra
    description TEXT,
    affected_org TEXT DEFAULT 'sf-fsc-prod-01',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```
Table already exists in Supabase. Do NOT run the DDL again.

---

## Complete File List

### CREATE (new files)

| File | Purpose |
|---|---|
| `backend/seed/analytics_seed.py` | Inserts 25 synthetic runs + ~375 incidents + ~225 resolutions + 8 deployment events. Idempotent: skip if > 10 runs already exist. |
| `frontend/src/views/Analytics.tsx` | Main analytics page. Fetches all 5 endpoints in parallel on mount. Refetches on days toggle. |
| `frontend/src/components/analytics/StatCard.tsx` | 6-up stat card with CSS sparkline bars (not Recharts). Props: label, value, unit, delta, deltaDir, sparkData[]. |
| `frontend/src/components/analytics/IncidentsOverTime.tsx` | Recharts LineChart, 5 series (one per DiscrepancyType), ReferenceLine per deployment, custom tooltip. |
| `frontend/src/components/analytics/RootCauseDonut.tsx` | Recharts PieChart (donut). Center label = total. Legend table right side. 5 segments = 5 discrepancy types. |
| `frontend/src/components/analytics/ByObjectChart.tsx` | Pure CSS stacked bars (not Recharts). Matches design obj-row exactly. P1/P2/P3 proportional widths. Sorted by total desc. |
| `frontend/src/components/analytics/AIAccuracyChart.tsx` | Recharts LineChart, 3 lines: recall@1 (green solid), recall@3 (teal solid), ai_was_correct (blue dashed). Y: 70-100%. Footer stat grid. |
| `frontend/src/components/analytics/DeploymentTable.tsx` | Plain HTML table. σ ≥ 3.0 = red delta, 1.5-3.0 = amber, < 1.5 = green. Status badges: investigating/resolved/rolled_back. |

### MODIFY (existing files)

| File | Change |
|---|---|
| `backend/main.py` | Add 5 analytics endpoints (see endpoint list below) |
| `backend/storage/supabase_adapter.py` | Add 6 analytics query methods (see method list below) |
| `frontend/src/App.tsx` | Add `/analytics` route + "Analytics" nav item between "Runs" and end |
| `frontend/src/lib/api.ts` | Add 5 analytics fetch functions |
| `frontend/src/types/index.ts` | Add 6 analytics response interfaces |

---

## Backend Endpoints to Add (main.py)

```
GET /api/v1/analytics/summary?days=30
GET /api/v1/analytics/incidents-over-time?days=30
GET /api/v1/analytics/by-object?days=30
GET /api/v1/analytics/root-cause-distribution?days=30
GET /api/v1/analytics/deployment-correlation?days=30
GET /api/v1/analytics/ai-accuracy?weeks=12
```

Sigma calculation for deployment-correlation:
- baseline = daily incident counts for 14 days before `deployed_at`
- `incidents_24h` = incidents with `created_at` in `[deployed_at, deployed_at + 24h]`
- σ = (incidents_24h − mean(baseline)) / stddev(baseline); 0 if stddev < 0.01
- status = "investigating" if σ ≥ 3.0 and no resolution exists, else "resolved"

AI accuracy endpoint uses `compute_recall_at_k` for current recall@k values (flat line)
plus real weekly `ai_was_correct` ratios from `resolutions` table grouped by week number.

Summary endpoint computes deltas by fetching full 2× period (e.g. 60d for 30d view)
and comparing current vs previous half in Python.

---

## Supabase Adapter Methods to Add

```python
async def get_incidents_since(self, since: datetime, limit=2000) -> list[dict]
    # SELECT id,recon_row_id,created_at,confidence,status,requires_human_review,
    #        total_tokens_used,total_tool_calls,latency_ms
    # FROM rca_incidents WHERE created_at >= since ORDER BY created_at LIMIT limit

async def get_recon_rows_by_ids(self, row_ids: list[str]) -> list[dict]
    # SELECT id,sf_object,sf_field,discrepancy_type,severity,run_id
    # FROM recon_rows WHERE id IN (row_ids)

async def get_resolutions_since(self, since: datetime) -> list[dict]
    # SELECT id,resolved_at,ai_was_correct,fix_type FROM resolutions WHERE resolved_at >= since

async def get_runs_since(self, since: datetime) -> list[dict]
    # SELECT id,created_at,status FROM recon_runs WHERE created_at >= since

async def get_total_runs_count(self) -> int
    # SELECT COUNT(*) FROM recon_runs  (used for idempotency check in seed)

async def get_deployment_events_since(self, since: datetime) -> list[dict]
    # SELECT * FROM deployment_events WHERE deployed_at >= since ORDER BY deployed_at DESC

async def get_all_deployment_events(self) -> list[dict]
    # SELECT * FROM deployment_events ORDER BY deployed_at DESC
    # (used by deployment-correlation to get full window for sigma baseline)
```

---

## TypeScript Types to Add (types/index.ts)

```typescript
export interface AnalyticsSummary {
  runs: { count: number; delta_pct: number }
  incidents_triaged: { count: number; delta_pct: number }
  avg_resolution_rate: { pct: number; delta_pt: number }
  avg_confidence: { pct: number; delta_pt: number }
  top_root_cause: { name: string; pct: number; count: number }
  deploy_correlations: { count: number; total_deploys: number }
}

export interface IncidentsOverTimeResponse {
  dates: string[]
  series: Record<string, number[]>   // keyed by DiscrepancyType value
  deployments: { date: string; name: string }[]
}

export interface ByObjectRow {
  object: string
  p1: number
  p2: number
  p3: number
  total: number
}

export interface RootCauseRow {
  root_cause: string   // discrepancy_type value (Option A)
  count: number
  pct: number
}

export interface AIAccuracyResponse {
  weeks: string[]         // ["w-11", "w-10", ..., "w-0"]
  recall_at_1: number[]   // flat line from current compute_recall_at_k
  recall_at_3: number[]   // flat line
  ai_was_correct: number[] // real weekly values from resolutions
  summary: {
    recall_at_1: number
    recall_at_3: number
    resolutions: number
    overrides: number    // resolutions where ai_was_correct = false
  }
}

export interface DeploymentCorrelation {
  deploy_name: string
  description: string | null
  deployed_at: string
  deploy_type: string
  incidents_24h: number
  sigma: number
  most_affected_object: string | null
  suspected_root_cause: string | null
  status: 'investigating' | 'resolved' | 'normal'
}
```

---

## Seed Script Design (analytics_seed.py)

```
Idempotency: query COUNT(*) FROM recon_runs. If > 10, print skip message and exit.

Data distributions:
  DiscrepancyType: NULL_DOWNSTREAM 32%, VALUE_MISMATCH 27%, STALE_VALUE 17%,
                   MISSING_RECORD 14%, DUPLICATE_DOWNSTREAM 10%
  Severity:        P1 10%, P2 40%, P3 50%
  SF Objects:      Account, Contact, FinancialAccount__c, KYC_Record__c,
                   Address__c, Asset, Lead (uniform)
  Confidence:      gauss(mu=0.85, sigma=0.06), clipped to [0.72, 0.97]
  total_tokens_used: randint(1200, 2100)
  total_tool_calls:  randint(3, 6)
  latency_ms:        randint(8000, 18000)
  ai_was_correct:    True 85%, False 15%

Timeline: April 6 – May 4, 2026 (29 days)
  Normal days:  1 run × 8-14 rows = ~11 incidents/day (use gauss for row count)
  Spike days:   Apr 22, Apr 26, Apr 29 → 2 runs each, 20-28 rows each
                → ~40-50 incidents/day (ensures σ ≥ 3.0 for those deployments)
  Total runs: ~25, total incidents: ~375, total resolutions: ~225

Deployment events (8 rows):
  1. Apr 08 mulesoft  mule-acct-out@v3.3.0          no spike
  2. Apr 11 mulesoft  cdc-pipeline@v2.18.0           no spike
  3. Apr 15 db2       db2-DDL-2026-04-15             no spike
  4. Apr 19 mulesoft  mule-contact@v4.1.2            no spike
  5. Apr 22 db2       db2-DDL-2026-04-22             SPIKE (σ ≈ 3.8)
  6. Apr 26 mulesoft  mule-acct-out@v3.4.1           SPIKE (σ ≈ 3.1)
  7. Apr 29 salesforce SEC-4432                      SPIKE (σ ≈ 4.7, largest)
  8. May 02 infra     cloudhub-runtime@v4.0.3        no spike

Insertion order (respects FKs):
  recon_runs → recon_rows → rca_incidents → resolutions → deployment_events

Use random.Random(42) for reproducibility.
Batch inserts: chunk list[dict] into 50-row batches to avoid request size limits.
Use synchronous supabase-py (no async) — seed script only.
```

---

## Chart Color Constants (for Recharts — use hex, not CSS vars)

```typescript
// Discrepancy type colors (approx. from CSS category palette)
const DISC_COLORS: Record<string, string> = {
  NULL_DOWNSTREAM:       '#e06040',  // --c-null  oklch(0.70 0.16 25)
  VALUE_MISMATCH:        '#c8a030',  // --c-mismatch oklch(0.78 0.13 75)
  STALE_VALUE:           '#8060d8',  // --c-stale oklch(0.72 0.13 295)
  MISSING_RECORD:        '#4090d8',  // --c-missing oklch(0.72 0.13 220)
  DUPLICATE_DOWNSTREAM:  '#30b0a8',  // --c-dup oklch(0.78 0.13 195)
}

// Severity colors
const SEV_COLORS = { P1: '#e06040', P2: '#c8a030', P3: '#7070a0' }

// Accuracy line colors
const ACC_COLORS = {
  recall_at_1:    '#40b875',  // --ok
  recall_at_3:    '#30b0a8',  // --teal
  ai_was_correct: '#4090d8',  // --info (dashed)
}
```

---

## Build Order for Fresh Session

1. Read `CLAUDE.md` and `docs/slices/slice-8.md`
2. Read `docs/design/Analytics.html` (full — critical for layout)
3. Read `backend/main.py`, `backend/storage/supabase_adapter.py`, `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `frontend/src/types/index.ts` (existing patterns)
4. **Build in this order:**
   a. `frontend/src/types/index.ts` — add 6 analytics interfaces
   b. `backend/seed/analytics_seed.py` — full seed script (synchronous supabase-py)
   c. `backend/storage/supabase_adapter.py` — add 7 query methods
   d. `backend/main.py` — add 6 analytics endpoints
   e. `frontend/src/lib/api.ts` — add 5 fetch functions
   f. `frontend/src/components/analytics/StatCard.tsx`
   g. `frontend/src/components/analytics/ByObjectChart.tsx`
   h. `frontend/src/components/analytics/DeploymentTable.tsx`
   i. `frontend/src/components/analytics/RootCauseDonut.tsx`
   j. `frontend/src/components/analytics/AIAccuracyChart.tsx`
   k. `frontend/src/components/analytics/IncidentsOverTime.tsx`
   l. `frontend/src/views/Analytics.tsx`
   m. `frontend/src/App.tsx` — add route + nav item
5. Run `npx tsc --noEmit` → 0 errors
6. Run `python -m backend.seed.analytics_seed` → verify inserts
7. Commit and push

---

## Notes for Fresh Session

- `recharts@2.12.7` is already installed — no `npm install` needed.
- Recharts stroke/fill props are SVG attributes; use hex colors, not CSS custom properties.
- The `ByObjectChart` and `StatCard` use plain CSS divs — do NOT reach for Recharts.
- Analytics page uses `useState` + `useEffect` + `Promise.all` only. No Zustand.
- The seed is idempotent — safe to run multiple times (skips if > 10 runs exist).
- Do not add `embedding` to seed recon_rows inserts — that column is nullable and populated separately.
- Settings and Docs nav links are already removed (done in previous session).
- `deployment_events` table already exists in Supabase — do not run DDL.
