# Slice 6 — Frontend (All 4 Views)

## Goal
Build the complete React frontend matching the Claude Design HTML mockups exactly. The design files are the source of truth — do not deviate from the visual system they establish.

## Design Reference Files
Four HTML files in `docs/design/` are the authoritative design reference:
- `docs/design/Home.html` → Upload view
- `docs/design/Live_Analysis.html` → Live Analysis view
- `docs/design/Incident_Detail.html` → Incident Detail view
- `docs/design/Run_Summary.html` → Run Summary view

**Read every design file before writing any component.** Extract CSS variables, component patterns, and layout structure directly from them.

---

## Design System (extracted from Claude Design files)

### Fonts
```
Inter (400, 500, 600, 700) → body, labels, UI
JetBrains Mono (400, 500, 600) → record IDs, field names, evidence sources, code values
```
Load via Google Fonts in index.html.

### Color tokens (CSS variables — copy exactly)
```css
--bg: oklch(0.16 0.006 250);
--bg-1: oklch(0.19 0.006 250);
--bg-2: oklch(0.22 0.007 250);
--bg-3: oklch(0.26 0.008 250);
--line: oklch(0.30 0.008 250);
--line-soft: oklch(0.25 0.007 250);
--fg: oklch(0.96 0.005 250);
--fg-1: oklch(0.82 0.006 250);
--fg-2: oklch(0.66 0.008 250);
--fg-3: oklch(0.50 0.008 250);

--p1: oklch(0.65 0.20 25);
--p1-bg: oklch(0.30 0.09 25);
--p2: oklch(0.78 0.15 75);
--p2-bg: oklch(0.32 0.07 75);
--p3: oklch(0.60 0.012 250);
--p3-bg: oklch(0.28 0.008 250);

--ok: oklch(0.74 0.16 155);
--ok-bg: oklch(0.30 0.07 155);
--warn: oklch(0.78 0.15 75);
--info: oklch(0.74 0.12 220);
--info-bg: oklch(0.28 0.06 220);
--violet: oklch(0.72 0.14 295);

--mono: 'JetBrains Mono', ui-monospace, monospace;
--sans: 'Inter', system-ui, sans-serif;
```

### Key component patterns
- **Incident cards:** `background: var(--bg-2)`, `border: 1px solid var(--line)`, left border 2px colored by severity, `border-radius: 6px`
- **Hypothesis pills:** small monospace badges, colored by state (done=green/ok, active=amber/warn, pending=fg-3)
- **Evidence chips:** `font-family: var(--mono)`, prefixed with `sf-fls://`, `splunk://`, `db2://`
- **SF→DB2 field mapping:** `[SF badge] ObjectName . FieldName → [DB2 badge] TABLE.COLUMN` in monospace
- **Stats row:** 6-column grid separated by `--line`, uppercase 10.5px labels, 22px monospace numbers
- **Topbar:** sticky 52px, gradient from bg-1 to bg, `border-bottom: 1px solid var(--line)`

---

## Tech Stack
- React 18 + Vite + TypeScript
- CSS custom properties (from design system above) in `src/index.css`
- Tailwind (layout utilities only — no Tailwind colors, use CSS vars)
- shadcn/ui New York theme for base form elements
- Framer Motion — SSE card animations
- Recharts — run summary charts
- TanStack Table — sortable incident list
- Zustand — shared state
- React Router v6 — navigation
- PapaParse — CSV parsing for sample data
- Native EventSource — SSE client (no library)

Install:
```bash
npm install framer-motion recharts @tanstack/react-table zustand react-router-dom papaparse
npm install -D @types/papaparse
```

---

## Routing (`src/App.tsx`)
```
/ → Upload
/runs/:runId → LiveAnalysis
/runs/:runId/summary → RunSummary
/incidents/:incidentId → IncidentDetail
```

---

## API
Base URL: `import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'`

Endpoints used:
- `POST /recon/runs` → upload CSV
- `GET /recon/runs/:id/stream` → SSE
- `GET /recon/runs/:id` → run + incidents
- `GET /recon/incidents/:id` → incident + evidence
- `POST /recon/incidents/:id/resolve` → submit resolution
- `GET /recon/runs/:id/incidents` → incident list

---

## Zustand Store (`src/store/reconStore.ts`)
```typescript
interface ReconStore {
  currentRunId: string | null
  incidents: Map<string, RCAIncident>
  runStatus: 'idle' | 'uploading' | 'streaming' | 'complete'
  llmConfig: 'claude' | 'groq' | 'hybrid'
  environment: 'PROD' | 'UAT'
  sseConnected: boolean
  runStats: RunStats | null
  setRunId: (id: string) => void
  upsertIncident: (incident: RCAIncident) => void
  setRunStatus: (status: string) => void
  setLlmConfig: (config: string) => void
  setEnvironment: (env: string) => void
}
```

Use `Map` not array — O(1) upsert when SSE updates incident.

---

## SSE Client (`src/lib/sse.ts`)
```typescript
export function connectToRun(runId: string, handlers: SSEHandlers): () => void {
  const es = new EventSource(`${API_URL}/recon/runs/${runId}/stream`)
  es.addEventListener('incident', e => handlers.onIncident(JSON.parse(e.data)))
  es.addEventListener('done', e => handlers.onDone(JSON.parse(e.data)))
  es.onerror = handlers.onError
  return () => es.close()
}
```

---

## View 1: Upload (`src/views/Upload.tsx`)
Reference: `docs/design/Home.html` — read it fully first.

- Topbar: ReconAI logo + brand mark, nav links (Runs, Settings), user badge
- Drop zone: dashed border, drag-and-drop CSV, changes to --info border on dragover
- "Or use sample FSC data" button:
  - Fetches `/sample_fsc_recon.csv` from public folder
  - Parses with PapaParse
  - Shows "10 rows loaded" confirmation
  - Must work without any file picker
- Config below drop zone:
  - Environment segmented control: PROD / UAT
  - LLM Model segmented control: Claude / Groq / Hybrid
- Recent runs table: run ID (mono), date, env badge, discrepancies, P1 count, status
- "Start Analysis" primary button → POST /recon/runs → navigate to /runs/:runId

Copy `data/sample_fsc_recon.csv` to `frontend/public/sample_fsc_recon.csv` before building.

---

## View 2: Live Analysis (`src/views/LiveAnalysis.tsx`)
Reference: `docs/design/Live_Analysis.html` — read it fully first.

**Layout:** main feed (left ~70%) + sidebar (right ~30%)

**Topbar:** breadcrumb (Runs > run_ID), model badge, env badge, progress pill with live count + ETA, pause button

**Stats row (6 columns):**
DISCREPANCIES | P1 CRITICAL | RESOLVED | NEEDS REVIEW | AUTO-FIX ELIGIBLE | MEAN TIME/INCIDENT

**Incident card (match design exactly):**
- Top: severity badge + integration name + record ID (mono) + status dot + elapsed time
- Field mapping: `[SF] Object . Field → [DB2] TABLE.COLUMN` in JetBrains Mono
- INC number right-aligned
- HYPOTHESES row: H1 H2 H3a H3b pills with done/active/pending states
- Analyzing state: live tool call log in monospace (`timestamp tool.name query...`)
- Complete state: ROOT CAUSE · CONFIRMED label + explanation + evidence chips + confidence bar

**Framer Motion:**
```typescript
<motion.div
  initial={{ opacity: 0, y: 12 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.2 }}
>
```
Cards sorted P1 first regardless of SSE arrival order.

**Right sidebar:**
- Agent Pipeline: numbered steps (Schema diff, FLS pull, DB2 query, Hypothesis ranking...) with latency
- Run Stats: TOKENS/INCIDENT, TOOL CALLS, CACHE HIT %, SPEND

Click completed card → navigate to /incidents/:incidentId

---

## View 3: Incident Detail (`src/views/IncidentDetail.tsx`)
Reference: `docs/design/Incident_Detail.html` — read it fully first.

- Breadcrumb: Runs > run_ID > INC-number
- Header: severity badge, object.field → table.column mapping, integration, record ID, status
- Hypothesis timeline: H1 → H2 → H3a with pass/fail/confirmed + latency per step
- Evidence section: cards each with source_type badge + source_reference (mono) + content + relevance
- Similar past incidents: 2-3 cards with similarity score bars
- Suggested fix: expandable
- Postmortem draft: expandable structured sections
- Jira summary: read-only + copy button
- Resolution form: confirmed_root_cause, fix_type select, fix_applied textarea, ai_was_correct toggle, submit

---

## View 4: Run Summary (`src/views/RunSummary.tsx`)
Reference: `docs/design/Run_Summary.html` — read it fully first.

- Run header: run ID (mono), date, env, duration, completed timestamp
- 6 stat cards
- Root cause distribution: Recharts horizontal bar chart
- By-object breakdown: TanStack Table (sortable)
- recall@k: percentage + trend
- LLM comparison table if groq config was used
- Export: Download JSON + Copy Jira text buttons

---

## Acceptance Criteria
- [ ] CSS variables applied globally in src/index.css, Inter + JetBrains Mono loaded
- [ ] Upload: drag-and-drop works, sample data button loads CSV without file picker
- [ ] Live Analysis: SSE connects, cards animate in, P1 always first, sidebar shows run stats
- [ ] Incident Detail: evidence cards with source badges, resolution form submits
- [ ] Run Summary: Recharts bar chart renders, recall@k displayed
- [ ] All routing works
- [ ] Zero hardcoded colors — all use CSS variables
- [ ] Design matches Claude Design HTML files visually

## Risk Flag
Framer Motion + rapid SSE events → React re-render storms. Use Map in Zustand (not array), wrap incident list in React.memo, and debounce SSE stat updates to prevent unnecessary re-renders during streaming.
