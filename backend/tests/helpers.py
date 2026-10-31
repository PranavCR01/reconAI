"""Small helpers for driving the API in tests."""
from __future__ import annotations

import io
import json


def upload_csv(client, csv_text: str, *, env: str = "PROD", ip: str | None = None, name: str = "t.csv"):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post(
        "/api/v1/recon/runs",
        files={"file": (name, io.BytesIO(csv_text.encode()), "text/csv")},
        data={"sf_org_id": "sf-demo-org", "db2_environment": env},
        headers=headers,
    )


def stream_events(client, run_id: str, params: str = "", headers: dict | None = None) -> list[dict]:
    """Consume the SSE stream for a run; returns [{'event', 'data', 'id'?}, ...]."""
    events, current = [], {}
    with client.stream("GET", f"/api/v1/recon/runs/{run_id}/stream{params}", headers=headers or {}) as response:
        for line in response.iter_lines():
            if line.startswith("id: "):
                current["id"] = line[4:]
            elif line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[6:])
            elif line == "" and current:
                events.append(current)
                current = {}
    if current:
        events.append(current)
    return events


def run_sample(client, csv_text: str, params: str = "") -> tuple[str, list[dict]]:
    """Upload a CSV and stream its analysis to completion."""
    response = upload_csv(client, csv_text)
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    return run_id, stream_events(client, run_id, params)


def ground_truth_row(incident: dict):
    """A ReconRow for a labeled benchmark incident (fields the simulators read)."""
    import uuid

    from backend.models.entities import DiscrepancyType, ReconRow

    return ReconRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, incident["id"]),
        sf_object=incident["sf_object"],
        sf_field=incident["sf_field"],
        sf_record_id=incident["sf_record_id"],
        sf_value="sf-value",
        db2_table="DB2_TABLE",
        db2_column="DB2_COLUMN",
        db2_value=None if incident["discrepancy_type"] == "NULL_DOWNSTREAM" else "db2-value",
        discrepancy_type=DiscrepancyType(incident["discrepancy_type"]),
    )


SYNTHESIS_PROMPT = "integration RCA analyst"


def synthesis_json(confidence: float = 0.9, root_cause: str = "Root cause from evidence.") -> str:
    import json

    return json.dumps({
        "root_cause": root_cause,
        "suggested_fix": "Apply the fix.",
        "postmortem_draft": "Postmortem.",
        "jira_summary": "RCA ticket",
        "confidence": confidence,
    })
