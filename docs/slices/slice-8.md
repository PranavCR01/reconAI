# Slice 8 — Analytics Dashboard

## Goal
Build a dedicated Analytics page showing historical trends across all reconciliation runs. Uses a hybrid data approach: synthetic historical data (30 days) seeded into Supabase + real runs from actual usage layered on top. The Deployment Correlation table is the headline differentiator.

## Demo-able When Complete
Navigate to Analytics from the nav bar → see 30 days of incident trends, deployment correlation spikes, root cause distribution donut, by-object stacked bars, AI accuracy trend — all populated with realistic data. Real runs from actual usage appear naturally alongside the historical backdrop.

## Design Reference
`docs/design/Analytics.html` — read fully before writing any component.

---

## Data Strategy: Hybrid A+B

### Synthetic Historical Seed (`backend/seed/analytics_seed.py`)
Generates and inserts into Supabase:

**25 synthetic ReconRun rows** — April 6 to May 4, 2026
- 1-2 runs per day, alternating PROD/UAT
- `status: complete`, realistic row counts (8-15 rows each)
- `sf_org_id: sf-fsc-prod-01`

**~400 synthetic RCAIncident rows** linked to those runs
- Distribution: NULL_DOWNSTREAM 32%, VALUE_MISMATCH 27%, STALE_VALUE 17%, MISSING_RECORD 14%, DUPLICATE_DOWNSTREAM 10%
- Root causes: FLS_STRIPPED 34%, CDC_EXCLUDED 22%, DATAWAVE_ERROR 18%, DELIVERY_GAP 14%, UNKNOWN 12%
- Objects: Account, Contact, FinancialAccount__c, KYC_Record__c, Address__c, Asset, Lead
- Confidence: 0.72-0.97 range, realistic distribution
- `total_tokens_used`: 1200-2100, `total_tool_calls`: 3-6, `latency_ms`: 8000-18000

**~240 synthetic Resolution rows** (~60% resolution rate)
- `ai_was_correct: true` for 85% — reflects improving accuracy over time
- `fix_type` distribution: fls_permission_grant 34%, dataweave_mapping_fix 22%, cdc_channel_config 18%, delivery_gap 14%, other 12%

**8 synthetic DeploymentEvent rows** (new table)
- `deploy_name`: e.g. "mule-acct-out@v3.4.1", "cdc-pipeline@v2.18.0", "sf-fsc sandbox refresh", "SEC-4432 profile PII tightening"
- `deployed_at`: timestamps spread across April 6 - May 4
- `deploy_type`: mulesoft | salesforce | db2 | infra
- `description`: one-line human-readable description
- 3 of 8 deployments have σ ≥ 3.0 incident spike in 24h window

**Idempotent:** Check count of recon_runs before seeding. Skip if > 10 runs already exist (preserves real data).

### New Supabase Table
```sql
CREATE TABLE deployment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deploy_name TEXT NOT NULL,
    deployed_at TIMESTAMPTZ NOT NULL,
    deploy_type TEXT NOT NULL,
    description TEXT,
    affected_org TEXT DEFAULT 'sf-fsc-prod-01',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## New Backend Endpoints (backend/main.py)

### GET /api/v1/analytics/summary?days=30&env=PROD
Returns the 6 stat cards:
```json
{
  "runs": { "count": 147, "delta_pct": 12 },
  "incidents_triaged": { "count": 1284, "delta_pct": 8 },
  "avg_resolution_rate": { "pct": 82, "delta_pt": 3 },
  "avg_confidence": { "pct": 88, "delta_pt": 2 },
  "top_root_cause": { "name": "FLS_STRIPPED", "pct": 34, "count": 437 },
  "deploy_correlations": { "count": 9, "total_deploys": 22 }
}
```

### GET /api/v1/analytics/incidents-over-time?days=30&env=PROD
Returns daily incident counts by discrepancy type:
```json
{
  "dates": ["2026-04-06", ...],
  "series": {
    "NULL_DOWNSTREAM": [12, 8, 15, ...],
    "VALUE_MISMATCH": [7, 5, 9, ...],
    ...
  },
  "deployments": [
    { "date": "2026-04-11", "name": "mule-platform@v6.2.0" },
    ...
  ]
}
```

### GET /api/v1/analytics/by-object?days=30&env=PROD
Returns per-object incident counts by severity:
```json
[
  { "object": "Account", "p1": 14, "p2": 86, "p3": 122, "total": 222 },
  ...
]
```

### GET /api/v1/analytics/root-cause-distribution?days=30&env=PROD
Returns root cause breakdown:
```json
[
  { "root_cause": "FLS_STRIPPED", "count": 437, "pct": 34 },
  ...
]
```

### GET /api/v1/analytics/deployment-correlation?days=30
Returns deployment correlation table:
```json
[
  {
    "deploy_name": "SEC-4432",
    "description": "profile · PII tightening",
    "deployed_at": "2026-04-29T03:11Z",
    "incidents_24h": 148,
    "sigma": 4.7,
    "most_affected_object": "Contact · Account",
    "suspected_root_cause": "FLS_STRIPPED",
    "status": "investigating"
  },
  ...
]
```
Sigma calculation: compare 24h post-deploy incident count against 14-day rolling mean and stddev. σ = (post_deploy_count - mean) / stddev. Status: investigating if σ ≥ 3.0 and no resolution linked, resolved if resolution exists.

### GET /api/v1/analytics/ai-accuracy?weeks=12
Returns weekly accuracy trend:
```json
{
  "weeks": ["w-12", "w-11", ...],
  "recall_at_1": [0.76, 0.78, ...],
  "recall_at_3": [0.90, 0.91, ...],
  "ai_was_correct": [0.75, 0.77, ...]
}
```

---

## New Frontend View (`src/views/Analytics.tsx`)
Reference: `docs/design/Analytics.html` — read fully first.

### Layout
- Full-width page, max-width 1400px
- Top: page title "Analytics" + subtitle + filter row (env dropdown, integrations dropdown, 7d/30d/90d toggle)
- Stats row: 6 cards with sparklines
- Main section: 2-column (70/30) — Incidents over time chart (left) + Root cause donut (right)
- Bottom section: 2-column (50/50) — By object bars (left) + AI accuracy trend (right)
- Full-width: Deployment correlation table

### Components to create:

**`src/components/analytics/StatCard.tsx`**
Props: label, value, delta, sparklineData[]
Renders the mini sparkline bar chart inline (CSS bars, not Recharts)

**`src/components/analytics/IncidentsOverTime.tsx`**
Recharts LineChart with:
- 5 colored lines (one per discrepancy type)
- ReferenceLine for each deployment event (dashed vertical)
- Custom tooltip showing all series values + deployment name if applicable
- Legend with counts

**`src/components/analytics/RootCauseDonut.tsx`**
Recharts PieChart (donut style):
- Center label: total count
- 5 segments with design colors
- Hover shows percentage + count
- Legend table to the right with % and count columns

**`src/components/analytics/ByObjectChart.tsx`**
CSS stacked bars (not Recharts — match design exactly):
- Each row: object name + stacked P1/P2/P3 bar + total count
- P1=red, P2=amber, P3=gray
- Sorted by total descending

**`src/components/analytics/AIAccuracyChart.tsx`**
Recharts LineChart:
- 3 lines: recall@1 (solid green), recall@3 (solid teal), ai_was_correct (dashed blue)
- Y axis: 70%-100%
- X axis: week labels (w-12 to w-0)
- Footer stats: recall@1 value, Δ vs 30d ago, total resolutions, overrides

**`src/components/analytics/DeploymentTable.tsx`**
Plain HTML table styled to match design:
- Columns: DEPLOYMENT, DATE, INCIDENTS +24H, MOST AFFECTED, SUSPECTED ROOT CAUSE, STATUS
- Color-coded sigma: red if σ ≥ 3.0, amber if σ 1.5-3.0, green if σ < 1.5
- Status badges: investigating (amber), resolved (green), rolled back (red)
- Footer: significance threshold note

---

## Routing Update
Add to `src/App.tsx`:
```
/analytics → Analytics
```

Update Topbar to add "Analytics" nav link between "Runs" and whatever comes next.
Remove "Settings" and "Docs" nav links (already flagged for removal).

---

## State Management
Analytics page uses local React state (useState + useEffect) — no Zustand needed.
All 5 API calls fire in parallel on mount using Promise.all.
Date range toggle (7d/30d/90d) refetches all endpoints with new `days` param.

---

## Seeding Instructions (run once before demo)
```bash
python -m backend.seed.analytics_seed
```
This populates 25 synthetic runs + 400 incidents + 240 resolutions + 8 deployment events.
Real runs sit on top automatically — the analytics queries don't distinguish.

Add to Render environment and run as a one-time job, or add to lifespan startup with the same idempotency check as fsc_incidents.py.

---

## Acceptance Criteria
- [ ] `python -m backend.seed.analytics_seed` runs without error, inserts data
- [ ] All 5 analytics endpoints return correct data
- [ ] Analytics page loads at /analytics with all 6 sections populated
- [ ] Incidents over time chart shows deployment vertical lines
- [ ] Deployment correlation table shows σ values and status badges
- [ ] Date range toggle (7d/30d/90d) refetches and updates all charts
- [ ] "Analytics" link in topbar navigates correctly
- [ ] Real runs from actual usage appear alongside synthetic data

## Risk Flag
The deployment correlation sigma calculation requires enough historical incident data to compute a meaningful rolling mean and stddev. With only synthetic data, ensure the seed generates realistic variance (not perfectly uniform) so sigma values are meaningful. Use random.gauss() for daily incident counts rather than uniform distribution.
