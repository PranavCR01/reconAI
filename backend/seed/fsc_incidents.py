"""Synthetic FSC incident seed data for the recon_artifacts RAG knowledge base.

23 resolved incidents covering all five discrepancy types and root cause categories.
Run once on startup when recon_artifacts is empty.
"""
from __future__ import annotations

import asyncio

from backend.models.entities import DiscrepancyType, ReconArtifact

_INCIDENTS: list[ReconArtifact] = [
    # ── NULL_DOWNSTREAM — FLS blocking ────────────────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="FinancialAccount__c",
        sf_field="TotalAssets__c",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="FLS_blocking",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.92,
        content=(
            "FinancialAccount__c.TotalAssets__c was null in DB2 for 847 records after a "
            "permission set reorg in March. Root cause: the FSC_Integration_User profile lost "
            "read access to TotalAssets__c when the custom FS_Data_Access permission set was "
            "removed during a Salesforce admin bulk update. Resolution: re-granted field-level "
            "security via FSC_Integration_PS permission set; downstream DB2 backfill completed "
            "via replay_manual_trigger within 4 hours. Confidence 0.92."
        ),
        source="incident://FSC-2024-0312/FLS",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Opportunity",
        sf_field="CloseDate",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="FLS_blocking",
        integration_name="Opp_Middleware",
        resolution_confirmed=True,
        confidence_score=0.89,
        content=(
            "Opportunity.CloseDate missing downstream for 312 records post-sandbox refresh. "
            "Root cause: sandbox-to-production permission migration omitted the Opp_Integration "
            "permission set for the middleware service account. Integration user 'opp-svc@org.com' "
            "lacked FLS read on CloseDate. Resolution: fls_permission_grant applied to "
            "Opp_Integration_PS; records resynced. Incident lasted 6 hours before detection."
        ),
        source="incident://OPP-2024-0118/FLS",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Contact",
        sf_field="TaxId__c",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="FLS_blocking",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.88,
        content=(
            "Contact.TaxId__c null in DB2 for all records modified after API version upgrade to v59. "
            "Root cause: API v59 enforced stricter FLS checks that surfaced an existing gap — "
            "FSC_Integration_User never had explicit read access to TaxId__c (it was previously "
            "accessible via a legacy object permission). Resolution: fls_permission_grant on "
            "TaxId__c; Salesforce TAM confirmed this is a known API v59 behaviour change."
        ),
        source="incident://FSC-2024-0521/FLS-APIv59",
    ),

    # ── NULL_DOWNSTREAM — CDC field exclusion ─────────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="FinancialAccount__c",
        sf_field="PortfolioValue__c",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="CDC_field_exclusion",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.91,
        content=(
            "FinancialAccount__c.PortfolioValue__c not propagating to DB2 for 5 weeks. "
            "Root cause: PortfolioValue__c was inadvertently excluded from the "
            "FinancialAccountChangeEvent CDC channel during a field set cleanup by a junior admin. "
            "The CDC channel config UI was used incorrectly — the field was unchecked without "
            "realising it controls downstream propagation. Resolution: cdc_channel_config fix; "
            "full backfill via data_backfill job over 2-hour window."
        ),
        source="incident://FSC-2024-0207/CDC",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Contact",
        sf_field="MobilePhone",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="CDC_field_exclusion",
        integration_name="Contact_Sync_MuleSoft",
        resolution_confirmed=True,
        confidence_score=0.86,
        content=(
            "Contact.MobilePhone null downstream for all contacts created after the ContactChangeEvent "
            "channel was reconfigured in the Spring '24 release window. Root cause: MobilePhone was "
            "not re-added to the tracked field list after the channel was recreated to resolve a "
            "separate duplicate-subscription bug. Resolution: cdc_channel_config corrected; "
            "MuleSoft replay consumer triggered for 72-hour window of missed events."
        ),
        source="incident://CONTACT-2024-0403/CDC",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Account",
        sf_field="AnnualRevenue",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="CDC_field_exclusion",
        integration_name="Account_DB2_Bridge",
        resolution_confirmed=True,
        confidence_score=0.84,
        content=(
            "Account.AnnualRevenue downstream null for Enterprise segment accounts post-migration. "
            "Root cause: AccountChangeEvent CDC channel was migrated to a new channel family during "
            "the Account object restructure. AnnualRevenue was not included in the new channel's "
            "field list because the migration script only copied 'Required' fields. "
            "Resolution: cdc_channel_config updated; backfill job for 2,100 affected records."
        ),
        source="incident://ACCT-2024-0614/CDC-migration",
    ),

    # ── NULL_DOWNSTREAM — Apex conditional publish ────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Account",
        sf_field="AnnualRevenue",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="Apex_conditional_publish",
        integration_name="Account_DB2_Bridge",
        resolution_confirmed=True,
        confidence_score=0.78,
        content=(
            "Account.AnnualRevenue null downstream for accounts with RecordType='Prospect'. "
            "Root cause: AccountSyncTrigger.trigger had an undocumented guard "
            "'if (acct.AnnualRevenue != null)' before publishing the platform event, "
            "which silently dropped null values instead of propagating them as explicit nulls. "
            "The trigger was written to avoid noisy events but caused data loss. "
            "Resolution: apex_code_change to publish event regardless of null; "
            "requires_human_review flagged because conditional logic was intentional for some cases."
        ),
        source="incident://ACCT-2024-0820/Apex",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="FinancialAccount__c",
        sf_field="RiskScore__c",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="Apex_conditional_publish",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.74,
        content=(
            "FinancialAccount__c.RiskScore__c null in DB2 for accounts flagged as 'Under Review'. "
            "Root cause: RiskScorePublisher Apex class suppressed platform event publication "
            "when account status was 'Under Review' as a compliance hold. This was intentional "
            "policy but undocumented, causing the recon team to raise a false positive. "
            "Resolution: documented the intentional suppression; added status='Under Review' "
            "to the exclusion list in the recon rules engine. confidence < 0.75 — human confirmed."
        ),
        source="incident://FSC-2024-0915/Apex-compliance",
    ),

    # ── NULL_DOWNSTREAM — Splunk missed events ───────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Lead",
        sf_field="Status",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="missed_CDC_events",
        integration_name="Lead_MuleSoft_Bridge",
        resolution_confirmed=True,
        confidence_score=0.87,
        content=(
            "Lead.Status null downstream for 1,200+ leads over a 48-hour window in November. "
            "Splunk showed 1,847 LeadChangeEvent platform events undelivered — MuleSoft consumer "
            "restarted during a Salesforce maintenance window and missed the replay window "
            "(default 72h replay ID expired). Root cause: CDC replay ID drift due to uncoordinated "
            "maintenance. Resolution: middleware_restart + data_backfill via SOQL export; "
            "replay window extended to 168h in MuleSoft config."
        ),
        source="incident://LEAD-2023-1102/Splunk-missed",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="FinancialAccount__c",
        sf_field="InvestmentRisk__c",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="missed_CDC_events",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.90,
        content=(
            "FinancialAccount__c.InvestmentRisk__c null for 340 accounts post-quarter-end batch. "
            "Splunk captured 340 unprocessed FinancialAccountChangeEvents — the DB2 consumer "
            "pod OOMKilled during a memory spike caused by concurrent recon batch, "
            "losing in-flight events. Root cause: resource contention between the recon batch "
            "and the CDC consumer on the same k8s node. Resolution: middleware_restart; "
            "added resource limits and anti-affinity rule to prevent co-scheduling."
        ),
        source="incident://FSC-2024-0101/Splunk-OOM",
    ),

    # ── NULL_DOWNSTREAM — DB2 history / downstream overwrite ─────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Opportunity",
        sf_field="Amount",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="downstream_overwrite",
        integration_name="Opp_Middleware",
        resolution_confirmed=True,
        confidence_score=0.85,
        content=(
            "Opportunity.Amount null in DB2 for 89 won opportunities. DB2 field history showed "
            "Amount was previously synced correctly then cleared. Root cause: a nightly DB2 "
            "reconciliation job incorrectly NULLed Amount for opportunities in 'Closed Won' "
            "status, treating them as stale. The reconciliation job had a logic error introduced "
            "in a hotfix. Resolution: data_backfill from Salesforce golden source; DB2 job "
            "query corrected to exclude 'Closed Won' from the null-propagation logic."
        ),
        source="incident://OPP-2024-0229/DB2-overwrite",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Account",
        sf_field="Phone",
        discrepancy_type=DiscrepancyType.NULL_DOWNSTREAM,
        root_cause_category="downstream_overwrite",
        integration_name="Account_DB2_Bridge",
        resolution_confirmed=True,
        confidence_score=0.82,
        content=(
            "Account.Phone null in DB2 for accounts with BillingCountry='CA'. DB2 history showed "
            "Phone was synced correctly until the Q3 data masking project. Root cause: a data "
            "masking script applied to DB2 PROD incorrectly NULLed Phone for all Canadian accounts "
            "instead of masking only SSN fields. Script had a WHERE clause bug. "
            "Resolution: data_backfill from Salesforce; masking script corrected and retested."
        ),
        source="incident://ACCT-2024-0710/DB2-masking",
    ),

    # ── MISSING_RECORD ────────────────────────────────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Account",
        sf_field="Id",
        discrepancy_type=DiscrepancyType.MISSING_RECORD,
        root_cause_category="sync_job_skip",
        integration_name="Account_DB2_Bridge",
        resolution_confirmed=True,
        confidence_score=0.88,
        content=(
            "2,400 Account records missing from DB2 after the Q2 full-sync job. "
            "Root cause: the sync job SOQL query included 'WHERE CreatedDate > :lastSync' but "
            "the lastSync timestamp was reset incorrectly to epoch (1970-01-01) after a "
            "config file corruption, causing the job to exclude all records predating 1970 "
            "(effectively all records). Resolution: full re-sync via data_backfill; "
            "lastSync checkpoint now stored in DB2 rather than config file."
        ),
        source="incident://ACCT-2024-0501/missing-sync",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Contact",
        sf_field="Id",
        discrepancy_type=DiscrepancyType.MISSING_RECORD,
        root_cause_category="integration_filter_exclusion",
        integration_name="Contact_Sync_MuleSoft",
        resolution_confirmed=True,
        confidence_score=0.91,
        content=(
            "Person Account Contacts missing from DB2 — 1,100 records affected. "
            "Root cause: MuleSoft integration flow filtered out Contacts with IsPersonAccount=true, "
            "a legacy filter from pre-FSC implementation that was never removed. "
            "Person Accounts were introduced in the FSC rollout but the integration was not updated. "
            "Resolution: dataweave_mapping_fix removing the IsPersonAccount filter; "
            "full backfill of Person Account contacts."
        ),
        source="incident://CONTACT-2024-0317/missing-filter",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Opportunity",
        sf_field="Id",
        discrepancy_type=DiscrepancyType.MISSING_RECORD,
        root_cause_category="batch_timeout",
        integration_name="Opp_Middleware",
        resolution_confirmed=True,
        confidence_score=0.83,
        content=(
            "450 Opportunity records missing from DB2 after month-end close. "
            "Root cause: the Apex batch job processing opportunity sync timed out at the "
            "Salesforce 10-minute limit due to a governor limit violation (SOQL in a loop "
            "introduced in a recent commit). Partial batch committed 8,300/8,750 records. "
            "Resolution: apex_code_change to bulkify the SOQL; missing records reprocessed "
            "via selective data_backfill using CreatedDate range."
        ),
        source="incident://OPP-2024-0131/missing-timeout",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="FinancialAccount__c",
        sf_field="Id",
        discrepancy_type=DiscrepancyType.MISSING_RECORD,
        root_cause_category="middleware_routing_error",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.86,
        content=(
            "FinancialAccount__c records with AccountSubType='529_Plan' missing from DB2. "
            "Root cause: MuleSoft routing rule used AccountType instead of AccountSubType "
            "for the FSC_DB2_Sync flow selector. 529_Plan subtype was not in the AccountType "
            "routing map, so records were silently dropped at the router. "
            "Resolution: dataweave_mapping_fix to use AccountSubType in routing; "
            "529_Plan records backfilled."
        ),
        source="incident://FSC-2024-0622/missing-routing",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Lead",
        sf_field="Id",
        discrepancy_type=DiscrepancyType.MISSING_RECORD,
        root_cause_category="transform_error_drop",
        integration_name="Lead_MuleSoft_Bridge",
        resolution_confirmed=True,
        confidence_score=0.84,
        content=(
            "Leads with Company=null (individual leads) missing from DB2 post-spring release. "
            "Root cause: a DataWeave transform function called .trim() on Company field without "
            "null guard, throwing a NullPointerException for individual leads and causing the "
            "MuleSoft flow to drop those records via the error handler's discard policy. "
            "Resolution: dataweave_mapping_fix to add null coalescing ('?' operator); "
            "affected leads reprocessed from Salesforce."
        ),
        source="incident://LEAD-2024-0409/missing-transform",
    ),

    # ── VALUE_MISMATCH ────────────────────────────────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Account",
        sf_field="BillingState",
        discrepancy_type=DiscrepancyType.VALUE_MISMATCH,
        root_cause_category="dataweave_mapping_error",
        integration_name="Account_DB2_Bridge",
        resolution_confirmed=True,
        confidence_score=0.93,
        content=(
            "Account.BillingState values mismatched between Salesforce (full state names) and "
            "DB2 (2-letter codes) for 3,200 records. Root cause: the DataWeave state mapping "
            "table was built for US states only; Canadian province codes were not included, "
            "causing Canadian accounts to pass through with full province names (e.g. 'Ontario') "
            "instead of DB2-expected codes (e.g. 'ON'). Resolution: dataweave_mapping_fix "
            "to extend the mapping table with all Canadian provinces and territories."
        ),
        source="incident://ACCT-2024-0825/mismatch-state",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="FinancialAccount__c",
        sf_field="CurrencyIsoCode",
        discrepancy_type=DiscrepancyType.VALUE_MISMATCH,
        root_cause_category="dataweave_mapping_error",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.90,
        content=(
            "FinancialAccount__c.CurrencyIsoCode mismatched: Salesforce stores 'CAD', DB2 expects "
            "numeric ISO 4217 code '124'. 6,700 records affected post-multi-currency enablement. "
            "Root cause: DataWeave transform was not updated when multi-currency was enabled — "
            "previously all accounts were USD so no conversion was needed. "
            "Resolution: dataweave_mapping_fix to convert ISO alpha codes to numeric via lookup table; "
            "records resynced via middleware_restart."
        ),
        source="incident://FSC-2024-0708/mismatch-currency",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Contact",
        sf_field="MailingCountry",
        discrepancy_type=DiscrepancyType.VALUE_MISMATCH,
        root_cause_category="enum_conversion_error",
        integration_name="Contact_Sync_MuleSoft",
        resolution_confirmed=True,
        confidence_score=0.87,
        content=(
            "Contact.MailingCountry mismatched between Salesforce and DB2 for 890 records. "
            "DB2 stores 2-char ISO country codes; Salesforce stores full names after "
            "State and Country Picklists were enabled. Root cause: MuleSoft integration "
            "did not handle the Salesforce picklist value format change (full name vs code). "
            "Resolution: dataweave_mapping_fix with ISO 3166-1 alpha-2 lookup; picklist "
            "values re-mapped for all affected contacts."
        ),
        source="incident://CONTACT-2024-0513/mismatch-country",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Opportunity",
        sf_field="StageName",
        discrepancy_type=DiscrepancyType.VALUE_MISMATCH,
        root_cause_category="status_mapping_drift",
        integration_name="Opp_Middleware",
        resolution_confirmed=True,
        confidence_score=0.85,
        content=(
            "Opportunity.StageName values mismatched for 1,500 records: Salesforce shows "
            "'Needs Analysis' but DB2 shows 'Qualification' (the previous stage name). "
            "Root cause: Sales Ops renamed two pipeline stages in Salesforce without "
            "updating the DB2 stage mapping table in the middleware. Integration continued "
            "translating old DB2 codes to old Salesforce names. "
            "Resolution: dataweave_mapping_fix to sync stage name mapping; future stage "
            "changes now gated on integration team review."
        ),
        source="incident://OPP-2024-0317/mismatch-stage",
    ),

    # ── DUPLICATE_DOWNSTREAM ──────────────────────────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Account",
        sf_field="Id",
        discrepancy_type=DiscrepancyType.DUPLICATE_DOWNSTREAM,
        root_cause_category="idempotency_key_missing",
        integration_name="Account_DB2_Bridge",
        resolution_confirmed=True,
        confidence_score=0.92,
        content=(
            "Account records appearing twice in DB2 after infrastructure failover event. "
            "Root cause: the Account upsert to DB2 used INSERT instead of MERGE, with no "
            "idempotency key on the SalesforceId column. During the failover, MuleSoft "
            "retried 3,400 in-flight events, all of which succeeded, creating duplicates. "
            "Resolution: dataweave_mapping_fix to use MERGE ON SalesforceId; dedup job "
            "removed 3,400 duplicate DB2 rows; added unique index on SalesforceId."
        ),
        source="incident://ACCT-2024-0630/duplicate-idempotency",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Contact",
        sf_field="Id",
        discrepancy_type=DiscrepancyType.DUPLICATE_DOWNSTREAM,
        root_cause_category="retry_loop_double_insert",
        integration_name="Contact_Sync_MuleSoft",
        resolution_confirmed=True,
        confidence_score=0.89,
        content=(
            "Contact records duplicated in DB2 for contacts updated within 5 minutes of each other. "
            "Root cause: MuleSoft retry policy was set to 3 retries with 0s delay on HTTP 5xx. "
            "A DB2 connection pool exhaustion event returned 503s, triggering retries that all "
            "succeeded once the pool recovered — but each retry inserted a new row. "
            "Resolution: dataweave_mapping_fix to upsert on SalesforceId; retry policy "
            "updated to exponential backoff with jitter; duplicate rows cleaned up."
        ),
        source="incident://CONTACT-2024-0422/duplicate-retry",
    ),

    # ── STALE_VALUE ───────────────────────────────────────────────────────────
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="FinancialAccount__c",
        sf_field="TotalAssets__c",
        discrepancy_type=DiscrepancyType.STALE_VALUE,
        root_cause_category="cache_TTL_too_long",
        integration_name="FSC_DB2_Sync",
        resolution_confirmed=True,
        confidence_score=0.86,
        content=(
            "FinancialAccount__c.TotalAssets__c stale in DB2 by up to 72 hours for high-frequency "
            "trading accounts. Root cause: the FSC_DB2_Sync middleware cached Salesforce field "
            "values with a 72-hour TTL to reduce API calls. For accounts with daily portfolio "
            "rebalancing, TotalAssets changed faster than the cache expired. "
            "Resolution: reduced TTL to 15 minutes for FinancialAccount records with "
            "AccountSubType in ('Brokerage','Investment'); cache eviction on CDC event receipt."
        ),
        source="incident://FSC-2024-0115/stale-cache",
    ),
    ReconArtifact(
        artifact_type="past_incident",
        sf_object="Opportunity",
        sf_field="Amount",
        discrepancy_type=DiscrepancyType.STALE_VALUE,
        root_cause_category="async_consumer_lag",
        integration_name="Opp_Middleware",
        resolution_confirmed=True,
        confidence_score=0.83,
        content=(
            "Opportunity.Amount stale in DB2 during quarter-end crunch — values 4-18 hours behind. "
            "Root cause: the CDC consumer queue depth exceeded 500k events during quarter-end "
            "deal rush, causing a processing backlog. The consumer was single-threaded and could "
            "not scale to meet the event rate. DB2 values reflected amounts from earlier in the day. "
            "Resolution: middleware scaled to 8 consumer threads; queue depth alerting added at "
            "10k events threshold; no data loss, only lag."
        ),
        source="incident://OPP-2024-0331/stale-lag",
    ),
]


async def seed_artifacts(storage) -> int:
    """Embed and insert all seed incidents if recon_artifacts is empty. Returns count seeded."""
    from backend.tools.rag_tools import embed_text

    try:
        existing = await storage.search_similar_artifacts(
            [0.0] * 1536, limit=1
        )
    except Exception:
        existing = []

    if existing:
        return 0

    seeded = 0
    for artifact in _INCIDENTS:
        try:
            embedding = await asyncio.to_thread(embed_text, artifact.content)
            await storage.save_artifact(artifact, embedding)
            seeded += 1
        except Exception:
            continue

    return seeded
