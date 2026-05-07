# ReconAI Health Check Report
Generated: 2026-05-07 07:03:25 UTC

## Backend API
| Check                                                 | Expected | Actual        | Status | Notes   |
| ----------------------------------------------------- | -------- | ------------- | ------ | ------- |
| GET /api/v1/health                                    | 200      | 200           | PASS   |         |
| GET /api/v1/recall                                    | 200      | ERR (timeout) | FAIL   | timeout |
| GET /api/v1/analytics/summary?days=30                 | 200      | 200           | PASS   |         |
| GET /api/v1/analytics/incidents-over-time?days=30     | 200      | 200           | PASS   |         |
| GET /api/v1/analytics/by-object?days=30               | 200      | 200           | PASS   |         |
| GET /api/v1/analytics/root-cause-distribution?days=30 | 200      | 200           | PASS   |         |
| GET /api/v1/analytics/deployment-correlation?days=30  | 200      | 200           | PASS   |         |
| GET /api/v1/analytics/ai-accuracy?weeks=5             | 200      | 200           | PASS   |         |
| POST /api/v1/track/pageview                           | 200      | 200           | PASS   |         |
| POST /api/v1/track/demo-request                       | 200      | 200           | PASS   |         |
| POST /api/v1/recon/runs                               | 201      | 201           | PASS   |         |

## Supabase Tables
| Check             | Expected | Actual  | Status | Notes                                        |
| ----------------- | -------- | ------- | ------ | -------------------------------------------- |
| recon_runs        | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| recon_rows        | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| rca_incidents     | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| rca_evidence      | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| resolutions       | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| rca_cache         | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| page_views        | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| demo_requests     | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| deployment_events | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |
| recon_artifacts   | exists   | SKIPPED | WARN   | SUPABASE_URL or SUPABASE_SERVICE_KEY not set |

## Environment Variables
| Check                | Expected | Actual  | Status | Notes                          |
| -------------------- | -------- | ------- | ------ | ------------------------------ |
| SUPABASE_URL         | set      | not set | FAIL   | Supabase project URL           |
| SUPABASE_SERVICE_KEY | set      | not set | FAIL   | Supabase service role key      |
| ANTHROPIC_API_KEY    | set      | not set | FAIL   | Claude LLM                     |
| OPENAI_API_KEY       | set      | set     | PASS   | Embeddings                     |
| GROQ_API_KEY         | optional | not set | WARN   | Groq LLM (optional)            |
| RESEND_API_KEY       | optional | not set | WARN   | Email notifications (optional) |
| NOTIFY_EMAIL         | optional | not set | WARN   | Email notifications (optional) |
| SENTRY_DSN           | optional | not set | WARN   | Error tracking (optional)      |
| VITE_DEMO_CODE       | optional | not set | WARN   | Frontend demo gate (optional)  |

## Frontend Routes
| Check             | Expected | Actual | Status | Notes |
| ----------------- | -------- | ------ | ------ | ----- |
| GET /             | 200      | 200    | PASS   |       |
| GET /upload       | 200      | 200    | PASS   |       |
| GET /analytics    | 200      | 200    | PASS   |       |
| GET /runs/test-id | 200      | 200    | PASS   |       |

## Navigation Links
| Check                                   | Expected   | Actual     | Status | Notes                                        |
| --------------------------------------- | ---------- | ---------- | ------ | -------------------------------------------- |
| AppNav Runs link                        | /upload    | /upload    | PASS   | in frontend/src/App.tsx                      |
| AppNav Analytics link                   | /analytics | /analytics | PASS   | in frontend/src/App.tsx                      |
| TopBar brand mark                       | /          | /          | PASS   | in frontend/src/components/layout/TopBar.tsx |
| RunSummary Runs breadcrumb              | /upload    | /upload    | PASS   | in frontend/src/views/RunSummary.tsx         |
| LiveAnalysis Runs breadcrumb            | /upload    | /upload    | PASS   | in frontend/src/views/LiveAnalysis.tsx       |
| IncidentDetail Live Analysis breadcrumb | present    | present    | PASS   | in frontend/src/views/IncidentDetail.tsx     |

## Summary
- **Total checks:** 40
- **Passed:** 21
- **Failed:** 4
- **Warnings:** 15

### Failed checks
- **Backend API / GET /api/v1/recall**: timeout
- **Environment Variables / SUPABASE_URL**: Supabase project URL
- **Environment Variables / SUPABASE_SERVICE_KEY**: Supabase service role key
- **Environment Variables / ANTHROPIC_API_KEY**: Claude LLM

### Warnings
- **Supabase Tables / recon_runs**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / recon_rows**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / rca_incidents**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / rca_evidence**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / resolutions**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / rca_cache**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / page_views**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / demo_requests**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / deployment_events**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Supabase Tables / recon_artifacts**: SUPABASE_URL or SUPABASE_SERVICE_KEY not set
- **Environment Variables / GROQ_API_KEY**: Groq LLM (optional)
- **Environment Variables / RESEND_API_KEY**: Email notifications (optional)
- **Environment Variables / NOTIFY_EMAIL**: Email notifications (optional)
- **Environment Variables / SENTRY_DSN**: Error tracking (optional)
- **Environment Variables / VITE_DEMO_CODE**: Frontend demo gate (optional)
