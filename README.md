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

AI-powered Salesforce FSC integration reconciliation and root cause analysis, replacing 3 hours of manual Splunk correlation with automated hypothesis graph analysis in under 15 seconds per incident.

---

## Links

| | |
|---|---|
| App | https://recon-ai-iota.vercel.app |
| Demo Video | https://youtu.be/cEzxQ1xfltU |
| Research Notes | https://www.notion.so/ReconAI-Research-Architecture-Notes-358a47a2b4cf8000944fefad0ddf1349 |
| Dev Journal | https://www.notion.so/ReconAI-Project-Arc-358a47a2b4cf8004a38bee6d50283911?source=copy_link |
| GitHub | https://github.com/PranavCR01/reconAI |

---

## The Problem

Salesforce FSC integration teams begin each day correlating data discrepancies between Salesforce and downstream systems like DB2 and Snowflake. The process depends on an Excel decision tree that encodes years of tribal knowledge: which Splunk query to run first, which FSC fields are commonly stripped by FLS, which CDC channels silently exclude custom objects. When a discrepancy repeats, the analyst must trace it from scratch. There is no postmortem, no audit trail, and no accumulated memory — only the same failures recurring week after week.

---

## What ReconAI Does

ReconAI encodes that decision tree as a deterministic hypothesis graph and runs it automatically for every discrepancy in the morning CSV, streaming results to the analyst in real time.

**Step 1 — Upload.** The analyst uploads the daily reconciliation CSV. Each row identifies a Salesforce object and field, the downstream DB2 table and column, the observed discrepancy type (NULL_DOWNSTREAM, VALUE_MISMATCH, STALE_VALUE, MISSING_RECORD, or DUPLICATE_DOWNSTREAM), and a severity rating.

**Step 2 — Analyze.** A LangGraph state machine routes each discrepancy through a hypothesis graph. Agents make real tool calls against Salesforce, Splunk, and DB2 simulators. The graph terminates as soon as a hypothesis is confirmed, avoiding unnecessary checks.

**Step 3 — Fix.** Every incident receives a root cause with cited evidence, a suggested remediation, an auto-generated postmortem draft, and a Jira summary. Results stream to the browser as each incident completes, with P1 incidents surfaced first regardless of processing order.

---

## Architecture

### System Overview

```
Upload CSV
    │
    ▼
Ingestion Agent  ──── classifies discrepancy type and severity (Claude Haiku)
    │
    ▼
Hypothesis Agent ──── walks graph, decides next hypothesis (Claude Sonnet)
    │
    ▼
Evidence Agent   ──── executes tool calls, returns cited EvidenceResult (Claude Sonnet)
    │
    ▼
Synthesis Agent  ──── assembles RCA from complete state (Claude Sonnet)
    │
    ▼
SSE Stream       ──── FastAPI StreamingResponse, one event per incident
    │
    ▼
React Frontend   ──── Zustand store, live incident cards, P1 priority sort
```

The Ingestion and Hypothesis agents carry no tool calls. Only the Evidence agent executes tools. This boundary is enforced by design: Hypothesis decides what to check, Evidence executes the check. The two responsibilities are never merged.

### The Hypothesis Graph

Each discrepancy enters the graph at H1 and exits at the first confirmed hypothesis. The graph structure encodes the diagnostic logic from the original Excel decision tree.

**H1: DB2 History Check.** Query the downstream DB2 field history over a 30-day window. Determines whether the discrepancy is new or recurring. Recurring patterns with no recent DB2 writes suggest a delivery gap rather than a data quality issue.

**H2: Splunk Triage.** Query Splunk CDC pipeline logs for missed platform events. Confirms whether CDC events fired and were dropped in transit, or never fired from Salesforce at all. The graph terminates early if a delivery gap is confirmed at this node.

**H3a: Field-Level Security Check.** Query Salesforce `FieldPermissions` for the integration profile on the specific object and field combination. FLS stripping is the most common root cause for NULL_DOWNSTREAM discrepancies and is checked before CDC configuration.

**H3b: CDC Channel Configuration.** Check whether the field appears in the `ChangeEvent` tracked field list for the object. Long text fields, formula fields, and certain custom fields are excluded from CDC payloads by platform default.

**H3c: Apex Trigger Logic.** Check for conditional publish suppression in Apex triggers. A common pattern in FSC implementations is a trigger that skips CDC event publishing when a field transitions from a populated value to null.

**H4: DataWeave Transform Deep Dive.** Analyze the MuleSoft DataWeave transform layer for picklist label versus API name mismatches, timezone conversion errors, and null-suppression conditionals that silently discard values in transit.

**H5: RAG Fallback.** If no deterministic hypothesis confirms, retrieve the five most similar past incidents from the pgvector store using cosine similarity on 1536-dimension embeddings. Claude Sonnet synthesizes a root cause from the retrieved context and attaches it with lower confidence.

Early termination applies throughout: a NULL_DOWNSTREAM incident with a confirmed FLS hit at H3a never evaluates H3b, H3c, H4, or H5.

### RAG Pipeline

Embeddings are generated with OpenAI `text-embedding-3-small` at 1536 dimensions. The `recon_artifacts` table in Supabase holds 23 FSC seed artifacts covering the known failure pattern library, indexed with a pgvector HNSW index for approximate nearest-neighbor retrieval.

Retrieval uses a hybrid approach: a Postgres pre-filter narrows candidates by `discrepancy_type`, an ANN search over the HNSW index ranks by cosine similarity, and Claude Sonnet reranks the top results before synthesis. Artifacts ingested within the last six hours are treated as ground truth and weighted accordingly.

When a human analyst confirms a resolution, that incident and its fix are embedded and written back to the artifact store, closing the memory loop.

### Data Sources

All integrations are implemented as simulators in the current version, with realistic probability distributions derived from known FSC failure patterns. No real Salesforce org, Splunk instance, or DB2 connection is required to run the application.

| Source | What the agents query |
|---|---|
| Salesforce | `FieldPermissions` for integration user, field value history, CDC `ChangeEvent` channel config, Apex trigger metadata |
| Splunk | CDC pipeline logs, platform event publish logs, MuleSoft flow execution logs |
| DB2 | Field value history over 30-day window, null pattern frequency analysis |
| MuleSoft / GitHub | DataWeave transform files, field mapping configurations, deployment history |

---

## Data Model

| Table | Purpose |
|---|---|
| `recon_runs` | One reconciliation execution, linked to uploaded CSV |
| `recon_rows` | One discrepancy row from the CSV, with 1536-dim embedding |
| `rca_incidents` | One RCA analysis result per discrepancy row |
| `rca_evidence` | Cited artifacts per incident — enforces the no-unsupported-claim constraint |
| `resolutions` | Human-confirmed fixes, written back to the RAG artifact store |
| `recon_artifacts` | pgvector HNSW store for RAG retrieval, 1536-dim cosine index |
| `rca_cache` | 24-hour TTL cache keyed on field and value combination, bypassed with `?bypass_cache=true` |

Supporting tables: `deployment_events` (analytics correlation), `page_views`, `demo_requests`.

---

## Benchmark Results

### Test Setup

Fifty synthetic Salesforce FSC incidents were generated across ten objects: Contact, Account, Task, Event, AccountAccountRelation, AccountContactRelation, ContactContactRelation, FinancialAccount\_\_c, KYC\_Record\_\_c, and Address\_\_c. The incidents span five discrepancy types and were manually labeled with ground truth root causes. All three configurations were evaluated with cache bypassed to ensure independent analysis. Run date: May 7, 2026.

### Results

| Config | Accuracy | Human Review Rate | Avg Confidence | Avg Latency | Cost per Incident |
|---|---|---|---|---|---|
| Claude Sonnet | 70% | 56% | 80% | 12.5s | $0.006 |
| Groq Llama 3.3 70B | 62% | 50% | 85% | 1.4s | $0.001 |
| Hybrid (recommended) | 67% | 65% | 81% | ~9s | $0.004 |

### Failure Patterns

All three configurations share the same failure modes, confirming these are graph-level issues rather than model-specific weaknesses.

| Pattern | Description | Incidents Affected |
|---|---|---|
| H2/H3a Confusion | Splunk check terminates before FLS check on complex NULL_DOWNSTREAM incidents where both CDC events are missing and FLS is restricted | 5 |
| STALE_VALUE RAG Fallback | The STALE_VALUE hypothesis branch exhausts without confirming DELIVERY_GAP, causing fallback to H5 instead of confirming consumer lag at H2 | 3 |
| CDC Exclusion Fallback | H3b fails to confirm CDC field exclusion, falling through to H5 RAG fallback instead of returning a deterministic result | 3 |

### Key Finding

The Hybrid configuration achieves the best human review calibration at 65%, combining Groq classification speed with Claude Sonnet synthesis quality to produce the optimal cost-accuracy tradeoff for production deployment.

---

## Design Constraints

These invariants are enforced throughout the codebase and are not negotiable.

1. Every `RCAIncident` must have at least one `rca_evidence` row per hypothesis tested. The orchestrator validates evidence completeness before Synthesis runs. Missing evidence triggers a retry (maximum two attempts), not a surface.
2. The `propose_replay` tool is always gated behind explicit human approval. It is never auto-executed.
3. Confidence below 0.75 sets `requires_human_review = true`. These incidents are surfaced separately in the UI.
4. Every LLM call is logged with model name, version, token count, and latency.
5. P1 incidents display first in the UI regardless of SSE arrival order.
6. Pydantic v2 validation is applied at every agent boundary. A schema violation triggers a retry with error context injected into the next prompt.
7. Simulator tools vary their responses based on input parameters. No static or hardcoded returns.

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
RESEND_API_KEY=              # optional, enables demo request email notifications
NOTIFY_EMAIL=                # optional, recipient for demo request notifications
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

The frontend runs on `http://localhost:5173` by default. Set `VITE_API_URL=http://localhost:8000/api/v1` in `frontend/.env.local` to point at the local backend.

**Seed analytics data (run once)**

```bash
python -m backend.seed.analytics_seed
```

This inserts 25 synthetic reconciliation runs, approximately 375 incidents, 225 resolutions, and 8 deployment events spanning April 6 to May 4, 2026. The script is idempotent and skips if more than 10 runs already exist.

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
│   ├── agents/
│   │   ├── ingestion.py          # discrepancy classification, Claude Haiku, no tool calls
│   │   ├── hypothesis.py         # graph traversal and routing, Claude Sonnet
│   │   ├── evidence.py           # all tool call execution, Claude Sonnet
│   │   └── synthesis.py          # RCA assembly from complete state, Claude Sonnet
│   ├── tools/
│   │   ├── salesforce_sim.py     # FieldPermissions, CDC config, Apex trigger metadata
│   │   ├── splunk_sim.py         # CDC pipeline logs, platform event logs
│   │   ├── db2_sim.py            # field history, null pattern analysis
│   │   └── rag_tools.py          # pgvector retrieval and reranking
│   ├── graph/
│   │   └── recon_graph.py        # LangGraph state machine definition
│   ├── models/
│   │   ├── state.py              # LangGraph state schema
│   │   ├── entities.py           # Pydantic domain models
│   │   └── outputs.py            # agent output schemas
│   ├── storage/
│   │   ├── adapter.py            # storage interface
│   │   └── supabase_adapter.py   # Supabase and pgvector implementation
│   ├── cache/
│   │   └── rca_cache.py          # 24-hour TTL keyed cache
│   ├── seed/
│   │   ├── fsc_incidents.py      # 23 FSC RAG seed artifacts
│   │   └── analytics_seed.py     # synthetic historical data for analytics
│   ├── config.py                 # AgentConfig, LLM routing per agent
│   └── main.py                   # FastAPI app, all endpoints, SSE streaming
├── frontend/src/
│   ├── views/
│   │   ├── Landing.tsx           # public landing page
│   │   ├── Upload.tsx            # CSV upload with access gate
│   │   ├── LiveAnalysis.tsx      # SSE streaming, real-time incident cards
│   │   ├── IncidentDetail.tsx    # full RCA view with resolution workflow
│   │   ├── RunSummary.tsx        # post-run summary and export
│   │   ├── Analytics.tsx         # historical analytics dashboard
│   │   └── Benchmark.tsx         # LLM benchmark results
│   ├── components/
│   │   ├── analytics/            # StatCard, IncidentsOverTime, RootCauseDonut,
│   │   │                         #   ByObjectChart, AIAccuracyChart, DeploymentTable
│   │   ├── layout/               # Shell, TopBar
│   │   └── ui/                   # Badge, BrandMark, Button, Card, ConfidenceBar,
│   │                             #   EvidenceChip, HypothesisPills, StatusPill, and others
│   ├── store/
│   │   └── reconStore.ts         # Zustand store for run and incident state
│   ├── lib/
│   │   ├── api.ts                # typed fetch wrappers for all endpoints
│   │   ├── sse.ts                # SSE client with Last-Event-ID reconnect
│   │   └── format.ts             # display formatting utilities
│   ├── types/
│   │   └── index.ts              # TypeScript interfaces for all API responses
│   └── data/
│       └── benchmark_data.json   # benchmark results data for Benchmark view
├── data/
│   ├── sample_fsc_recon.csv      # representative FSC discrepancy sample
│   ├── benchmark_incidents.csv   # 50 benchmark test incidents
│   └── benchmark_ground_truth.json
├── docs/
│   ├── design/                   # HTML design references for each view
│   ├── slices/                   # implementation slice briefs
│   └── slides/                   # LinkedIn slide deck
├── scripts/
│   └── health_check.py           # 40-point E2E health check
├── vercel.json                   # SPA rewrite rule for Vercel deployment
└── requirements.txt
```

---

## Built By

**Pranav CR**
Graduate Researcher, UIUC Information Management
Former Deloitte Analyst — Financial Services Cloud integrations
ML Intern, Drongo AI

[LinkedIn](https://www.linkedin.com/in/pranav-c-r-852752202/) | [GitHub](https://github.com/PranavCR01) | [Portfolio](https://pranavcr01.github.io/)
