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
    status: str  # "delivered" | "missed" | "error" | "retried"
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
    # MuleSoft DataWeave transform failures logged for this record/field.
    transform_errors: int = 0
    # Middleware retries of the same delivery (a precondition for duplicate inserts).
    retry_count: int = 0


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


def _event(rng: random.Random, now: datetime, lookback_hours: int, sf_record_id: str, sf_field: str,
           event_type: str, status: str) -> SplunkEvent:
    hours_ago = rng.uniform(0.5, lookback_hours)
    return SplunkEvent(
        event_type=event_type,
        timestamp=(now - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        record_id=sf_record_id, field=sf_field, status=status, correlation_id=_correlation_id(rng),
    )


def _from_scenario(scenario, sf_record_id: str, sf_field: str, sf_object: str, lookback_hours: int) -> SplunkResult:
    """Signals consistent with the record's declared fault (see backend/tools/world.py)."""
    rng = random.Random(_seed("scenario", sf_record_id, sf_field, sf_object))
    now = datetime.now(timezone.utc)
    fault = scenario.fault
    events: list[SplunkEvent] = []

    if fault != "CDC_FIELD_EXCLUDED":  # an untracked field publishes no change events at all
        for _ in range(rng.randint(1, 3)):
            events.append(_event(rng, now, lookback_hours, sf_record_id, sf_field, rng.choice(_DELIVERED_TYPES), "delivered"))

    missed = 0
    if fault == "DELIVERY_GAP":
        missed = rng.randint(1, 3)
    elif scenario.has("unrelated_missed_event"):
        missed = 1
    for _ in range(missed):
        events.append(_event(rng, now, lookback_hours, sf_record_id, sf_field, rng.choice(_MISSED_TYPES), "missed"))

    transform_errors = rng.randint(1, 4) if fault == "DATAWAVE_TRANSFORM_ERROR" else 0
    for _ in range(transform_errors):
        events.append(_event(rng, now, lookback_hours, sf_record_id, sf_field, "DATAWEAVE_TRANSFORM_ERROR", "error"))

    retries = rng.randint(2, 4) if fault == "DUPLICATE_DOWNSTREAM" else 0
    for _ in range(retries):
        events.append(_event(rng, now, lookback_hours, sf_record_id, sf_field, "MIDDLEWARE_RETRY", "retried"))

    events.sort(key=lambda e: e.timestamp)
    return SplunkResult(
        record_id=sf_record_id, sf_field=sf_field, sf_object=sf_object,
        events_found=len(events), missed_events=missed > 0, missed_count=missed,
        last_event_ts=events[-1].timestamp if events else None, event_log=events,
        source_reference=f"splunk://cdc-pipeline/{sf_object}.{sf_field}/{sf_record_id}",
        transform_errors=transform_errors, retry_count=retries,
    )


def query_splunk(
    sf_record_id: str,
    sf_field: str,
    sf_object: str,
    lookback_hours: int = 72,
) -> SplunkResult:
    from backend.tools.world import lookup

    scenario = lookup(sf_record_id)
    if scenario is not None:
        return _from_scenario(scenario, sf_record_id, sf_field, sf_object, lookback_hours)

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

    # Signals added later draw from their own generator so the fields above keep
    # their historical values for unknown records.
    extra = random.Random(_seed("extra", sf_record_id, sf_field, sf_object))
    transform_errors = extra.randint(1, 3) if extra.random() < 0.25 else 0
    retry_count = extra.randint(2, 4) if extra.random() < 0.15 else 0

    return SplunkResult(
        transform_errors=transform_errors,
        retry_count=retry_count,
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
