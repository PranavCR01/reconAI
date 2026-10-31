"""Publish committed eval results to the frontend (/benchmark page).

    python -m backend.evals.publish

Writes frontend/src/data/eval_results.json from evals/results/*.json, without the
per-incident records. A test fails if the published file is out of date, so every
number on the page maps to a committed results file.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.evals.labels import ROOT

RESULTS_DIR = ROOT / "evals" / "results"
PUBLISHED = ROOT / "frontend" / "src" / "data" / "eval_results.json"


def compose(results_dir: Path = RESULTS_DIR) -> dict:
    results = {}
    for path in sorted(results_dir.glob("*.json")):
        data = json.loads(path.read_text())
        results[path.stem] = {k: v for k, v in data.items() if k != "incidents"}
        results[path.stem]["source_file"] = f"evals/results/{path.name}"
    return {"results": results}


def render(results_dir: Path = RESULTS_DIR) -> str:
    return json.dumps(compose(results_dir), indent=2) + "\n"


def publish(results_dir: Path = RESULTS_DIR, target: Path = PUBLISHED) -> Path:
    target.write_text(render(results_dir))
    return target


if __name__ == "__main__":
    print(f"Wrote {publish().relative_to(ROOT)}")
