from __future__ import annotations

from datetime import date
from typing import Any


def _cfop_current(record: dict[str, Any], period_start: date, period_end: date) -> bool:
    effective_from = date.fromisoformat(record["effective_from"])
    effective_to_raw = record.get("effective_to")
    effective_to = date.fromisoformat(effective_to_raw) if effective_to_raw else None
    return effective_from <= period_end and (
        effective_to is None or effective_to >= period_start
    )


def classify_product_item(
    record: dict[str, Any],
    cfop_index: dict[str, dict[str, Any]],
    sale_cfops: set[str],
    inbound_return_cfops: set[str],
    period_start: date,
    period_end: date,
) -> tuple[str, dict[str, Any] | None]:
    """Classify an NF-e/NFC-e product operation using one CFOP ruleset."""

    cfop = str(record.get("cfop") or "").strip()
    official = cfop_index.get(cfop)
    if (
        official is None
        or official.get("ind_nfe") != 1
        or not _cfop_current(official, period_start, period_end)
    ):
        return "INVALID_CFOP_PENDING", official
    direction = record.get("direction")
    if official["ind_devolution"] == 1:
        if direction == "ENTRADA" and cfop in inbound_return_cfops:
            return "SALES_RETURN_INBOUND", official
        if direction == "SAIDA":
            return "PURCHASE_RETURN_OUTBOUND", official
        return "RETURN_INBOUND_PENDING_ORIGIN", official
    if official["ind_annulment"] == 1:
        return "NON_REVENUE_ANNULMENT", official
    if official["ind_return"] == 1:
        return "NON_REVENUE_RETURN", official
    if official["ind_remittance"] == 1:
        return "NON_REVENUE_REMITTANCE", official
    if direction == "SAIDA" and cfop in sale_cfops:
        return "REVENUE_GOODS", official
    if direction == "SAIDA":
        return "PENDING_REVENUE_TREATMENT", official
    return "PURCHASE_CONTEXT", official


def classify_acquisition_product_item(
    record: dict[str, Any],
    cfop_index: dict[str, dict[str, Any]],
    inbound_return_cfops: set[str],
    period_start: date,
    period_end: date,
) -> tuple[str, dict[str, Any] | None]:
    """Map the shared operation classes to purchase-side semantics."""

    classification, official = classify_product_item(
        record,
        cfop_index,
        set(),
        inbound_return_cfops,
        period_start,
        period_end,
    )
    if classification == "PURCHASE_CONTEXT":
        return classification, official
    if classification in {
        "SALES_RETURN_INBOUND",
        "NON_REVENUE_ANNULMENT",
        "NON_REVENUE_RETURN",
        "NON_REVENUE_REMITTANCE",
    }:
        return "NON_PURCHASE_ENTRY", official
    return "PENDING_PURCHASE_TREATMENT", official
