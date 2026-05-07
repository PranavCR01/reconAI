"""
ReconAI health check script.
Checks backend API, Supabase tables, frontend routes, and nav links.
Writes scripts/health_report.md with results.

Usage:
    python scripts/health_check.py
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://reconai-backend-ctnz.onrender.com"
FRONTEND_URL = "https://recon-ai-iota.vercel.app"
REPO_ROOT = Path(__file__).parent.parent
TIMEOUT = 20  # seconds per HTTP request

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


class Results:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, section: str, name: str, expected: str, actual: str, status: str, note: str = ""):
        self.rows.append(dict(section=section, name=name, expected=expected,
                              actual=actual, status=status, note=note))

    @property
    def passed(self):  return sum(1 for r in self.rows if r["status"] == PASS)
    @property
    def failed(self):  return sum(1 for r in self.rows if r["status"] == FAIL)
    @property
    def warned(self):  return sum(1 for r in self.rows if r["status"] == WARN)
    @property
    def total(self):   return len(self.rows)


results = Results()


def _http(method: str, url: str, timeout_override: int | None = None, **kwargs) -> tuple[int | None, str]:
    """Return (status_code, error_string). error_string is '' on success."""
    t = timeout_override if timeout_override is not None else TIMEOUT
    try:
        resp = requests.request(method, url, timeout=t, **kwargs)
        return resp.status_code, ""
    except requests.exceptions.Timeout:
        return None, f"timeout (>{t}s)"
    except requests.exceptions.ConnectionError as e:
        return None, f"connection error: {e}"
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# 1. Backend API checks
# ---------------------------------------------------------------------------

SAMPLE_CSV = textwrap.dedent("""\
    sf_object,sf_field,sf_record_id,sf_value,sf_last_modified,sf_modified_by,\
db2_table,db2_column,db2_value,db2_last_updated,last_deployed_at,\
integration_name,discrepancy_type,severity
    Account,AnnualRevenue,001xx000003GYn1,1000000.0,2026-01-15T10:00:00,user1,\
ACCT_FACT,ANNUAL_REV,900000.0,2026-01-14T09:00:00,2026-01-10T08:00:00,\
MuleSoft CDC,VALUE_MISMATCH,P1
""").strip()

BACKEND_CHECKS: list[tuple[str, str, dict]] = [
    ("GET",  "/api/v1/health",                                          {}),
    ("GET",  "/api/v1/recall",                                          {"timeout_override": 30}),
    ("GET",  "/api/v1/analytics/summary?days=30",                       {}),
    ("GET",  "/api/v1/analytics/incidents-over-time?days=30",           {}),
    ("GET",  "/api/v1/analytics/by-object?days=30",                     {}),
    ("GET",  "/api/v1/analytics/root-cause-distribution?days=30",       {}),
    ("GET",  "/api/v1/analytics/deployment-correlation?days=30",        {}),
    ("GET",  "/api/v1/analytics/ai-accuracy?weeks=5",                   {}),
    ("POST", "/api/v1/track/pageview",                                  {
        "json": {"page": "/health-check", "session_id": "hc-test-session",
                 "referrer": "", "user_agent": "health-check-script"},
    }),
    ("POST", "/api/v1/track/demo-request",                              {
        "json": {"full_name": "Health Check Bot", "work_email": "hc@example.com",
                 "company": "ReconAI Test", "session_id": "hc-test-session",
                 "referrer": ""},
    }),
]

EXPECTED_STATUS = {
    "POST /api/v1/recon/runs": 201,
}

def run_backend_checks():
    print("-- Backend API", flush=True)
    for method, path, kwargs in BACKEND_CHECKS:
        url = BASE_URL + path
        expected = EXPECTED_STATUS.get(f"{method} {path}", 200)
        print(f"   {method} {path} ...", end=" ", flush=True)
        kw = dict(kwargs)
        to = kw.pop("timeout_override", None)
        status, err = _http(method, url, timeout_override=to, **kw)
        actual = str(status) if status else f"ERR ({err})"
        ok = status == expected
        res = PASS if ok else FAIL
        results.add("Backend API", f"{method} {path}", str(expected), actual, res,
                    err if not ok and err else "")
        print(res, flush=True)

    # POST /api/v1/recon/runs — multipart
    path = "/api/v1/recon/runs"
    url = BASE_URL + path
    expected = 201
    print(f"   POST {path} ...", end=" ", flush=True)
    files = {"file": ("sample.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")}
    data = {"sf_org_id": "hc-test-org", "db2_environment": "UAT"}
    status, err = _http("POST", url, files=files, data=data)
    actual = str(status) if status else f"ERR ({err})"
    ok = status == expected
    res = PASS if ok else FAIL
    results.add("Backend API", f"POST {path}", str(expected), actual, res,
                err if not ok and err else "")
    print(res, flush=True)


# ---------------------------------------------------------------------------
# 2. Supabase table checks
# ---------------------------------------------------------------------------

REQUIRED_TABLES = [
    ("recon_runs",        ["id", "status", "completed_at"]),
    ("recon_rows",        ["id", "run_id", "sf_object", "sf_field", "discrepancy_type", "severity"]),
    ("rca_incidents",     ["id", "recon_row_id", "confidence", "status", "requires_human_review"]),
    ("rca_evidence",      ["id", "incident_id", "source_type", "content"]),
    ("resolutions",       ["id", "incident_id", "confirmed_root_cause", "fix_type", "resolved_by"]),
    ("rca_cache",         ["cache_key", "rca_output", "expires_at"]),
    ("page_views",        ["id", "page", "session_id"]),
    ("demo_requests",     ["id", "name", "email", "company", "requested_at"]),
    ("deployment_events", ["id", "deploy_name", "deployed_at"]),
    ("recon_artifacts",   ["id", "content", "embedding"]),
]

def run_supabase_checks():
    print("-- Supabase tables", flush=True)
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            for table, _ in REQUIRED_TABLES:
                results.add("Supabase Tables", table, "exists", "SKIPPED",
                            WARN, "SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
            print("   SKIPPED — env vars missing", flush=True)
            return
        client = create_client(url, key)
    except ImportError:
        for table, _ in REQUIRED_TABLES:
            results.add("Supabase Tables", table, "exists", "SKIPPED",
                        WARN, "supabase-py not installed")
        print("   SKIPPED — supabase-py not installed", flush=True)
        return

    for table, expected_cols in REQUIRED_TABLES:
        print(f"   {table} ...", end=" ", flush=True)
        try:
            resp = client.table(table).select(",".join(expected_cols)).limit(1).execute()
            # If we get here without exception the table exists and columns are present
            results.add("Supabase Tables", table, "exists + cols present",
                        "exists + cols present", PASS)
            print(PASS, flush=True)
        except Exception as e:
            err_str = str(e)
            # Distinguish "table not found" from "column not found"
            if "does not exist" in err_str.lower() or "relation" in err_str.lower():
                note = "table missing"
            elif "column" in err_str.lower():
                note = f"column missing: {err_str[:120]}"
            else:
                note = err_str[:120]
            results.add("Supabase Tables", table, "exists + cols present",
                        "ERROR", FAIL, note)
            print(FAIL, flush=True)

    # Extra: check UNIQUE constraint on resolutions.incident_id by attempting a duplicate insert
    print("   resolutions UNIQUE(incident_id) ...", end=" ", flush=True)
    try:
        # Fetch any existing incident_id from resolutions
        resp = client.table("resolutions").select("incident_id").limit(1).execute()
        if resp.data:
            iid = resp.data[0]["incident_id"]
            try:
                client.table("resolutions").insert({
                    "incident_id": iid,
                    "confirmed_root_cause": "hc-test",
                    "fix_type": "other",
                    "resolved_by": "health-check",
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
                # If insert succeeded the constraint may be missing
                results.add("Supabase Tables", "resolutions UNIQUE(incident_id)",
                            "duplicate rejected", "duplicate accepted", WARN,
                            "constraint may be missing or upsert mode active")
                print(WARN, flush=True)
            except Exception as e:
                if "unique" in str(e).lower() or "duplicate" in str(e).lower() or "23505" in str(e):
                    results.add("Supabase Tables", "resolutions UNIQUE(incident_id)",
                                "duplicate rejected", "duplicate rejected", PASS)
                    print(PASS, flush=True)
                else:
                    results.add("Supabase Tables", "resolutions UNIQUE(incident_id)",
                                "duplicate rejected", "error", WARN, str(e)[:120])
                    print(WARN, flush=True)
        else:
            results.add("Supabase Tables", "resolutions UNIQUE(incident_id)",
                        "duplicate rejected", "no data to test", WARN,
                        "resolutions table is empty — cannot test constraint")
            print(WARN, flush=True)
    except Exception as e:
        results.add("Supabase Tables", "resolutions UNIQUE(incident_id)",
                    "duplicate rejected", "error", WARN, str(e)[:120])
        print(WARN, flush=True)


# ---------------------------------------------------------------------------
# 3. Environment variable checks
# ---------------------------------------------------------------------------

REQUIRED_ENV_VARS = [
    ("SUPABASE_URL",         "Supabase project URL"),
    ("SUPABASE_SERVICE_KEY", "Supabase service role key"),
    ("ANTHROPIC_API_KEY",    "Claude LLM"),
    ("OPENAI_API_KEY",       "Embeddings"),
    ("GROQ_API_KEY",         "Groq LLM (optional)", True),
    ("RESEND_API_KEY",       "Email notifications (optional)", True),
    ("NOTIFY_EMAIL",         "Email notifications (optional)", True),
    ("SENTRY_DSN",           "Error tracking (optional)", True),
    ("VITE_DEMO_CODE",       "Frontend demo gate (optional)", True),
]

def run_env_checks():
    print("-- Environment variables", flush=True)
    for entry in REQUIRED_ENV_VARS:
        var, desc = entry[0], entry[1]
        optional = len(entry) > 2 and entry[2]
        val = os.environ.get(var, "")
        set_str = "set" if val else "not set"
        if val:
            res = PASS
        elif optional:
            res = WARN
        else:
            res = FAIL
        print(f"   {var} ... {res}", flush=True)
        results.add("Environment Variables", var, "set" if not optional else "optional",
                    set_str, res, desc)


# ---------------------------------------------------------------------------
# 4. Frontend route checks
# ---------------------------------------------------------------------------

FRONTEND_ROUTES = [
    ("/",              200),
    ("/upload",        200),
    ("/analytics",     200),
    ("/runs/test-id",  200),  # SPA rewrite — should serve index.html, not 404
]

def run_frontend_checks():
    print("-- Frontend routes", flush=True)
    for route, expected in FRONTEND_ROUTES:
        url = FRONTEND_URL + route
        print(f"   GET {route} ...", end=" ", flush=True)
        status, err = _http("GET", url)
        actual = str(status) if status else f"ERR ({err})"
        ok = status == expected
        res = PASS if ok else FAIL
        note = err if not ok and err else ""
        if not ok and status == 404 and route not in ("/", "/upload", "/analytics"):
            note = "SPA rewrite may be missing in vercel.json"
        results.add("Frontend Routes", f"GET {route}", str(expected), actual, res, note)
        print(res, flush=True)


# ---------------------------------------------------------------------------
# 5. Navigation link static analysis
# ---------------------------------------------------------------------------

def _read(rel: str) -> str:
    p = REPO_ROOT / rel
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1) if m else None


NAV_CHECKS = [
    # (component_file, check_label, regex_to_find_value, expected_value)
    (
        "frontend/src/App.tsx",
        "AppNav Runs link",
        r"label:\s*['\"]Runs['\"].*?href:\s*['\"]([^'\"]+)['\"]",
        "/upload",
    ),
    (
        "frontend/src/App.tsx",
        "AppNav Analytics link",
        r"label:\s*['\"]Analytics['\"].*?href:\s*['\"]([^'\"]+)['\"]",
        "/analytics",
    ),
    (
        "frontend/src/components/layout/TopBar.tsx",
        "TopBar brand mark",
        r"<Link\s+to=['\"]([^'\"]+)['\"]",
        "/",
    ),
    (
        "frontend/src/views/RunSummary.tsx",
        "RunSummary Runs breadcrumb",
        r"label:\s*['\"]Runs['\"][^}]*to:\s*['\"]([^'\"]+)['\"]",
        "/upload",
    ),
    (
        "frontend/src/views/LiveAnalysis.tsx",
        "LiveAnalysis Runs breadcrumb",
        r"label:\s*['\"]Runs['\"][^}]*to:\s*['\"]([^'\"]+)['\"]",
        "/upload",
    ),
    (
        "frontend/src/views/IncidentDetail.tsx",
        "IncidentDetail Live Analysis breadcrumb",
        r"label:\s*['\"]Live Analysis['\"]",
        "present",  # just check it exists; it has no `to` (current page label)
    ),
]

def run_nav_checks():
    print("-- Navigation links (static)", flush=True)
    for file_rel, label, pattern, expected in NAV_CHECKS:
        text = _read(file_rel)
        if not text:
            results.add("Navigation Links", label, expected, "FILE NOT FOUND", FAIL,
                        f"{file_rel} missing")
            print(f"   {label} ... {FAIL}", flush=True)
            continue

        if expected == "present":
            found = bool(re.search(pattern, text, re.DOTALL))
            actual = "present" if found else "not found"
            res = PASS if found else FAIL
        else:
            val = _find(pattern, text) if "\n" not in pattern else _find(
                re.compile(pattern, re.DOTALL).pattern, text)
            # try with DOTALL for multiline matches
            if val is None:
                m = re.search(pattern, text, re.DOTALL)
                val = m.group(1) if m else None
            actual = val if val else "not found"
            res = PASS if val == expected else FAIL

        print(f"   {label} ... {res}", flush=True)
        results.add("Navigation Links", label, expected, actual, res,
                    f"in {file_rel}" if res == PASS else f"expected '{expected}', got '{actual}' in {file_rel}")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    header = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    lines = [header, sep]
    for row in rows:
        lines.append("| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)) + " |")
    return "\n".join(lines)


def generate_report() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sections_order = [
        "Backend API",
        "Supabase Tables",
        "Environment Variables",
        "Frontend Routes",
        "Navigation Links",
    ]

    lines = [
        "# ReconAI Health Check Report",
        f"Generated: {ts}",
        "",
    ]

    for section in sections_order:
        section_rows = [r for r in results.rows if r["section"] == section]
        if not section_rows:
            continue
        lines.append(f"## {section}")
        table_rows = [
            [r["name"], r["expected"], r["actual"], r["status"],
             r["note"] if r["note"] else ""]
            for r in section_rows
        ]
        lines.append(_table(["Check", "Expected", "Actual", "Status", "Notes"], table_rows))
        lines.append("")

    lines += [
        "## Summary",
        f"- **Total checks:** {results.total}",
        f"- **Passed:** {results.passed}",
        f"- **Failed:** {results.failed}",
        f"- **Warnings:** {results.warned}",
        "",
    ]

    if results.failed:
        lines.append("### Failed checks")
        for r in results.rows:
            if r["status"] == FAIL:
                lines.append(f"- **{r['section']} / {r['name']}**: {r['note'] or 'see actual column'}")
        lines.append("")

    if results.warned:
        lines.append("### Warnings")
        for r in results.rows:
            if r["status"] == WARN:
                lines.append(f"- **{r['section']} / {r['name']}**: {r['note'] or 'see actual column'}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    t0 = time.time()
    print(f"\nReconAI Health Check — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Backend:  {BASE_URL}")
    print(f"Frontend: {FRONTEND_URL}\n")

    run_backend_checks()
    print()
    run_supabase_checks()
    print()
    run_env_checks()
    print()
    run_frontend_checks()
    print()
    run_nav_checks()

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.1f}s  —  "
          f"{results.passed} passed, {results.failed} failed, {results.warned} warnings\n")

    report = generate_report()
    out_path = REPO_ROOT / "scripts" / "health_report.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Report written to {out_path}\n")

    sys.exit(0 if results.failed == 0 else 1)
