from __future__ import annotations

import hashlib
import random

from pydantic import BaseModel


class FieldPermissionsResult(BaseModel):
    integration_user: str
    sf_object: str
    sf_field: str
    has_read_access: bool
    has_field_level_security: bool
    permission_sets: list[str]
    api_name: str


class CDCFieldConfigResult(BaseModel):
    sf_object: str
    sf_field: str
    is_tracked: bool
    reason_excluded: str | None = None
    cdc_channel: str | None = None


class ApexTriggerResult(BaseModel):
    sf_object: str
    trigger_name: str | None = None
    events: list[str]
    has_conditional_publish: bool
    conditional_logic_description: str | None = None


_PSET_POOL = [
    "FSC_Integration_Base_PS",
    "SF_DB2_Sync_Integration_PS",
    "Custom_FLS_Override_PS",
    "Platform_Integration_User_PS",
    "Recon_Integration_Access_PS",
    "FinancialServices_Integration_PS",
    "KYC_Pipeline_Integration_PS",
]

_ALWAYS_EXCLUDED_FIELDS = frozenset({"Body__c", "Description", "Notes__c", "LongNote__c"})
_FORMULA_SUFFIXES = ("Formula__c", "Calc__c", "Derived__c")
_HIGH_CONDITIONAL_OBJECTS = frozenset({"KYC_Record__c", "Address__c", "FinancialHolding__c"})

_APEX_EVENTS = [
    "before insert", "after insert",
    "before update", "after update",
    "after delete",
]
_CONDITIONAL_DESCRIPTIONS = [
    "Suppresses null value propagation when field was previously populated",
    "Skips publish if record owner changed in same transaction",
    "Only fires for HNW segment RecordType — excludes retail accounts",
    "Conditional on integration_active__c flag field being True",
    "Deduplication gate: skips if identical event published within 60s",
]
_CDC_EXCLUSION_REASONS = [
    "field_excluded_from_channel_config",
    "custom_field_not_in_tracked_field_set",
    "permission_based_exclusion_at_channel_level",
]


def _seed(*parts: str) -> int:
    key = ":".join(str(p) for p in parts)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def get_field_permissions(
    integration_user: str,
    sf_object: str,
    sf_field: str,
) -> FieldPermissionsResult:
    rng = random.Random(_seed(integration_user, sf_object, sf_field))

    if sf_object == "FinancialAccount__c":
        prob_blocked = 0.45
    elif sf_field.endswith("__c"):
        prob_blocked = 0.35
    elif sf_object == "Contact" and sf_field in ("Phone", "Email", "MailingCity"):
        prob_blocked = 0.15
    else:
        prob_blocked = 0.25

    has_read_access = rng.random() >= prob_blocked
    pset_count = rng.randint(1, 3) if has_read_access else rng.randint(0, 2)
    permission_sets = rng.sample(_PSET_POOL, min(pset_count, len(_PSET_POOL)))

    return FieldPermissionsResult(
        integration_user=integration_user,
        sf_object=sf_object,
        sf_field=sf_field,
        has_read_access=has_read_access,
        has_field_level_security=not has_read_access,
        permission_sets=permission_sets,
        api_name=f"{sf_object}.{sf_field}",
    )


def get_cdc_field_config(sf_object: str, sf_field: str) -> CDCFieldConfigResult:
    channel = f"sf_{sf_object.lower().replace('__c', '').replace('_', '')}_cdc"

    if sf_field in _ALWAYS_EXCLUDED_FIELDS:
        return CDCFieldConfigResult(
            sf_object=sf_object, sf_field=sf_field,
            is_tracked=False, reason_excluded="long_text_field",
        )
    if any(sf_field.endswith(pat) for pat in _FORMULA_SUFFIXES):
        return CDCFieldConfigResult(
            sf_object=sf_object, sf_field=sf_field,
            is_tracked=False, reason_excluded="formula_field",
        )

    rng = random.Random(_seed(sf_object, sf_field))
    is_tracked = rng.random() < (0.75 if sf_field.endswith("__c") else 0.90)

    if is_tracked:
        return CDCFieldConfigResult(
            sf_object=sf_object, sf_field=sf_field,
            is_tracked=True, cdc_channel=channel,
        )
    return CDCFieldConfigResult(
        sf_object=sf_object, sf_field=sf_field,
        is_tracked=False,
        reason_excluded=rng.choice(_CDC_EXCLUSION_REASONS),
        cdc_channel=channel,
    )


def get_apex_trigger_config(sf_object: str) -> ApexTriggerResult:
    rng = random.Random(_seed(sf_object))

    if rng.random() < 0.20:
        return ApexTriggerResult(
            sf_object=sf_object, events=[],
            has_conditional_publish=False,
        )

    obj_clean = sf_object.replace("__c", "").replace("_", "")
    events = rng.sample(_APEX_EVENTS, k=rng.randint(2, 4))
    prob_conditional = 0.65 if sf_object in _HIGH_CONDITIONAL_OBJECTS else 0.25
    has_conditional = rng.random() < prob_conditional

    return ApexTriggerResult(
        sf_object=sf_object,
        trigger_name=f"{obj_clean}IntegrationTrigger",
        events=events,
        has_conditional_publish=has_conditional,
        conditional_logic_description=(
            rng.choice(_CONDITIONAL_DESCRIPTIONS) if has_conditional else None
        ),
    )
