from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .core import (
    ValidationError,
    _format_decimal,
    _local_name,
    _parse_decimal,
    _parse_xml_file,
    _raw_files,
    _safe_relative_files,
)

CONTENT_SCHEMA = "br.com.planejamento-reforma-tributaria/fiscal-content"
CONTENT_SCHEMA_VERSION = "1.0.0"

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
    missing_severity: str = "REVIEW",
) -> None:
    if not value:
        findings.append(_finding(missing_code, field, missing_severity))
    elif re.fullmatch(pattern, value) is None:
        findings.append(_finding(invalid_code, field, "REVIEW"))


def _content_status(findings: list[dict[str, str]]) -> str:
    severities = {finding["severity"] for finding in findings}
    if "BLOCKER" in severities:
        return "BLOCKED"
    if "REVIEW" in severities:
        return "REVIEW_REQUIRED"
    if "WARNING" in severities:
        return "READY_WITH_WARNINGS"
    return "READY"


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
        "other_expenses": None,
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
        "referenced_document_count": 0,
        "findings": [],
        "content_status": "READY",
    }


def _product_records(
    root: Any,
    document: dict[str, Any],
    validation_record: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    info = _first_element(root, {"infNFe"})
    if info is None:
        raise ValidationError("NF-e autorizada sem infNFe durante o UC-002")
    items = [item for item in info.iter() if _local_name(item.tag) == "det"]
    records: list[dict[str, Any]] = []
    item_amounts: list[Decimal] = []
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
                "benefit_code": _direct_text(product, "cBenef"),
                "unit": _direct_text(product, "uCom"),
                "quantity": _number(_direct_text(product, "qCom")),
                "unit_value": _number(_direct_text(product, "vUnCom")),
                "gross_amount": _number(_direct_text(product, "vProd")),
                "discount": _number(_direct_text(product, "vDesc")),
                "freight": _number(_direct_text(product, "vFrete")),
                "other_expenses": _number(_direct_text(product, "vOutro")),
                "includes_document_total": _direct_text(product, "indTot"),
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
            findings.append(_finding("DESCRIPTION_MISSING", "description", "BLOCKER"))
        if not record["product_code"]:
            findings.append(_finding("PRODUCT_CODE_MISSING", "product_code", "WARNING"))
        _validate_code(
            findings,
            record["ncm"],
            field="ncm",
            missing_code="NCM_MISSING",
            invalid_code="NCM_INVALID",
            pattern=r"\d{8}",
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
            findings.append(_finding("GROSS_AMOUNT_INVALID", "gross_amount", "BLOCKER"))
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
        amount = _parse_decimal(record["gross_amount"])
        if amount is not None and record["includes_document_total"] != "0":
            item_amounts.append(amount)
        records.append(record)

    declared_total = _parse_decimal(_text(_first_element(info, {"ICMSTot"}), {"vProd"}))
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
        findings.append(_finding("DESCRIPTION_MISSING", "description", "BLOCKER"))
    if not record["service_list_code"]:
        findings.append(
            _finding("SERVICE_LIST_CODE_MISSING", "service_list_code", "REVIEW")
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
        findings.append(_finding("GROSS_AMOUNT_INVALID", "gross_amount", "BLOCKER"))
    if not record["nbs"]:
        findings.append(_finding("NBS_MISSING", "nbs", "REVIEW"))
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
            _finding("PREDOMINANT_PRODUCT_MISSING", "description", "REVIEW")
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
            _finding("TRANSPORT_MODAL_MISSING", "transport_modal", "REVIEW")
        )
    if not record["nature_operation"]:
        findings.append(
            _finding("NATURE_OPERATION_MISSING", "nature_operation", "REVIEW")
        )
    if record["gross_amount"] is None:
        findings.append(_finding("GROSS_AMOUNT_INVALID", "gross_amount", "BLOCKER"))
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
    if result.get("use_case") != "UC-001":
        raise ValidationError("validation-result.json não pertence ao UC-001")
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
    authorized_records = {
        record["document_ref"]: record
        for record in validation.get("documents", {}).get("records", [])
        if record.get("authorized_for_planning")
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
                root, document, authorized_records[document["document_ref"]]
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
                    "severity": "BLOCKER",
                }
            )
    blockers = [item for item in flattened_findings if item["severity"] == "BLOCKER"]
    reviews = [item for item in flattened_findings if item["severity"] == "REVIEW"]
    warnings = [item for item in flattened_findings if item["severity"] == "WARNING"]
    extraction_ready = bool(content_records) and not blockers
    classification_ready = extraction_ready and not reviews
    status = (
        "CONTENT_BLOCKED"
        if not extraction_ready
        else "CONTENT_REVIEW_REQUIRED"
        if reviews
        else "CONTENT_READY_WITH_WARNINGS"
        if warnings
        else "CONTENT_READY"
    )
    analysis_material = {
        "validation_id": validation["validation_id"],
        "document_refs": sorted(authorized_records),
        "source_hashes": sorted(source_hashes),
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
            "lcp214_classification_ready": classification_ready,
            "analyst_review_required": bool(reviews),
        },
        "blockers": blockers,
        "review_findings": reviews,
        "warnings": warnings,
        "source_hashes": sorted(source_hashes),
        "limitations": [
            "O UC-002 avalia presença, formato e coerência do conteúdo; não conclui tratamento tributário.",
            "NCM, NBS, CNAE ou descrição isolados não determinam cClassTrib ou direito a crédito.",
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
        f"- Componentes de CT-e: {result['component_count']}",
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
        for category in ("blockers", "review_findings", "warnings")
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
            f"- Classificação LCP 214 pronta: `{str(result['gates']['lcp214_classification_ready']).lower()}`",
            f"- Revisão do analista necessária: `{str(result['gates']['analyst_review_required']).lower()}`",
            "",
            "## Limitações",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def write_content_outputs(
    result: dict[str, Any], output_dir: Path | str
) -> tuple[Path, Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    summary_path = target / "content-summary.json"
    records_path = target / "normalized-items.local.jsonl"
    report_path = target / "relatorio-qualidade-conteudo.md"
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
    report_path.write_text(_markdown_report(result), encoding="utf-8")
    return summary_path, records_path, report_path
