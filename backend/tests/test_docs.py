"""Issue #16: docs cite committed eval results, carry no stale claims, and have no broken links."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts" / "check_docs.py")
check_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_docs)


@pytest.fixture
def scratch_root(tmp_path, monkeypatch):
    monkeypatch.setattr(check_docs, "ROOT", tmp_path)
    return tmp_path


def test_docs_are_clean():
    files = check_docs.doc_files()
    assert {"README.md", "CLAUDE.md", "docs/ADR.md", "docs/presentation-claims.md"} <= \
        {str(f.relative_to(ROOT)) for f in files}
    problems = check_docs.check_metrics(files) + check_docs.check_stale(files) + check_docs.check_links(files)
    assert not problems, "\n".join(problems)


def test_headline_numbers_are_tagged():
    tags = sum(len(check_docs.TAG.findall(f.read_text())) for f in check_docs.doc_files())
    assert tags >= 15, "headline numbers must be tagged against evals/results"


@pytest.mark.parametrize("text,expected_problem", [
    ("Accuracy <!--m:offline_claude/metrics.accuracy.overall:pct-->70%", "shows '70%'"),
    ("<!--m:offline_claude/metrics.nope:pct-->1%", "does not resolve"),
    ("<!--m:missing_file/metrics.accuracy.overall:pct-->1%", "does not resolve"),
])
def test_metric_drift_is_caught(scratch_root, text, expected_problem):
    f = scratch_root / "x.md"
    f.write_text(text)
    problems = check_docs.check_metrics([f])
    assert any(expected_problem in p for p in problems), problems


def test_correct_metric_passes(scratch_root):
    f = scratch_root / "x.md"
    f.write_text("Accuracy <!--m:offline_claude/metrics.accuracy.overall:frac-->50/50, done.")
    assert check_docs.check_metrics([f]) == []


@pytest.mark.parametrize("line", [
    "Use access code reconai2026", "We sync to Snowflake", "propose_replay is gated", "Export to Jira",
    "costs $0.006 per incident", "in under 15 seconds",
])
def test_stale_claims_are_caught_outside_the_log(scratch_root, line):
    f = scratch_root / "x.md"
    f.write_text(f"# Overview\n{line}\n")
    assert check_docs.check_stale([f])
    f.write_text(f"## Session Log\n{line}\n")
    assert not check_docs.check_stale([f]), "historical log entries are allowed"


def test_link_check_catches_missing_paths(scratch_root):
    f = scratch_root / "x.md"
    f.write_text("[a](missing.md) and `backend/nope.py` and [ok](https://x.y) and [anchor](#top)")
    assert len(check_docs.check_links([f])) == 2


def test_render_formats():
    rate = {"k": 30, "n": 50, "rate": 0.6, "ci95": [0.4618, 0.7239]}
    assert check_docs.render(rate, "pct") == "60%"
    assert check_docs.render(rate, "frac") == "30/50"
    assert check_docs.render(rate, "ci") == "46-72%"
    assert check_docs.render(2.06, "num") == "2.06"
