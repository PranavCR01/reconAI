from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel


class FieldHistoryResult(BaseModel):
    was_populated: bool
    last_value: str | None = None
    last_updated_at: str | None = None
    db2_column: str
    time_window_days: int
    records_checked: int


_DB2_COLUMN_MAP: dict[str, str] = {
    "MailingCity": "MAILING_CITY_NM",
    "MailingStreet": "MAILING_STREET_ADDR",
    "Phone": "PHONE_NBR",
    "Email": "EMAIL_ADDR_TXT",
    "TaxId__c": "TAX_IDENT_NBR",
    "AnnualIncome__c": "ANNUAL_INCOME_AMT",
    "AccountStatus__c": "ACCT_STATUS_CD",
    "BalanceAmt__c": "BALANCE_AMT",
    "VerificationStatus__c": "VERIFICATION_STATUS_CD",
    "PostalCode": "POSTAL_CD",
    "StateCode": "STATE_CD",
    "CountryCode": "CNTRY_CD",
}

_SAMPLE_VALUES: dict[str, list[str]] = {
    "MailingCity": ["Chicago", "New York", "Los Angeles", "Houston", "Phoenix"],
    "Phone": ["+1-312-555-1234", "+1-773-555-9876", "+1-847-555-4321", "+1-630-555-0011"],
    "TaxId__c": ["XXX-XX-1234", "XXX-XX-5678", "XXX-XX-9012", "XXX-XX-3456"],
    "AnnualIncome__c": ["125000.00", "150000.00", "200000.00", "95000.00", "310000.00"],
    "AccountStatus__c": ["Active", "Pending", "Inactive", "Suspended"],
    "BalanceAmt__c": ["12500.00", "47250.00", "98000.00", "3200.00"],
    "VerificationStatus__c": ["Verified", "Pending", "Under Review", "Rejected"],
    "PostalCode": ["60601", "60614", "60657", "60640", "60622"],
    "StateCode": ["IL", "CA", "NY", "TX", "FL"],
}


def _seed(*parts: str) -> int:
    key = ":".join(str(p) for p in parts)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def query_db2_field_history(
    sf_object: str,
    sf_field: str,
    sf_record_id: str,
    time_window_days: int = 30,
) -> FieldHistoryResult:
    rng = random.Random(_seed(sf_object, sf_field, sf_record_id))

    if "Status" in sf_field or "Verification" in sf_field:
        prob = 0.60
    elif sf_object == "KYC_Record__c":
        prob = 0.40
    else:
        prob = 0.20

    was_populated = rng.random() < prob
    db2_col = _DB2_COLUMN_MAP.get(
        sf_field, sf_field.upper().replace("__C", "") + "_VAL"
    )

    if not was_populated:
        return FieldHistoryResult(
            was_populated=False,
            db2_column=db2_col,
            time_window_days=time_window_days,
            records_checked=0,
        )

    days_ago = rng.randint(2, time_window_days)
    last_dt = (
        datetime.now(timezone.utc) - timedelta(days=days_ago)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    pool = _SAMPLE_VALUES.get(sf_field, ["PREV_VAL_A", "PREV_VAL_B", "PREV_VAL_C"])

    return FieldHistoryResult(
        was_populated=True,
        last_value=rng.choice(pool),
        last_updated_at=last_dt,
        db2_column=db2_col,
        time_window_days=time_window_days,
        records_checked=rng.randint(1, 5),
    )
