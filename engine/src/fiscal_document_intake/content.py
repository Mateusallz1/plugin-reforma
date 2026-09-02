from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from functools import lru_cache
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .core import (
    DOCUMENT_SCHEMA_VERSION,
    ValidationError,
    _format_decimal,
    _local_name,
    _parse_decimal,
    _parse_xml_file,
    _raw_files,
    _safe_relative_files,
)
from .ruleset_integrity import verify_trusted_hash

CONTENT_SCHEMA = "br.com.planejamento-reforma-tributaria/fiscal-content"
CONTENT_SCHEMA_VERSION = "1.4.0"
PRODUCT_NCM_CATALOG = Path("00_CONTROLE") / "catalogo-produtos-ncm.csv"
NCM_SNAPSHOT_NAME = "ncm-2026-09-01.json"
NCM_SOURCE_URL = (
    "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"
)

FIELD_COVERAGE = {
    "PRODUCT": (
        "description",
        "product_code",
        "ean",
        "ncm",
        "cest",
        "cfop",
        "benefit_code",
        "cclass_trib",
        "ibs_cbs_cst",
        "insurance",
        "ipi_amount",
        "icms_st_amount",
        "fcp_st_amount",
        "import_duty_amount",
        "ipi_returned_amount",
    ),
    "SERVICE": (
        "description",
        "service_list_code",
        "cnae",
        "municipal_tax_code",
        "nbs",
        "cclass_trib",
        "ibs_cbs_cst",
    ),
    "TRANSPORT": (
        "description",
        "cfop",
        "transport_modal",
        "nature_operation",
        "cclass_trib",
        "ibs_cbs_cst",
    ),
}

VNF_COMPONENT_FIELDS = (
    ("vProd", "product", 1, "ICMSTot"),
    ("vDesc", "discount", -1, "ICMSTot"),
    ("vICMSDeson", "icms_exempt", -1, "ICMSTot"),
    ("vST", "icms_st", 1, "ICMSTot"),
    ("vFCPST", "fcp_st", 1, "ICMSTot"),
    ("vFrete", "freight", 1, "ICMSTot"),
    ("vSeg", "insurance", 1, "ICMSTot"),
    ("vOutro", "other_expenses", 1, "ICMSTot"),
    ("vII", "import_duty", 1, "ICMSTot"),
    ("vIPI", "ipi", 1, "ICMSTot"),
    ("vIPIDevol", "ipi_returned", 1, "ICMSTot"),
    ("vServ", "services", 1, "ISSQNtot"),
)


def _first_element(element: Any | None, names: set[str]) -> Any | None:
    if element is None:
        return None
    normalized = {name.lower() for name in names}
    return next(
        (
            candidate
            for candidate in element.iter()
            if _local_name(candidate.tag).lower() in normalized
        ),
        None,
    )


def _direct_child(element: Any | None, name: str) -> Any | None:
    if element is None:
        return None
    normalized = name.lower()
    return next(
        (
            child
            for child in list(element)
            if _local_name(child.tag).lower() == normalized
        ),
        None,
    )


def _text(element: Any | None, names: set[str]) -> str | None:
    found = _first_element(element, names)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _direct_text(element: Any | None, name: str) -> str | None:
    child = _direct_child(element, name)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _number(value: Any) -> str | None:
    parsed = _parse_decimal(value)
    return None if parsed is None else format(parsed, "f")


def _item_ref(document_ref: str, record_kind: str, item_number: int) -> str:
    digest = hashlib.sha256(
        f"{document_ref}:{record_kind}:{item_number}".encode()
    ).hexdigest()
    return f"ITEM-{digest[:16].upper()}"


def _component_ref(item_ref: str, index: int) -> str:
    digest = hashlib.sha256(f"{item_ref}:COMPONENT:{index}".encode()).hexdigest()
    return f"COMP-{digest[:16].upper()}"


def _finding(code: str, field: str, severity: str) -> dict[str, str]:
    return {"code": code, "field": field, "severity": severity}


def _validate_code(
    findings: list[dict[str, str]],
    value: str | None,
    *,
    field: str,
    missing_code: str,
    invalid_code: str,
    pattern: str,
    missing_severity: str = "OBSERVATION",
    invalid_severity: str = "OBSERVATION",
) -> None:
    if not value:
        findings.append(_finding(missing_code, field, missing_severity))
    elif re.fullmatch(pattern, value) is None:
        findings.append(_finding(invalid_code, field, invalid_severity))


def _content_status(findings: list[dict[str, str]]) -> str:
    severities = {finding["severity"] for finding in findings}
    if "RESTRICTION" in severities:
        return "RESTRICTED"
    if "BLOCKER" in severities:
        return "BLOCKED"
    if severities & {"OBSERVATION", "REVIEW", "WARNING"}:
        return "READY_WITH_OBSERVATIONS"
    return "READY"


def _catalog_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_br_date(value: str) -> date | None:
    try:
        day, month, year = (int(part) for part in value.split("/"))
        return date(year, month, day)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _load_ncm_snapshot() -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    resource = resource_files("fiscal_document_intake").joinpath(
        "data", NCM_SNAPSHOT_NAME
    )
    try:
        raw = resource.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(
            "Snapshot oficial da NCM está ausente ou inválido"
        ) from error
    if not isinstance(payload, dict) or not isinstance(
        payload.get("Nomenclaturas"), list
    ):
        raise ValidationError("Snapshot oficial da NCM possui formato incompatível")

    catalog: dict[str, dict[str, str]] = {}
    for entry in payload["Nomenclaturas"]:
        if not isinstance(entry, dict):
            continue
        code = re.sub(r"\D", "", str(entry.get("Codigo") or ""))
        if len(code) != 8:
            continue
        start = _parse_br_date(str(entry.get("Data_Inicio") or ""))
        end = _parse_br_date(str(entry.get("Data_Fim") or ""))
        if start is None or end is None:
            continue
        catalog[code] = {
            "description": str(entry.get("Descricao") or "").strip(),
            "effective_from": start.isoformat(),
            "effective_to": end.isoformat(),
        }
    source_hash = hashlib.sha256(raw).hexdigest()
    integrity = verify_trusted_hash(
        Path(NCM_SNAPSHOT_NAME), source_hash, "snapshot oficial da NCM"
    )
    return catalog, {
        "status": "LOADED",
        "snapshot_id": NCM_SNAPSHOT_NAME.removesuffix(".json"),
        "source": NCM_SOURCE_URL,
        "verified_at": "2026-09-01",
        "effective_label": payload.get("Data_Ultima_Atualizacao_NCM"),
        "act": payload.get("Ato"),
        "source_hash": source_hash,
        **integrity,
        "records": len(catalog),
    }


def _ncm_description_review(
    record: dict[str, Any],
    ncm_catalog: dict[str, dict[str, str]],
    period: str | None,
) -> dict[str, Any]:
    ncm = str(record.get("ncm") or "")
    description = str(record.get("description") or "").strip()
    review: dict[str, Any] = {
        "status": "INCONCLUSIVE",
        "basis": "XML_DESCRIPTION_ONLY",
        "suspected_field": None,
        "reported_ncm": ncm or None,
        "approved_ncm": None,
        "evidence_ref": None,
        "reason_codes": [],
    }
    if not description or re.fullmatch(r"\d{8}", ncm) is None:
        review["status"] = "UNVERIFIABLE"
        review["suspected_field"] = "NCM" if description else None
        review["reason_codes"] = ["DESCRIPTION_OR_NCM_UNAVAILABLE"]
        return review
    official = ncm_catalog.get(ncm)
    if official is None:
        review["status"] = "UNVERIFIABLE"
        review["suspected_field"] = "NCM"
        review["reason_codes"] = ["NCM_NOT_EFFECTIVE"]
        return review
    period_start = None
    period_end = None
    if period and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        year, month = (int(value) for value in period.split("-"))
        period_start = date(year, month, 1)
        period_end = date(year, month, calendar.monthrange(year, month)[1])
    effective_from = date.fromisoformat(official["effective_from"])
    effective_to = date.fromisoformat(official["effective_to"])
    if period_start is not None and not (
        effective_from <= period_end and effective_to >= period_start
    ):
        review["status"] = "UNVERIFIABLE"
        review["suspected_field"] = "NCM"
        review["reason_codes"] = ["NCM_NOT_EFFECTIVE"]
        return review
    review["basis"] = "OFFICIAL_NCM_TEXT"
    review["reason_codes"] = ["DESCRIPTION_REVIEW_PENDING_TECHNICAL_EVIDENCE"]
    review["official_description"] = official["description"]
    return review


def _load_product_ncm_catalog(folder: Path) -> tuple[dict[str, str], dict[str, Any]]:
    path = folder / PRODUCT_NCM_CATALOG
    digest = _catalog_digest(path)
    if digest is None:
        return {}, {"status": "ABSENT", "approved_entries": 0, "source_hash": None}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(4096)
            stream.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.DictReader(stream, delimiter=delimiter)
            headers = set(reader.fieldnames or [])
            required = {"codigo_produto", "ncm_aprovado", "status"}
            if not required.issubset(headers):
                raise ValidationError(
                    "catalogo-produtos-ncm.csv exige codigo_produto, ncm_aprovado e status"
                )
            catalog: dict[str, str] = {}
            for line_number, row in enumerate(reader, start=2):
                product_code = (row.get("codigo_produto") or "").strip()
                approved_ncm = re.sub(r"\D", "", row.get("ncm_aprovado") or "")
                status = (row.get("status") or "").strip().upper()
                if status != "APROVADO":
                    continue
                if not product_code or re.fullmatch(r"\d{8}", approved_ncm) is None:
                    raise ValidationError(
                        f"catalogo-produtos-ncm.csv possui linha APROVADO inválida: {line_number}"
                    )
                previous = catalog.get(product_code)
                if previous is not None and previous != approved_ncm:
                    raise ValidationError(
                        "catalogo-produtos-ncm.csv possui mais de um NCM aprovado para o mesmo produto"
                    )
                catalog[product_code] = approved_ncm
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValidationError(
            "catalogo-produtos-ncm.csv deve ser CSV UTF-8 válido"
        ) from error
    return catalog, {
        "status": "LOADED",
        "approved_entries": len(catalog),
        "source_hash": digest,
    }


def _apply_product_ncm_policy(
    record: dict[str, Any], catalog: dict[str, str], catalog_loaded: bool
) -> None:
    findings = record["findings"]
    ncm = record.get("ncm")
    product_code = record.get("product_code")
    validation = {"status": "INCONCLUSIVE", "source": "DOCUMENT_ONLY"}
    if not ncm or re.fullmatch(r"\d{8}", ncm) is None:
        validation["status"] = "UNVERIFIABLE"
    elif not catalog_loaded:
        findings.append(
            _finding("PRODUCT_NCM_CATALOG_ABSENT", "product_ncm", "OBSERVATION")
        )
    elif not product_code or product_code not in catalog:
        findings.append(
            _finding(
                "PRODUCT_NCM_CATALOG_ENTRY_MISSING",
                "product_ncm",
                "OBSERVATION",
            )
        )
    elif catalog[product_code] == ncm:
        validation = {"status": "VALIDATED", "source": "ANALYST_APPROVED_CATALOG"}
    else:
        validation = {"status": "MISMATCH", "source": "ANALYST_APPROVED_CATALOG"}
        findings.append(_finding("PRODUCT_NCM_MISMATCH", "product_ncm", "RESTRICTION"))
    record["product_ncm_validation"] = validation
    review = record.get("ncm_description_review")
    if not isinstance(review, dict):
        review = {
            "status": "INCONCLUSIVE",
            "basis": "XML_DESCRIPTION_ONLY",
            "suspected_field": None,
            "reported_ncm": ncm or None,
            "approved_ncm": None,
            "evidence_ref": None,
            "reason_codes": [],
        }
    if catalog_loaded and product_code and product_code in catalog:
        review["basis"] = "ANALYST_APPROVED_CATALOG"
        review["approved_ncm"] = catalog[product_code]
        if ncm == catalog[product_code]:
            review["status"] = "ANALYST_CONFIRMED_MATCH"
            review["suspected_field"] = None
            review["reason_codes"] = ["CATALOG_NCM_MATCH"]
        else:
            review["status"] = "ANALYST_CONFIRMED_MISMATCH"
            review["suspected_field"] = "NCM"
            review["reason_codes"] = ["PRODUCT_NCM_MISMATCH"]
    record["ncm_description_review"] = review
    restriction_codes = sorted(
        finding["code"] for finding in findings if finding["severity"] == "RESTRICTION"
    )
    record["restriction_codes"] = restriction_codes
    record["eligible_for_uc003"] = not restriction_codes
    record["content_status"] = _content_status(findings)


def _tax_detail(container: Any | None) -> Any | None:
    if container is None:
        return None
    return next(iter(list(container)), None)


def _ibs_cbs(element: Any) -> tuple[str | None, str | None, dict[str, str | None]]:
    group = _first_element(element, {"IBSCBS", "gIBSCBS"})
    if group is None:
        return (
            None,
            None,
            {
                "base_amount": None,
                "ibs_uf_rate": None,
                "ibs_municipal_rate": None,
                "cbs_rate": None,
            },
        )
    return (
        _text(group, {"CST"}),
        _text(group, {"cClassTrib"}),
        {
            "base_amount": _number(_text(group, {"vBCIBSCBS", "vBC"})),
            "ibs_uf_rate": _number(_text(group, {"pIBSUF"})),
            "ibs_municipal_rate": _number(_text(group, {"pIBSMun"})),
            "cbs_rate": _number(_text(group, {"pCBS"})),
        },
    )


def _document_total_components(info: Any) -> dict[str, Any]:
    """Read the official NF-e ``vNF`` composition from document totals.

    Optional monetary tags absent from ``ICMSTot`` are treated as zero by the
    NF-e rule. Their raw presence remains visible in ``components`` so a
    reviewer can distinguish an explicit zero from an unavailable mandatory
    total such as ``vProd`` or ``vNF``.
    """

    totals = _first_element(info, {"ICMSTot"})
    issqn_totals = _first_element(info, {"ISSQNtot"})
    components: dict[str, str | None] = {}
    expected = Decimal(0)
    missing_required: list[str] = []
    direct_vehicle = _direct_text(_direct_child(info, "ide"), "tpOp") == "2"
    excluded_for_rule = {"vST", "vFCPST", "vIPIDevol"} if direct_vehicle else set()

    for tag, name, sign, container_name in VNF_COMPONENT_FIELDS:
        container = totals if container_name == "ICMSTot" else issqn_totals
        value = _number(_text(container, {tag}))
        components[name] = value
        if value is not None and tag not in excluded_for_rule:
            expected += sign * (_parse_decimal(value) or Decimal(0))

    declared_vnf = _number(_text(totals, {"vNF"}))
    if components["product"] is None:
        missing_required.append("vProd")
    if declared_vnf is None:
        missing_required.append("vNF")

    declared_value = _parse_decimal(declared_vnf)
    no_deson_expected = expected + (
        _parse_decimal(components["icms_exempt"]) or Decimal(0)
    )
    if missing_required:
        status = "UNAVAILABLE"
        expected_vnf = None
        difference = None
        rule = "FATURAMENTO_DIRETO" if direct_vehicle else "PADRAO"
    elif (
        not direct_vehicle
        and components["icms_exempt"] is not None
        and declared_value == no_deson_expected
    ):
        # The validation rules tolerate a vNF that does not subtract
        # vICMSDeson. Preserve that accepted representation instead of
        # manufacturing a residual for a document that is internally coherent.
        expected_vnf = _format_decimal(no_deson_expected)
        difference = _format_decimal(declared_value - no_deson_expected)
        status = "MATCHED"
        rule = "PADRAO_SEM_DEDUCAO_ICMS_DESON"
    else:
        expected_vnf = _format_decimal(expected)
        difference = _format_decimal((declared_value or Decimal(0)) - expected)
        status = "MATCHED" if difference == "0.00" else "MISMATCH"
        rule = "FATURAMENTO_DIRETO" if direct_vehicle else "PADRAO"

    return {
        "declared_vnf": declared_vnf,
        "expected_vnf": expected_vnf,
        "difference": difference,
        "status": status,
        "rule": rule,
        "missing_required": missing_required,
        "components": components,
    }


def _base_record(
    document: dict[str, Any],
    validation_record: dict[str, Any],
    *,
    record_kind: str,
    item_number: int,
) -> dict[str, Any]:
    item_ref = _item_ref(document["document_ref"], record_kind, item_number)
    return {
        "schema": CONTENT_SCHEMA,
        "schema_version": CONTENT_SCHEMA_VERSION,
        "document_ref": document["document_ref"],
        "item_ref": item_ref,
        "source_hash": document["source_hash"],
        "document_type": document["document_type"],
        "analysis_scope": validation_record["analysis_scope"],
        "analysis_group": validation_record["analysis_group"],
        "direction": validation_record["direction"],
        "record_kind": record_kind,
        "item_number": item_number,
        "description": None,
        "product_code": None,
        "ean": None,
        "ncm": None,
        "cest": None,
        "cfop": None,
        "benefit_code": None,
        "service_list_code": None,
        "cnae": None,
        "municipal_tax_code": None,
        "nbs": None,
        "unit": None,
        "quantity": None,
        "unit_value": None,
        "gross_amount": None,
        "discount": None,
        "freight": None,
        "insurance": None,
        "other_expenses": None,
        "ipi_amount": None,
        "icms_st_amount": None,
        "icms_exempt_amount": None,
        "fcp_st_amount": None,
        "import_duty_amount": None,
        "ipi_returned_amount": None,
        "includes_document_total": None,
        "transport_modal": None,
        "nature_operation": None,
        "cclass_trib": None,
        "ibs_cbs_cst": None,
        "ibs_cbs": {
            "base_amount": None,
            "ibs_uf_rate": None,
            "ibs_municipal_rate": None,
            "cbs_rate": None,
        },
        "legacy_tax": {
            "icms_origin": None,
            "icms_cst": None,
            "icms_csosn": None,
            "pis_cst": None,
            "cofins_cst": None,
            "ipi_cst": None,
            "iss_retained": None,
            "iss_rate": None,
        },
        "components": [],
        "document_total_components": None,
        "referenced_document_count": 0,
        "findings": [],
        "content_status": "READY",
        "eligible_for_uc003": True,
        "restriction_codes": [],
        "product_ncm_validation": {
            "status": "NOT_APPLICABLE",
            "source": None,
        },
        "ncm_description_review": None,
    }


def _product_records(
    root: Any,
    document: dict[str, Any],
    validation_record: dict[str, Any],
    ncm_catalog: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    info = _first_element(root, {"infNFe"})
    if info is None:
        raise ValidationError("NF-e autorizada sem infNFe durante o UC-002")
    items = [item for item in info.iter() if _local_name(item.tag) == "det"]
    records: list[dict[str, Any]] = []
    item_amounts: list[Decimal] = []
    document_total_components = _document_total_components(info)
    document_nature_operation = _direct_text(_direct_child(info, "ide"), "natOp")
    for index, item in enumerate(items, start=1):
        item_number_raw = item.attrib.get("nItem", "")
        item_number = int(item_number_raw) if item_number_raw.isdigit() else index
        record = _base_record(
            document,
            validation_record,
            record_kind="PRODUCT",
            item_number=item_number,
        )
        product = _direct_child(item, "prod")
        tax = _direct_child(item, "imposto")
        icms = _first_element(tax, {"ICMS"})
        pis = _tax_detail(_first_element(tax, {"PIS"}))
        cofins = _tax_detail(_first_element(tax, {"COFINS"}))
        ipi = _first_element(tax, {"IPI"})
        ipi_detail = _tax_detail(ipi)
        ibs_cbs_cst, cclass_trib, ibs_cbs = _ibs_cbs(item)
        record.update(
            {
                "description": _direct_text(product, "xProd"),
                "product_code": _direct_text(product, "cProd"),
                "ean": _direct_text(product, "cEAN"),
                "ncm": _direct_text(product, "NCM"),
                "cest": _direct_text(product, "CEST"),
                "cfop": _direct_text(product, "CFOP"),
                "nature_operation": document_nature_operation,
                "benefit_code": _direct_text(product, "cBenef"),
                "unit": _direct_text(product, "uCom"),
                "quantity": _number(_direct_text(product, "qCom")),
                "unit_value": _number(_direct_text(product, "vUnCom")),
                "gross_amount": _number(_direct_text(product, "vProd")),
                "discount": _number(_direct_text(product, "vDesc")),
                "freight": _number(_direct_text(product, "vFrete")),
                "insurance": _number(_direct_text(product, "vSeg")),
                "other_expenses": _number(_direct_text(product, "vOutro")),
                "ipi_amount": _number(_text(ipi_detail, {"vIPI"})),
                "icms_st_amount": _number(_text(_tax_detail(icms), {"vICMSST"})),
                "icms_exempt_amount": _number(_text(_tax_detail(icms), {"vICMSDeson"})),
                "fcp_st_amount": _number(_text(_tax_detail(icms), {"vFCPST"})),
                "import_duty_amount": _number(
                    _text(_tax_detail(_first_element(tax, {"II"})), {"vII"})
                ),
                "ipi_returned_amount": _number(
                    _text(_first_element(tax, {"impostoDevol"}), {"vIPIDevol"})
                ),
                "includes_document_total": _direct_text(product, "indTot"),
                "document_total_components": document_total_components,
                "ncm_description_review": None,
                "cclass_trib": cclass_trib,
                "ibs_cbs_cst": ibs_cbs_cst,
                "ibs_cbs": ibs_cbs,
                "legacy_tax": {
                    "icms_origin": _text(_tax_detail(icms), {"orig"}),
                    "icms_cst": _text(_tax_detail(icms), {"CST"}),
                    "icms_csosn": _text(_tax_detail(icms), {"CSOSN"}),
                    "pis_cst": _text(pis, {"CST"}),
                    "cofins_cst": _text(cofins, {"CST"}),
                    "ipi_cst": _text(ipi_detail, {"CST"}),
                    "iss_retained": None,
                    "iss_rate": None,
                },
            }
        )
        findings: list[dict[str, str]] = []
        if not record["description"]:
            findings.append(
                _finding("DESCRIPTION_MISSING", "description", "OBSERVATION")
            )
        if not record["product_code"]:
            findings.append(
                _finding("PRODUCT_CODE_MISSING", "product_code", "OBSERVATION")
            )
        _validate_code(
            findings,
            record["ncm"],
            field="ncm",
            missing_code="NCM_MISSING",
            invalid_code="NCM_INVALID",
            pattern=r"\d{8}",
            missing_severity="RESTRICTION",
            invalid_severity="RESTRICTION",
        )
        _validate_code(
            findings,
            record["cfop"],
            field="cfop",
            missing_code="CFOP_MISSING",
            invalid_code="CFOP_INVALID",
            pattern=r"\d{4}",
        )
        if record["gross_amount"] is None:
            findings.append(
                _finding("GROSS_AMOUNT_INVALID", "gross_amount", "OBSERVATION")
            )
        _validate_code(
            findings,
            record["cclass_trib"],
            field="cclass_trib",
            missing_code="CCLASSTRIB_MISSING",
            invalid_code="CCLASSTRIB_INVALID",
            pattern=r"\d{6}",
        )
        record["findings"] = findings
        record["ncm_description_review"] = _ncm_description_review(
            record,
            ncm_catalog,
            validation_record.get("emission_period"),
        )
        if "NCM_NOT_EFFECTIVE" in record["ncm_description_review"]["reason_codes"]:
            findings.append(_finding("NCM_NOT_EFFECTIVE", "ncm", "RESTRICTION"))
        record["content_status"] = _content_status(findings)
        amount = _parse_decimal(record["gross_amount"])
        if amount is not None and record["includes_document_total"] != "0":
            item_amounts.append(amount)
        records.append(record)

    totals = _first_element(info, {"ICMSTot"})
    declared_total = _parse_decimal(_text(totals, {"vProd"}))
    calculated_total = sum(item_amounts, Decimal(0))
    if declared_total is None:
        reconciliation_status = "UNAVAILABLE"
        difference = None
    else:
        difference = calculated_total - declared_total
        reconciliation_status = "MATCHED" if difference == 0 else "MISMATCH"
    reconciliation = {
        "document_ref": document["document_ref"],
        "status": reconciliation_status,
        "calculated_content_total": _format_decimal(calculated_total),
        "declared_content_total": _format_decimal(declared_total),
        "difference": _format_decimal(difference),
        "document_total_components": document_total_components,
        "declared_document_total": document_total_components["declared_vnf"],
        "calculated_document_total": document_total_components["expected_vnf"],
        "document_total_difference": document_total_components["difference"],
        "document_total_status": document_total_components["status"],
    }
    return records, reconciliation


def _service_record(
    note: Any,
    document: dict[str, Any],
    validation_record: dict[str, Any],
) -> dict[str, Any]:
    record = _base_record(
        document,
        validation_record,
        record_kind="SERVICE",
        item_number=1,
    )
    service = _first_element(note, {"Servico"})
    ibs_cbs_cst, cclass_trib, ibs_cbs = _ibs_cbs(note)
    record.update(
        {
            "description": _text(service, {"Discriminacao"}),
            "service_list_code": _text(service, {"ItemListaServico"}),
            "cnae": _text(service, {"CodigoCnae"}),
            "municipal_tax_code": _text(service, {"CodigoTributacaoMunicipio"}),
            "nbs": _text(service, {"NBS", "CodigoNBS"}),
            "gross_amount": _number(_text(service, {"ValorServicos", "vServ"})),
            "cclass_trib": cclass_trib,
            "ibs_cbs_cst": ibs_cbs_cst,
            "ibs_cbs": ibs_cbs,
            "legacy_tax": {
                "icms_origin": None,
                "icms_cst": None,
                "icms_csosn": None,
                "pis_cst": None,
                "cofins_cst": None,
                "ipi_cst": None,
                "iss_retained": _text(note, {"IssRetido"}),
                "iss_rate": _number(_text(note, {"Aliquota"})),
            },
        }
    )
    findings: list[dict[str, str]] = []
    if not record["description"]:
        findings.append(_finding("DESCRIPTION_MISSING", "description", "OBSERVATION"))
    if not record["service_list_code"]:
        findings.append(
            _finding("SERVICE_LIST_CODE_MISSING", "service_list_code", "OBSERVATION")
        )
    _validate_code(
        findings,
        record["cnae"],
        field="cnae",
        missing_code="CNAE_MISSING",
        invalid_code="CNAE_INVALID",
        pattern=r"\d{7}",
    )
    if record["gross_amount"] is None:
        findings.append(_finding("GROSS_AMOUNT_INVALID", "gross_amount", "OBSERVATION"))
    if not record["nbs"]:
        findings.append(_finding("NBS_MISSING", "nbs", "OBSERVATION"))
    _validate_code(
        findings,
        record["cclass_trib"],
        field="cclass_trib",
        missing_code="CCLASSTRIB_MISSING",
        invalid_code="CCLASSTRIB_INVALID",
        pattern=r"\d{6}",
    )
    record["findings"] = findings
    record["content_status"] = _content_status(findings)
    return record


def _transport_record(
    info: Any,
    document: dict[str, Any],
    validation_record: dict[str, Any],
) -> dict[str, Any]:
    record = _base_record(
        document,
        validation_record,
        record_kind="TRANSPORT",
        item_number=1,
    )
    ibs_cbs_cst, cclass_trib, ibs_cbs = _ibs_cbs(info)
    components: list[dict[str, Any]] = []
    for index, component in enumerate(
        [item for item in info.iter() if _local_name(item.tag) == "Comp"],
        start=1,
    ):
        components.append(
            {
                "component_ref": _component_ref(record["item_ref"], index),
                "name": _text(component, {"xNome"}),
                "amount": _number(_text(component, {"vComp"})),
            }
        )
    record.update(
        {
            "description": _text(info, {"proPred"}),
            "cfop": _text(info, {"CFOP"}),
            "transport_modal": _text(info, {"modal"}),
            "nature_operation": _text(info, {"natOp"}),
            "gross_amount": _number(_text(info, {"vTPrest"})),
            "cclass_trib": cclass_trib,
            "ibs_cbs_cst": ibs_cbs_cst,
            "ibs_cbs": ibs_cbs,
            "components": components,
            "referenced_document_count": len(
                [item for item in info.iter() if _local_name(item.tag) == "infNFe"]
            ),
            "legacy_tax": {
                "icms_origin": _text(_first_element(info, {"ICMS"}), {"orig"}),
                "icms_cst": _text(_first_element(info, {"ICMS"}), {"CST"}),
                "icms_csosn": None,
                "pis_cst": None,
                "cofins_cst": None,
                "ipi_cst": None,
                "iss_retained": None,
                "iss_rate": None,
            },
        }
    )
    findings: list[dict[str, str]] = []
    if not record["description"]:
        findings.append(
            _finding("PREDOMINANT_PRODUCT_MISSING", "description", "OBSERVATION")
        )
    _validate_code(
        findings,
        record["cfop"],
        field="cfop",
        missing_code="CFOP_MISSING",
        invalid_code="CFOP_INVALID",
        pattern=r"\d{4}",
    )
    if not record["transport_modal"]:
        findings.append(
            _finding("TRANSPORT_MODAL_MISSING", "transport_modal", "OBSERVATION")
        )
    if not record["nature_operation"]:
        findings.append(
            _finding("NATURE_OPERATION_MISSING", "nature_operation", "OBSERVATION")
        )
    if record["gross_amount"] is None:
        findings.append(_finding("GROSS_AMOUNT_INVALID", "gross_amount", "OBSERVATION"))
    _validate_code(
        findings,
        record["cclass_trib"],
        field="cclass_trib",
        missing_code="CCLASSTRIB_MISSING",
        invalid_code="CCLASSTRIB_INVALID",
        pattern=r"\d{6}",
    )
    record["findings"] = findings
    record["content_status"] = _content_status(findings)
    return record


def _load_validation_result(folder: Path) -> dict[str, Any]:
    path = folder / "03_SAIDAS" / "validation-result.json"
    if not path.is_file():
        raise ValidationError(
            "UC-002 exige 03_SAIDAS/validation-result.json produzido pelo UC-001"
        )
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(
            "validation-result.json deve ser JSON UTF-8 válido"
        ) from error
    if (
        result.get("use_case") != "UC-001"
        or result.get("schema_version") != DOCUMENT_SCHEMA_VERSION
    ):
        raise ValidationError(
            "validation-result.json não pertence à versão vigente do UC-001"
        )
    if not result.get("gates", {}).get("planning_authorized"):
        raise ValidationError("UC-002 exige ao menos um escopo autorizado pelo UC-001")
    return result


def _xml_paths(folder: Path) -> list[Path]:
    structured = (folder / "00_CONTROLE" / "escopo.json").is_file() and (
        folder / "01_XML"
    ).is_dir()
    return (
        _safe_relative_files(folder / "01_XML", "*.xml")
        if structured
        else _raw_files(folder, ".xml")
    )


def _field_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    for kind, fields in FIELD_COVERAGE.items():
        selected = [record for record in records if record["record_kind"] == kind]
        coverage[kind] = {
            "records": len(selected),
            "fields": {
                field: {
                    "present": sum(
                        record.get(field) not in {None, ""} for record in selected
                    ),
                    "missing": sum(
                        record.get(field) in {None, ""} for record in selected
                    ),
                }
                for field in fields
            },
        }
    return coverage


def extract_content_folder(folder: Path | str) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta informada não existe")
    validation = _load_validation_result(base)
    ncm_catalog, ncm_snapshot = _load_ncm_snapshot()
    product_ncm_catalog, catalog_summary = _load_product_ncm_catalog(base)
    authorized_records = {
        record["document_ref"]: record
        for record in validation.get("documents", {}).get("records", [])
        if record.get("included")
        and record.get("authorized_for_planning")
        and record.get("operational_analysis_required")
    }
    if not authorized_records:
        raise ValidationError("UC-001 não produziu documentos com análise operacional")

    content_records: list[dict[str, Any]] = []
    reconciliations: list[dict[str, Any]] = []
    matched_document_refs: set[str] = set()
    source_hashes: set[str] = set()
    for path in _xml_paths(base):
        parsed_documents, _, _ = _parse_xml_file(path)
        selected_documents = [
            document
            for document in parsed_documents
            if document["document_ref"] in authorized_records
            and document["document_ref"] not in matched_document_refs
        ]
        if not selected_documents:
            continue
        try:
            root = SafeET.parse(path).getroot()
        except (OSError, ParseError, DefusedXmlException) as error:
            raise ValidationError(
                "XML autorizado ficou ilegível durante o UC-002"
            ) from error
        source_hashes.add(selected_documents[0]["source_hash"])
        if selected_documents[0]["document_type"] in {"NFE", "NFCE"}:
            document = selected_documents[0]
            records, reconciliation = _product_records(
                root,
                document,
                authorized_records[document["document_ref"]],
                ncm_catalog,
            )
            content_records.extend(records)
            reconciliations.append(reconciliation)
            matched_document_refs.add(document["document_ref"])
        elif selected_documents[0]["document_type"] == "NFSE":
            notes = [
                item
                for item in root.iter()
                if _local_name(item.tag).lower() == "infnfse"
            ]
            if len(notes) != len(parsed_documents):
                raise ValidationError(
                    "NFS-e consolidada não pôde ser alinhada no UC-002"
                )
            for document, note in zip(parsed_documents, notes, strict=True):
                if document["document_ref"] not in authorized_records:
                    continue
                content_records.append(
                    _service_record(
                        note, document, authorized_records[document["document_ref"]]
                    )
                )
                matched_document_refs.add(document["document_ref"])
        elif selected_documents[0]["document_type"] == "CTE":
            document = selected_documents[0]
            info = _first_element(root, {"infCte"})
            if info is None:
                raise ValidationError("CT-e autorizado sem infCte durante o UC-002")
            content_records.append(
                _transport_record(
                    info, document, authorized_records[document["document_ref"]]
                )
            )
            matched_document_refs.add(document["document_ref"])

    missing_refs = sorted(set(authorized_records) - matched_document_refs)
    if missing_refs:
        raise ValidationError(
            f"UC-002 não localizou {len(missing_refs)} documento(s) autorizado(s)"
        )
    content_records.sort(
        key=lambda record: (record["document_ref"], record["item_number"])
    )
    for record in content_records:
        if record["record_kind"] == "PRODUCT":
            _apply_product_ncm_policy(
                record,
                product_ncm_catalog,
                catalog_summary["status"] == "LOADED",
            )

    flattened_findings = [
        {
            "item_ref": record["item_ref"],
            "document_ref": record["document_ref"],
            **finding,
        }
        for record in content_records
        for finding in record["findings"]
    ]
    for reconciliation in reconciliations:
        if reconciliation["status"] == "MISMATCH":
            flattened_findings.append(
                {
                    "item_ref": None,
                    "document_ref": reconciliation["document_ref"],
                    "code": "DOCUMENT_PRODUCT_TOTAL_MISMATCH",
                    "field": "declared_content_total",
                    "severity": "OBSERVATION",
                }
            )
    blockers = [item for item in flattened_findings if item["severity"] == "BLOCKER"]
    restrictions = [
        item for item in flattened_findings if item["severity"] == "RESTRICTION"
    ]
    observations = [
        item
        for item in flattened_findings
        if item["severity"] in {"OBSERVATION", "REVIEW", "WARNING"}
    ]
    warnings = [item for item in flattened_findings if item["severity"] == "WARNING"]
    extraction_ready = bool(content_records) and not blockers
    eligible_records = sum(record["eligible_for_uc003"] for record in content_records)
    restricted_records = len(content_records) - eligible_records
    uc003_authorized = extraction_ready and eligible_records > 0
    classification_ready = extraction_ready and not observations and not restrictions
    status = (
        "CONTENT_BLOCKED"
        if not extraction_ready
        else "CONTENT_READY_WITH_RESTRICTIONS"
        if restrictions
        else "CONTENT_READY_WITH_OBSERVATIONS"
        if observations
        else "CONTENT_READY"
    )
    analysis_material = {
        "validation_id": validation["validation_id"],
        "document_refs": sorted(authorized_records),
        "source_hashes": sorted(source_hashes),
        "product_ncm_catalog_hash": catalog_summary["source_hash"],
        "ncm_snapshot_hash": ncm_snapshot["source_hash"],
        "schema_version": CONTENT_SCHEMA_VERSION,
    }
    content_analysis_id = (
        "CNT-"
        + hashlib.sha256(
            json.dumps(
                analysis_material, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        .hexdigest()[:16]
        .upper()
    )
    result = {
        "schema": CONTENT_SCHEMA,
        "schema_version": CONTENT_SCHEMA_VERSION,
        "use_case": "UC-002",
        "content_analysis_id": content_analysis_id,
        "validation_id": validation["validation_id"],
        "status": status,
        "scope": validation["scope"],
        "documents_selected": len(authorized_records),
        "records_total": len(content_records),
        "record_kind_counts": dict(
            sorted(Counter(record["record_kind"] for record in content_records).items())
        ),
        "document_type_counts": dict(
            sorted(
                Counter(record["document_type"] for record in content_records).items()
            )
        ),
        "analysis_group_counts": dict(
            sorted(
                Counter(record["analysis_group"] for record in content_records).items()
            )
        ),
        "content_status_counts": dict(
            sorted(
                Counter(record["content_status"] for record in content_records).items()
            )
        ),
        "uc003_eligibility": {
            "eligible_records": eligible_records,
            "restricted_records": restricted_records,
            "restriction_counts_by_scope": dict(
                sorted(
                    Counter(
                        record["analysis_scope"]
                        for record in content_records
                        if not record["eligible_for_uc003"]
                    ).items()
                )
            ),
        },
        "product_ncm_catalog": catalog_summary,
        "ncm_snapshot": ncm_snapshot,
        "ncm_description_status_counts": dict(
            sorted(
                Counter(
                    record["ncm_description_review"]["status"]
                    for record in content_records
                    if record["record_kind"] == "PRODUCT"
                    and isinstance(record.get("ncm_description_review"), dict)
                ).items()
            )
        ),
        "component_count": sum(len(record["components"]) for record in content_records),
        "referenced_document_count": sum(
            record["referenced_document_count"] for record in content_records
        ),
        "field_coverage": _field_coverage(content_records),
        "document_reconciliation": {
            "status_counts": dict(
                sorted(Counter(item["status"] for item in reconciliations).items())
            ),
            "records": reconciliations,
        },
        "gates": {
            "content_extraction_ready": extraction_ready,
            "uc003_analysis_authorized": uc003_authorized,
            "uc003_full_population_ready": extraction_ready and restricted_records == 0,
            "lcp214_classification_ready": classification_ready,
            "analyst_review_required": bool(observations or restrictions),
        },
        "blockers": blockers,
        "restrictions": restrictions,
        "observations": observations,
        "review_findings": observations,
        "warnings": warnings,
        "source_hashes": sorted(source_hashes),
        "limitations": [
            "O UC-002 avalia presença, formato e coerência do conteúdo; não conclui tratamento tributário.",
            "NCM, NBS, CNAE ou descrição isolados não determinam cClassTrib ou direito a crédito.",
            "Observações não impedem o UC-003; restrições Produto x NCM afetam somente os itens correspondentes.",
            "A comparação semântica Produto x NCM só é conclusiva contra catálogo APROVADO pelo analista.",
            "Descrições comerciais permanecem somente no JSONL local restrito.",
            "Tabelas legais e técnicas da LCP 214 serão aplicadas no UC-003.",
        ],
        "_private_records": content_records,
    }
    return result


def _markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Relatório de Qualidade do Conteúdo Fiscal",
        "",
        f"- Análise de conteúdo: `{result['content_analysis_id']}`",
        f"- Validação documental: `{result['validation_id']}`",
        f"- Situação: `{result['status']}`",
        f"- Documentos selecionados: {result['documents_selected']}",
        f"- Registros normalizados: {result['records_total']}",
        f"- Registros liberados para UC-003: {result['uc003_eligibility']['eligible_records']}",
        f"- Registros restritos: {result['uc003_eligibility']['restricted_records']}",
        f"- Componentes de CT-e: {result['component_count']}",
        f"- Catálogo Produto × NCM: `{result['product_ncm_catalog']['status']}`",
        "",
        "## Registros por tipo",
        "",
        "| Tipo | Registros |",
        "|---|---:|",
    ]
    for kind, count in result["record_kind_counts"].items():
        lines.append(f"| `{kind}` | {count} |")
    lines.extend(
        [
            "",
            "## Grupos operacionais",
            "",
            "| Grupo | Registros |",
            "|---|---:|",
        ]
    )
    for group, count in result["analysis_group_counts"].items():
        lines.append(f"| `{group}` | {count} |")
    lines.extend(["", "## Cobertura de campos", ""])
    for kind, coverage in result["field_coverage"].items():
        if coverage["records"] == 0:
            continue
        lines.extend(
            [
                f"### {kind}",
                "",
                "| Campo | Presente | Ausente |",
                "|---|---:|---:|",
            ]
        )
        for field, counts in coverage["fields"].items():
            lines.append(f"| `{field}` | {counts['present']} | {counts['missing']} |")
        lines.append("")
    finding_counts = Counter(
        finding["code"]
        for category in ("blockers", "restrictions", "observations")
        for finding in result[category]
    )
    lines.extend(
        [
            "## Achados",
            "",
            "| Código | Ocorrências |",
            "|---|---:|",
        ]
    )
    if finding_counts:
        for code, count in sorted(finding_counts.items()):
            lines.append(f"| `{code}` | {count} |")
    else:
        lines.append("| `NONE` | 0 |")
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- Extração pronta: `{str(result['gates']['content_extraction_ready']).lower()}`",
            f"- UC-003 autorizado: `{str(result['gates']['uc003_analysis_authorized']).lower()}`",
            f"- População integral pronta: `{str(result['gates']['uc003_full_population_ready']).lower()}`",
            f"- Completude classificatória LCP 214: `{str(result['gates']['lcp214_classification_ready']).lower()}`",
            f"- Revisão do analista necessária: `{str(result['gates']['analyst_review_required']).lower()}`",
            "",
            "## Limitações",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def _ncm_review_queue(records: list[dict[str, Any]]) -> str:
    columns = [
        "item_ref",
        "document_ref",
        "reported_ncm",
        "status",
        "suspected_field",
        "reason_codes",
        "approved_ncm",
        "evidence_ref",
        "observacao",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter=";", lineterminator="\n"
    )
    writer.writeheader()
    for record in records:
        review = record.get("ncm_description_review")
        if record.get("record_kind") != "PRODUCT" or not isinstance(review, dict):
            continue
        writer.writerow(
            {
                "item_ref": record["item_ref"],
                "document_ref": record["document_ref"],
                "reported_ncm": review.get("reported_ncm") or "",
                "status": review.get("status") or "INCONCLUSIVE",
                "suspected_field": review.get("suspected_field") or "",
                "reason_codes": ",".join(review.get("reason_codes") or []),
                "approved_ncm": review.get("approved_ncm") or "",
                "evidence_ref": review.get("evidence_ref") or "",
                "observacao": "",
            }
        )
    return stream.getvalue()


def write_content_outputs(
    result: dict[str, Any], output_dir: Path | str
) -> tuple[Path, Path, Path, Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    summary_path = target / "content-summary.json"
    records_path = target / "normalized-items.local.jsonl"
    report_path = target / "relatorio-qualidade-conteudo.md"
    queue_path = target / "fila-revisao-ncm-descricao.csv"
    ncm_review_path = target / "ncm-description-review.local.jsonl"
    public_result = {
        key: value for key, value in result.items() if not key.startswith("_private_")
    }
    summary_path.write_text(
        json.dumps(public_result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    records_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in result["_private_records"]
        ),
        encoding="utf-8",
    )
    queue_path.write_text(
        _ncm_review_queue(result["_private_records"]), encoding="utf-8-sig"
    )
    ncm_review_path.write_text(
        "".join(
            json.dumps(
                {
                    "item_ref": record["item_ref"],
                    "document_ref": record["document_ref"],
                    "description": record.get("description"),
                    "ncm_description_review": record.get("ncm_description_review"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for record in result["_private_records"]
            if record.get("record_kind") == "PRODUCT"
        ),
        encoding="utf-8",
    )
    report_path.write_text(_markdown_report(result), encoding="utf-8")
    return summary_path, records_path, report_path, queue_path, ncm_review_path
