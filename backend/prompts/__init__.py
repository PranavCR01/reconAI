"""Versioned prompt templates (prompts are treated like code).

Each template's content hash is recorded in VERSIONS.json; a test fails if a prompt
changes without updating that file, so every prompt change shows up in review.
Incidents store the versions they were produced with.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent
VERSIONS_FILE = PROMPT_DIR / "VERSIONS.json"


def content_hash(name: str) -> str:
    return hashlib.sha256((PROMPT_DIR / name).read_bytes()).hexdigest()[:12]


@lru_cache(maxsize=None)
def template(name: str) -> str:
    return (PROMPT_DIR / name).read_text()


def recorded_versions() -> dict[str, str]:
    return json.loads(VERSIONS_FILE.read_text())


def versions(*names: str) -> dict[str, str]:
    """{name: recorded hash} for the given prompts (what an incident was produced with)."""
    recorded = recorded_versions()
    return {name: recorded[name] for name in names}
