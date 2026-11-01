"""Docs checks (run in CI via backend/tests/test_docs.py, or directly: python scripts/check_docs.py).

1. Metric tags: every number in the docs that comes from an eval is written as
       <!--m:offline_claude/metrics.accuracy.overall:pct-->100%
   i.e. results file stem / dotted path : format, immediately followed by the value.
   The check fails if the value differs from the committed results file.
   Formats: pct -> "100%", frac -> "50/50", ci -> "93-100%", num -> str(value).
2. Stale claims: banned phrases for features or numbers that don't exist.
3. Links: relative markdown links and backticked repo paths must exist.

Historical material (docs/history/, docs/slices/, docs/design/) is not checked, and
lines inside a "Session Log" section are exempt from the stale-claim lint.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"

HISTORICAL = ("docs/history/", "docs/slices/", "docs/design/")
# Files that must quote retired claims in order to correct them.
STALE_ALLOWED_FILES = {"docs/presentation-claims.md"}

BANNED = [
    (re.compile(r"access code", re.I), "the access gate was removed"),
    (re.compile(r"snowflake", re.I), "there is no Snowflake integration"),
    (re.compile(r"propose_replay"), "no replay tool exists"),
    (re.compile(r"export to jira", re.I), "there is no Jira export (only copy-to-clipboard)"),
    (re.compile(r"\$0\.006"), "retired cost figure; cite evals/results"),
    (re.compile(r"under 15 seconds", re.I), "retired latency claim; cite evals/results"),
]

TAG = re.compile(r'<!--m:([\w-]+)/([\w.]+):(pct|frac|ci|num)-->([^\s|<),;"]*)')
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE_PATH = re.compile(r"`((?:backend|frontend|docs|data|scripts|evals)/[\w./-]+\.\w+)`")


def doc_files() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md"))]
    return [f for f in files if f.exists() and not str(f.relative_to(ROOT)).startswith(HISTORICAL)]


def _lookup(stem: str, path: str):
    value = json.loads((RESULTS / f"{stem}.json").read_text())
    for part in path.split("."):
        value = value[part]
    return value


def render(value, fmt: str) -> str:
    if fmt == "pct":
        return f"{round(value['rate'] * 100)}%"
    if fmt == "frac":
        return f"{value['k']}/{value['n']}"
    if fmt == "ci":
        lo, hi = value["ci95"]
        return f"{round(lo * 100)}-{round(hi * 100)}%"
    return str(value)


def check_metrics(files) -> list[str]:
    errors = []
    for f in files:
        for stem, path, fmt, shown in TAG.findall(f.read_text()):
            shown = shown.rstrip(".")  # sentence-ending period
            try:
                expected = render(_lookup(stem, path), fmt)
            except (FileNotFoundError, KeyError, TypeError) as exc:
                errors.append(f"{f.relative_to(ROOT)}: tag {stem}/{path}:{fmt} does not resolve ({exc!r})")
                continue
            if shown != expected:
                errors.append(f"{f.relative_to(ROOT)}: {stem}/{path} shows {shown!r}, results say {expected!r}")
    return errors


def check_stale(files) -> list[str]:
    errors = []
    for f in files:
        rel = str(f.relative_to(ROOT))
        if rel in STALE_ALLOWED_FILES:
            continue
        in_log = False
        for n, line in enumerate(f.read_text().splitlines(), start=1):
            if line.startswith("#"):
                in_log = "session log" in line.lower() or "changelog" in line.lower()
            if in_log:
                continue
            for pattern, why in BANNED:
                if pattern.search(line):
                    errors.append(f"{rel}:{n}: '{pattern.pattern}' ({why})")
    return errors


def check_links(files) -> list[str]:
    errors = []
    for f in files:
        text = f.read_text()
        targets = [t for t in MD_LINK.findall(text) if not re.match(r"^(https?:|mailto:|#)", t)]
        for t in targets:
            if not (f.parent / t.split("#")[0]).exists():
                errors.append(f"{f.relative_to(ROOT)}: broken link {t}")
        for p in CODE_PATH.findall(text):
            if not (ROOT / p).exists():
                errors.append(f"{f.relative_to(ROOT)}: referenced path {p} does not exist")
    return errors


def main() -> int:
    files = doc_files()
    errors = check_metrics(files) + check_stale(files) + check_links(files)
    for e in errors:
        print(e)
    print(f"{len(files)} docs checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
