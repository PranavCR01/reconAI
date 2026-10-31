"""Issue #10: scenario-driven simulators (backend/tools/world.py)."""
import json

import pytest

from backend.tools import world
from backend.tools.db2_sim import query_db2_field_history
from backend.tools.salesforce_sim import get_apex_trigger_config, get_cdc_field_config, get_field_permissions
from backend.tools.splunk_sim import query_splunk


def _signals(record_id, sf_object="Contact", sf_field="Phone"):
    return {
        "splunk": query_splunk(record_id, sf_field, sf_object),
        "db2": query_db2_field_history(sf_object, sf_field, record_id),
        "fls": get_field_permissions("svc@x", sf_object, sf_field, record_id),
        "cdc": get_cdc_field_config(sf_object, sf_field, record_id),
        "apex": get_apex_trigger_config(sf_object, record_id),
    }


# Which signals each declared fault must produce (and nothing else may).
EXPECTED = {
    "FLS_STRIPPED": dict(fls_blocked=True),
    "CDC_FIELD_EXCLUDED": dict(cdc_excluded=True, no_events=True),
    "DELIVERY_GAP": dict(missed=True),
    "DATAWAVE_TRANSFORM_ERROR": dict(transform=True),
    "DUPLICATE_DOWNSTREAM": dict(retries=True, duplicate_rows=True),
    "DOWNSTREAM_OVERWRITE": dict(populated=True),
    "APEX_SUPPRESSION": dict(suppressed=True),
    "NO_FAULT_FOUND": dict(),
}


@pytest.mark.parametrize("fault", world.FAULTS)
def test_each_fault_produces_exactly_its_signals(scenarios, fault):
    scenarios.add(f"W-{fault}", fault)
    s = _signals(f"W-{fault}")
    want = EXPECTED[fault]
    assert (s["fls"].has_read_access is False) == want.get("fls_blocked", False)
    assert (s["cdc"].is_tracked is False) == want.get("cdc_excluded", False)
    assert s["splunk"].missed_events == want.get("missed", False)
    assert (s["splunk"].events_found == 0) == want.get("no_events", False)
    assert (s["splunk"].transform_errors > 0) == want.get("transform", False)
    assert (s["splunk"].retry_count >= 2) == want.get("retries", False)
    assert (s["db2"].duplicate_rows > 1) == want.get("duplicate_rows", False)
    assert s["db2"].was_populated == want.get("populated", False)
    assert s["apex"].suppressed_for_record == want.get("suppressed", False)


def test_unrelated_missed_event_confounder(scenarios):
    scenarios.add("W-CONF-1", "FLS_STRIPPED", confounders=["unrelated_missed_event"])
    s = _signals("W-CONF-1")
    assert s["splunk"].missed_events and s["splunk"].missed_count == 1
    assert s["fls"].has_read_access is False  # the real cause is still visible


def test_dormant_apex_confounder(scenarios):
    scenarios.add("W-CONF-2", "DELIVERY_GAP", confounders=["apex_conditional_dormant"])
    a = _signals("W-CONF-2")["apex"]
    assert a.has_conditional_publish and not a.suppressed_for_record
    assert "Suppresses null" not in (a.conditional_logic_description or "")


def test_scenario_signals_are_deterministic(scenarios):
    scenarios.add("W-DET", "DATAWAVE_TRANSFORM_ERROR")
    a, b = _signals("W-DET"), _signals("W-DET")
    assert a["splunk"].transform_errors == b["splunk"].transform_errors
    assert [e.event_type for e in a["splunk"].event_log] == [e.event_type for e in b["splunk"].event_log]


def test_scenario_validation():
    with pytest.raises(ValueError):
        world.Scenario("X", "NOT_A_FAULT")
    with pytest.raises(ValueError):
        world.Scenario("X", "FLS_STRIPPED", frozenset({"made_up_noise"}))


def test_unknown_records_keep_their_original_random_signals():
    """Live uploads have no scenario; these values come from the pre-scenario simulators."""
    assert world.lookup("UNKNOWN0001") is None
    s = query_splunk("UNKNOWN0001", "Phone", "Contact")
    assert (s.missed_events, s.missed_count, s.events_found) == (True, 3, 6)
    d = query_db2_field_history("KYC_Record__c", "VerificationStatus__c", "UNKNOWN0002")
    assert (d.was_populated, d.last_value, d.db2_column) == (False, None, "VERIFICATION_STATUS_CD")
    f = get_field_permissions("a@x", "FinancialAccount__c", "TaxId__c")
    assert f.has_read_access and f.permission_sets == ["FSC_Integration_Base_PS", "KYC_Pipeline_Integration_PS", "Platform_Integration_User_PS"]
    assert get_cdc_field_config("Contact", "Score__c").is_tracked
    a = get_apex_trigger_config("KYC_Record__c")
    assert a.has_conditional_publish and a.trigger_name == "KYCRecordIntegrationTrigger"
    assert a.conditional_logic_description == "Deduplication gate: skips if identical event published within 60s"


def test_every_benchmark_incident_has_a_scenario_matching_its_label(ground_truth):
    for inc in ground_truth:
        s = world.lookup(inc["sf_record_id"])
        assert s is not None and s.source == "benchmark", inc["id"]
        assert s.fault == inc["ground_truth"]["root_cause"], inc["id"]


def test_every_sample_row_has_a_scenario(sample_rows):
    for row in sample_rows:
        assert world.lookup(row["sf_record_id"]) is not None, row["sf_record_id"]


def test_scenario_file_is_reproducible():
    """data/scenarios.json must equal what scripts/build_scenarios.py generates (nothing hand-edited)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "build_scenarios.py"
    spec = importlib.util.spec_from_file_location("build_scenarios", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build() == json.loads(world.SCENARIO_FILE.read_text())
