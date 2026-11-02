"""Publish the hypothesis catalogue to the frontend (/hypotheses page).

    python -m backend.graph.publish

A test fails if frontend/src/data/hypothesis_catalogue.json is out of date, so the page
always shows the checks, order and confidences the code actually uses.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.graph.hypotheses import catalogue_summary

PUBLISHED = Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "hypothesis_catalogue.json"


def render() -> str:
    return json.dumps(catalogue_summary(), indent=2) + "\n"


if __name__ == "__main__":
    PUBLISHED.write_text(render())
    print(f"Wrote {PUBLISHED}")
