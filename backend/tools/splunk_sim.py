from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel


class SplunkEvent(BaseModel):
    event_type: str
    timestamp: str
    record_id: str
    field: str
    status: str  # "delivered" | "missed" | "error"
    correlation_id: str


class SplunkResult(BaseModel):
    record_id: str
    sf_field: str
    sf_object: str
    events_found: int
    missed_events: bool
    missed_count: int
    last_event_ts: str | None
    event_log: list[SplunkEvent]
    source_reference: str


_DELIVERED_TYPES = [
    "CDC_FIELD_CHANGE",
    "PLATFORM_EVENT_PUBLISH",
    "PLATFORM_EVENT_CONSUMED",
]

_MISSED_TYPES = [
    "PLATFORM_EVENT_MISSED",
    "CDC_CHANNEL_ERROR",
    "MIDDLEWARE_TIMEOUT",
]


def _seed(*parts: str) -> int:
    key = ":".join(str(p) for p in parts)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _correlation_id(rng: random.Random) -> str:
    return (
        f"{rng.randint(0, 0xFFFFFFFF):08x}-"
        f"{rng.randint(0, 0xFFFF):04x}-"
        f"{rng.randint(0, 0xFFFF):04x}-"
        f"{rng.randint(0, 0xFFFF):04x}-"
        f"{rng.randint(0, 0xFFFFFFFFFFFF):012x}"
    )


def query_splunk(
    sf_record_id: str,
    sf_field: str,
    sf_object: str,
    lookback_hours: int = 72,
) -> SplunkResult:
    rng = random.Random(_seed(sf_record_id, sf_field, sf_object))
    source_ref = f"splunk://cdc-pipeline/{sf_object}.{sf_field}/{sf_record_id}"

    if "Status" in sf_field or "Verification" in sf_field:
        miss_prob = 0.55
    elif sf_object == "KYC_Record__c":
        miss_prob = 0.45
    elif sf_object == "FinancialAccount__c":
        miss_prob = 0.40
    elif sf_field.endswith("__c"):
        miss_prob = 0.30
    else:
        miss_prob = 0.20

    has_missed = rng.random() < miss_prob
    total_events = rng.randint(2, 6) if has_missed else rng.randint(1, 4)
    missed_count = rng.randint(1, min(3, total_events)) if has_missed else 0

    now = datetime.now(timezone.utc)
    events: list[SplunkEvent] = []

    for i in range(total_events):
        hours_ago = rng.uniform(0.5, lookback_hours)
        ts = (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        is_miss = has_missed and i < missed_count
        events.append(SplunkEvent(
            event_type=rng.choice(_MISSED_TYPES if is_miss else _DELIVERED_TYPES),
            timestamp=ts,
            record_id=sf_record_id,
            field=sf_field,
            status="missed" if is_miss else "delivered",
            correlation_id=_correlation_id(rng),
        ))

    events.sort(key=lambda e: e.timestamp)

    return SplunkResult(
        record_id=sf_record_id,
        sf_field=sf_field,
        sf_object=sf_object,
        events_found=total_events,
        missed_events=has_missed,
        missed_count=missed_count,
        last_event_ts=events[-1].timestamp if events else None,
        event_log=events,
        source_reference=source_ref,
    )
