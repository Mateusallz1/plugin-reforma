from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
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

COUNTERPARTY_SCHEMA = (
    "br.com.planejamento-reforma-tributaria/counterparty-regime-review"
)
COUNTERPARTY_SCHEMA_VERSION = "1.2.0"
SUPPLIER_LOCAL_FILE = "fornecedores-regime.local.jsonl"
SUPPLIER_PRODUCTS_LOCAL_FILE = "fornecedores-produtos.local.jsonl"
SUPPLIER_PRODUCTS_REPORT_FILE = "fornecedores-produtos.local.md"
CUSTOMER_LOCAL_FILE = "clientes-cnpj-regime.local.jsonl"
SUPPLIER_SUMMARY_FILE = "fornecedores-regime-summary.json"
CUSTOMER_SUMMARY_FILE = "clientes-cnpj-regime-summary.json"
MEETING_REPORT_FILE = "contrapartes-regime.local.md"
DEFAULT_REGISTRY = Path("00_CONTROLE") / "simples-registry.local.jsonl"
PERIOD_PATTERN = re.compile(r"20\d{2}-(0[1-9]|1[0-2])")


def _digits(value: Any) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _money(value: Any) -> str:
    return _format_decimal(_parse_decimal(value) or Decimal(0)) or "0.00"


def _quantity(value: Any) -> str:
    parsed = _parse_decimal(value) or Decimal(0)
    return format(parsed.quantize(Decimal("0.0001")), "f")


def _percent(value: Decimal, total: Decimal) -> str:
    if total == 0:
        return "0.0000"
    return format((value * Decimal(100) / total).quantize(Decimal("0.0001")), "f")


def _party_label(name: Any, cnpj: Any) -> str:
    normalized_name = " ".join(str(name or "").split()) or "SEM NOME"
    return f"{normalized_name} + {_digits(cnpj)}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"UC-003D exige {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} deve ser JSON UTF-8 válido") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} deve conter um objeto JSON")
    return value


def _xml_paths(folder: Path) -> list[Path]:
    structured = (folder / "00_CONTROLE" / "escopo.json").is_file() and (
        folder / "01_XML"
    ).is_dir()
    return (
        _safe_relative_files(folder / "01_XML", "*.xml")
        if structured
        else _raw_files(folder, ".xml")
    )


def _text(element: Any | None, names: set[str]) -> str | None:
    if element is None:
        return None
    wanted = {name.casefold() for name in names}
    for candidate in element.iter():
        if _local_name(candidate.tag).casefold() in wanted and candidate.text:
            value = candidate.text.strip()
            if value:
                return value
    return None


def _direct_text(element: Any | None, name: str) -> str | None:
    if element is None:
        return None
    for child in list(element):
        if _local_name(child.tag).casefold() == name.casefold() and child.text:
            value = child.text.strip()
            return value or None
    return None


def _nfe_crt(root: Any, document_key: str) -> str | None:
    for nfe in (
        candidate for candidate in root.iter() if _local_name(candidate.tag) == "NFe"
    ):
        info = next(
            (
                candidate
                for candidate in nfe.iter()
                if _local_name(candidate.tag) == "infNFe"
            ),
            None,
        )
        if info is None:
            continue
        key = _digits(info.attrib.get("Id", ""))
        if document_key and key and key != _digits(document_key):
            continue
        emit = next(
            (
                candidate
                for candidate in info.iter()
                if _local_name(candidate.tag) == "emit"
            ),
            None,
        )
        crt = _direct_text(emit, "CRT")
        if crt:
            return crt
    return None


def _generic_issuer_regime(
    root: Any, document_type: str
) -> tuple[str | None, str | None]:
    if document_type in {"NFE", "NFCE", "CTE"}:
        for candidate in root.iter():
            if _local_name(candidate.tag) in {"emit", "Emit"}:
                crt = _direct_text(candidate, "CRT")
                if crt:
                    return crt, "DOCUMENT_CRT"
    optante = _text(
        root,
        {"OptanteSimplesNacional", "OptanteSimples", "OptantePeloSimples"},
    )
    if optante:
        normalized = _digits(optante) or optante.strip().upper()
        if normalized in {"1", "S", "SIM", "TRUE"}:
            return "OPTANTE_SIMPLES", "DOCUMENT_NFSE_OPTANTE"
        if normalized in {"0", "2", "N", "NAO", "NÃO", "FALSE"}:
            return "NAO_OPTANTE_SIMPLES", "DOCUMENT_NFSE_OPTANTE"
    return None, None


def _document_regime_evidence(
    folder: Path, documents: dict[str, dict[str, Any]]
) -> dict[str, list[tuple[str, str]]]:
    evidence: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for path in _xml_paths(folder):
        try:
            parsed, _, _ = _parse_xml_file(path)
            root = SafeET.parse(path).getroot()
        except (OSError, ParseError, DefusedXmlException, ValidationError):
            continue
        for document in parsed:
            selected = documents.get(document.get("document_ref"))
            if selected is None:
                continue
            value: str | None = None
            source: str | None = None
            if selected.get("document_type") in {"NFE", "NFCE"}:
                value = _nfe_crt(root, str(document.get("document_key") or ""))
                source = "DOCUMENT_CRT" if value else None
            if value is None:
                value, source = _generic_issuer_regime(
                    root, str(selected.get("document_type") or "")
                )
            if value and source:
                evidence[selected["document_ref"]].append((value, source))
        if len(parsed) == 1:
            selected = documents.get(parsed[0].get("document_ref"))
            if selected is not None and not evidence.get(selected["document_ref"]):
                value, source = _generic_issuer_regime(
                    root, str(selected.get("document_type") or "")
                )
                if value and source:
                    evidence[selected["document_ref"]].append((value, source))
    return evidence


def _document_party_details(
    folder: Path, documents: dict[str, dict[str, Any]]
) -> dict[str, dict[str, str]]:
    parties: dict[str, dict[str, str]] = {}
    for path in _xml_paths(folder):
        try:
            parsed, _, _ = _parse_xml_file(path)
        except (OSError, ValidationError):
            continue
        for document in parsed:
            document_ref = document.get("document_ref")
            if document_ref not in documents:
                continue
            parties[document_ref] = {
                "issuer_id": _digits(document.get("issuer_id")),
                "issuer_name": str(document.get("issuer_name") or ""),
                "recipient_id": _digits(document.get("recipient_id")),
                "recipient_name": str(document.get("recipient_name") or ""),
            }
    return parties


def _own_taxpayer_ids(scope_identity: dict[str, Any]) -> set[str]:
    if not isinstance(scope_identity, dict):
        raise ValidationError("A identidade do estabelecimento deve ser um objeto")
    taxpayers = scope_identity.get("entity_taxpayer_ids")
    if not isinstance(taxpayers, list) or not taxpayers:
        raise ValidationError(
            "A identidade do estabelecimento deve conter ao menos um CNPJ"
        )
    normalized = {_digits(value) for value in taxpayers}
    if any(len(value) != 14 for value in normalized):
        raise ValidationError("A identidade do estabelecimento contém um CNPJ inválido")
    return normalized


def _load_acquisition_items(folder: Path) -> tuple[list[dict[str, Any]], str]:
    path = folder / "05_REVISAO_AQUISICOES" / "acquisition-items.local.jsonl"
    if not path.is_file():
        return [], "NOT_AVAILABLE"
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValidationError(
                    f"{path.name} possui linha inválida: {line_number}"
                )
            records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(
            "acquisition-items.local.jsonl deve ser JSONL UTF-8 válido"
        ) from error
    return records, "AVAILABLE"


def _product_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("product_code") or "").strip(),
        str(record.get("ncm") or "").strip(),
        " ".join(str(record.get("description") or "").split()).casefold(),
    )


def _supplier_product_mix(
    suppliers: list[dict[str, Any]],
    supplier_inputs: list[dict[str, Any]],
    acquisition_items: list[dict[str, Any]],
    product_basis_status: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    supplier_by_document = {
        record["document_ref"]: _digits(record.get("party_id"))
        for record in supplier_inputs
        if record.get("document_ref") and len(_digits(record.get("party_id"))) == 14
    }
    grouped: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "product_code": "",
                "ncm": "",
                "description": "",
                "units_observed": set(),
                "item_count": 0,
                "quantity": Decimal(0),
                "item_total": Decimal(0),
            }
        )
    )
    for item in acquisition_items:
        if (
            item.get("direction") != "ENTRADA"
            or item.get("record_kind") != "PRODUCT"
            or item.get("eligible_for_uc003") is not True
            or item.get("purchase_operation_status") != "PURCHASE_CONTEXT"
        ):
            continue
        supplier_cnpj = supplier_by_document.get(item.get("document_ref"))
        if not supplier_cnpj:
            continue
        key = _product_key(item)
        product = grouped[supplier_cnpj][key]
        product["product_code"] = str(item.get("product_code") or "").strip()
        product["ncm"] = str(item.get("ncm") or "").strip()
        product["description"] = " ".join(str(item.get("description") or "").split())
        unit = str(item.get("unit") or "").strip()
        if unit:
            product["units_observed"].add(unit)
        product["item_count"] += 1
        product["quantity"] += _parse_decimal(item.get("quantity")) or Decimal(0)
        product["item_total"] += _parse_decimal(item.get("gross_amount")) or Decimal(0)

    product_totals = {
        supplier_cnpj: sum(
            (item["item_total"] for item in products.values()), Decimal(0)
        )
        for supplier_cnpj, products in grouped.items()
    }
    portfolio_total = sum(product_totals.values(), Decimal(0))
    product_mix: list[dict[str, Any]] = []
    for supplier in suppliers:
        cnpj = supplier["cnpj"]
        products = []
        for product in sorted(
            grouped.get(cnpj, {}).values(),
            key=lambda item: (
                -item["item_total"],
                item["description"].casefold(),
                item["product_code"],
                item["ncm"],
            ),
        ):
            products.append(
                {
                    "product_code": product["product_code"],
                    "ncm": product["ncm"],
                    "description": product["description"],
                    "units_observed": sorted(product["units_observed"]),
                    "item_count": product["item_count"],
                    "quantity": _quantity(product["quantity"]),
                    "item_total": _money(product["item_total"]),
                    "share_of_supplier_products": _percent(
                        product["item_total"], product_totals.get(cnpj, Decimal(0))
                    ),
                    "share_of_portfolio_products": _percent(
                        product["item_total"], portfolio_total
                    ),
                }
            )
        supplier_total = product_totals.get(cnpj, Decimal(0))
        product_mix.append(
            {
                "schema": COUNTERPARTY_SCHEMA,
                "schema_version": COUNTERPARTY_SCHEMA_VERSION,
                "role": "SUPPLIER_PRODUCT_MIX",
                "party_type": "CNPJ",
                "cnpj": cnpj,
                "name": supplier["name"],
                "name_cnpj": _party_label(supplier["name"], cnpj),
                "competence": supplier["competence"],
                "simples_status": supplier["simples_status"],
                "document_count": supplier["document_count"],
                "document_total": supplier["document_total"],
                "product_line_count": sum(item["item_count"] for item in products),
                "product_distinct_count": len(products),
                "product_total": _money(supplier_total),
                "share_of_portfolio_products": _percent(
                    supplier_total, portfolio_total
                ),
                "products": products,
            }
        )

    by_status: dict[str, dict[str, Any]] = {}
    for supplier in product_mix:
        status = supplier["simples_status"]
        group = by_status.setdefault(
            status,
            {
                "supplier_count": 0,
                "supplier_count_with_products": 0,
                "product_line_count": 0,
                "product_distinct_count": 0,
                "product_total": Decimal(0),
            },
        )
        group["supplier_count"] += 1
        if supplier["product_line_count"]:
            group["supplier_count_with_products"] += 1
        group["product_line_count"] += supplier["product_line_count"]
        group["product_distinct_count"] += supplier["product_distinct_count"]
        group["product_total"] += _parse_decimal(supplier["product_total"]) or Decimal(
            0
        )
    summary = {
        "basis_status": product_basis_status,
        "supplier_count": len(product_mix),
        "supplier_count_with_products": sum(
            item["product_line_count"] > 0 for item in product_mix
        ),
        "product_line_count": sum(item["product_line_count"] for item in product_mix),
        "product_distinct_count": sum(
            item["product_distinct_count"] for item in product_mix
        ),
        "product_total": _money(portfolio_total),
        "by_simples_status": {
            status: {
                **values,
                "product_total": _money(values["product_total"]),
            }
            for status, values in sorted(by_status.items())
        },
    }
    return product_mix, summary


def _period_bounds(period: str) -> tuple[date, date]:
    if PERIOD_PATTERN.fullmatch(period) is None:
        raise ValidationError("A competência deve estar no formato AAAA-MM")
    year, month = (int(value) for value in period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _load_registry(
    folder: Path, registry_path: Path | str | None, period: str
) -> dict[str, dict[str, Any]]:
    path = (
        Path(registry_path).expanduser().resolve()
        if registry_path is not None
        else folder / DEFAULT_REGISTRY
    )
    if not path.is_file():
        return {}
    period_start, period_end = _period_bounds(period)
    result: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValidationError(
                    f"{path.name} possui linha inválida: {line_number}"
                )
            cnpj = _digits(row.get("cnpj"))
            status = str(row.get("status") or "").strip().upper()
            effective_from = str(row.get("effective_from") or "").strip()
            effective_to = str(row.get("effective_to") or "").strip()
            source = str(row.get("source") or "").strip()
            verified_at = str(row.get("verified_at") or "").strip()
            if (
                len(cnpj) != 14
                or status
                not in {
                    "OPTANTE_SIMPLES",
                    "NAO_OPTANTE_SIMPLES",
                    "INDETERMINADO",
                }
                or not effective_from
                or not effective_to
                or not source
                or not verified_at
            ):
                raise ValidationError(
                    f"{path.name} possui registro inválido: {line_number}"
                )
            start = date.fromisoformat(effective_from)
            end = date.fromisoformat(effective_to)
            date.fromisoformat(verified_at)
            if start <= period_end and end >= period_start:
                previous = result.get(cnpj)
                if previous is not None and previous["status"] != status:
                    result[cnpj] = {
                        "status": "DIVERGENTE_NO_PERIODO",
                        "source": "REGISTRY",
                    }
                else:
                    result[cnpj] = {
                        "status": status,
                        "source": source,
                    }
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, ValidationError):
            raise
        raise ValidationError(
            "O snapshot local de regime deve ser JSONL válido"
        ) from error
    return result


def _status_from_values(values: set[str]) -> str:
    if not values:
        return "UNKNOWN"
    if len(values) == 1:
        return next(iter(values))
    return "DIVERGENTE_NO_PERIODO"


def _crt_status(value: str) -> str | None:
    normalized = value.strip().upper()
    if normalized in {"OPTANTE_SIMPLES", "NAO_OPTANTE_SIMPLES"}:
        return normalized
    normalized = _digits(value)
    if normalized in {"1", "2", "4"}:
        return "OPTANTE_SIMPLES"
    if normalized == "3":
        return "NAO_OPTANTE_SIMPLES"
    return None


def _aggregate_party(
    records: list[dict[str, Any]],
    *,
    role: str,
    registry: dict[str, dict[str, Any]],
    document_evidence: dict[str, list[tuple[str, str]]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        cnpj = _digits(record.get("party_id"))
        if len(cnpj) != 14:
            continue
        entry = grouped.setdefault(
            cnpj,
            {
                "schema": COUNTERPARTY_SCHEMA,
                "schema_version": COUNTERPARTY_SCHEMA_VERSION,
                "role": role,
                "party_type": "CNPJ",
                "cnpj": cnpj,
                "name": record.get("party_name") or "",
                "names_observed": [],
                "competence": record["period"],
                "document_count": 0,
                "document_total": Decimal(0),
                "document_refs": [],
                "crt_values": set(),
                "evidence_sources": set(),
                "simples_status": "UNKNOWN",
            },
        )
        name = str(record.get("party_name") or "").strip()
        if name and name not in entry["names_observed"]:
            entry["names_observed"].append(name)
        entry["document_count"] += 1
        entry["document_total"] += _parse_decimal(
            record.get("gross_amount")
        ) or Decimal(0)
        entry["document_refs"].append(record["document_ref"])
        for value, source in document_evidence.get(record["document_ref"], []):
            entry["crt_values"].add(value)
            entry["evidence_sources"].add(source)

    result: list[dict[str, Any]] = []
    for cnpj, entry in sorted(grouped.items()):
        document_statuses = {
            status
            for value in entry["crt_values"]
            if (status := _crt_status(value)) is not None
        }
        registry_entry = registry.get(cnpj)
        registry_status = registry_entry.get("status") if registry_entry else None
        if registry_status:
            entry["evidence_sources"].add(
                registry_entry.get("source", "LOCAL_REGISTRY")
            )
        document_status = _status_from_values(document_statuses)
        if len(entry["crt_values"]) > 1:
            status = "DIVERGENTE_NO_PERIODO"
        elif registry_status and document_status not in {"UNKNOWN", registry_status}:
            status = "EVIDENCIA_CONFLITANTE"
        elif registry_status:
            status = registry_status
        else:
            status = document_status
        entry["simples_status"] = status
        result.append(
            {
                **entry,
                "name": entry["name"]
                or (min(entry["names_observed"]) if entry["names_observed"] else ""),
                "name_cnpj": _party_label(
                    entry["name"]
                    or (
                        min(entry["names_observed"]) if entry["names_observed"] else ""
                    ),
                    cnpj,
                ),
                "names_observed": sorted(entry["names_observed"]),
                "document_total": _money(entry["document_total"]),
                "document_refs": sorted(entry["document_refs"]),
                "crt_values": sorted(entry["crt_values"]),
                "evidence_sources": sorted(entry["evidence_sources"]),
            }
        )
    return result


def review_counterparties_folder(
    folder: Path | str,
    *,
    simples_registry_path: Path | str | None = None,
    scope_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta empresarial informada não existe")
    validation = _load_json(
        base / "03_SAIDAS" / "validation-result.json",
        "03_SAIDAS/validation-result.json",
    )
    if (
        validation.get("use_case") != "UC-001"
        or validation.get("schema_version") != DOCUMENT_SCHEMA_VERSION
        or not validation.get("gates", {}).get("planning_authorized")
    ):
        raise ValidationError("UC-003D exige validação documental vigente e autorizada")
    period = str(validation.get("scope", {}).get("period") or "")
    if scope_identity is None:
        scope_input = _load_json(
            base / "00_CONTROLE" / "escopo.json", "00_CONTROLE/escopo.json"
        )
    else:
        scope_input = scope_identity
    own_ids = _own_taxpayer_ids(scope_input)
    documents = {
        record["document_ref"]: record
        for record in validation.get("documents", {}).get("records", [])
        if record.get("included") and record.get("authorized_for_planning")
    }
    evidence = _document_regime_evidence(base, documents)
    parties = _document_party_details(base, documents)
    registry = _load_registry(base, simples_registry_path, period)
    supplier_inputs: list[dict[str, Any]] = []
    customer_inputs: list[dict[str, Any]] = []
    cpf_sales = 0
    cpf_total = Decimal(0)
    unidentified_sales = 0
    unidentified_total = Decimal(0)
    for document in documents.values():
        party = parties.get(document["document_ref"], {})
        party_id = party.get("issuer_id", "")
        if document.get("direction") == "ENTRADA" and party_id not in own_ids:
            supplier_inputs.append(
                {
                    "party_id": party_id,
                    "party_name": party.get("issuer_name", ""),
                    "gross_amount": document.get("gross_amount"),
                    "document_ref": document["document_ref"],
                    "period": period,
                }
            )
        if document.get("direction") != "SAIDA":
            continue
        party_id = party.get("recipient_id", "")
        if party_id in own_ids:
            continue
        amount = _parse_decimal(document.get("gross_amount")) or Decimal(0)
        if len(party_id) == 11:
            cpf_sales += 1
            cpf_total += amount
        elif len(party_id) == 14:
            customer_inputs.append(
                {
                    "party_id": party_id,
                    "party_name": party.get("recipient_name", ""),
                    "gross_amount": document.get("gross_amount"),
                    "document_ref": document["document_ref"],
                    "period": period,
                }
            )
        else:
            unidentified_sales += 1
            unidentified_total += amount

    suppliers = _aggregate_party(
        supplier_inputs,
        role="SUPPLIER",
        registry=registry,
        document_evidence=evidence,
    )
    customers = _aggregate_party(
        customer_inputs,
        role="CUSTOMER",
        registry=registry,
        # The CRT in a sales document identifies the issuer, not the
        # recipient. Customer regime requires the optional local registry.
        document_evidence={},
    )
    acquisition_items, product_basis_status = _load_acquisition_items(base)
    supplier_products, product_mix_summary = _supplier_product_mix(
        suppliers,
        supplier_inputs,
        acquisition_items,
        product_basis_status,
    )

    def public_by_status(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in items:
            status = item["simples_status"]
            summary = grouped.setdefault(
                status,
                {
                    "counterparty_count": 0,
                    "document_count": 0,
                    "document_total": Decimal(0),
                },
            )
            summary["counterparty_count"] += 1
            summary["document_count"] += item["document_count"]
            summary["document_total"] += _parse_decimal(
                item["document_total"]
            ) or Decimal(0)
        return {
            status: {
                **summary,
                "document_total": _money(summary["document_total"]),
            }
            for status, summary in sorted(grouped.items())
        }

    supplier_summary = {
        "schema": COUNTERPARTY_SCHEMA,
        "schema_version": COUNTERPARTY_SCHEMA_VERSION,
        "role": "SUPPLIER",
        "competence": period,
        "supplier_count": len(suppliers),
        "by_simples_status": public_by_status(suppliers),
        "product_mix": product_mix_summary,
        "registry_status": "LOADED" if registry else "ABSENT",
    }
    customer_summary = {
        "schema": COUNTERPARTY_SCHEMA,
        "schema_version": COUNTERPARTY_SCHEMA_VERSION,
        "role": "CUSTOMER",
        "competence": period,
        "cnpj_customer_count": len(customers),
        "cnpj_by_simples_status": public_by_status(customers),
        "sales_to_individuals": {
            "document_count": cpf_sales,
            "document_total": _money(cpf_total),
        },
        "sales_to_unidentified_recipients": {
            "document_count": unidentified_sales,
            "document_total": _money(unidentified_total),
        },
        "registry_status": "LOADED" if registry else "ABSENT",
    }
    return {
        "schema": COUNTERPARTY_SCHEMA,
        "schema_version": COUNTERPARTY_SCHEMA_VERSION,
        "use_case": "UC-003D",
        "scope": validation["scope"],
        "supplier_summary": supplier_summary,
        "customer_summary": customer_summary,
        "_private_suppliers": suppliers,
        "_private_supplier_products": supplier_products,
        "_private_customers": customers,
    }


def _meeting_report(result: dict[str, Any]) -> str:
    lines = [
        "# Apuração de contrapartes e regime",
        "",
        f"- Competência: `{result['scope']['period']}`",
        "- Documento de trabalho confidencial para reunião; valores são documentais.",
        "",
        "## Fornecedores",
        "",
        "| Empresa + CNPJ | Simples | Documentos | Valor documental |",
        "|---|---|---:|---:|",
    ]
    for item in result["_private_suppliers"]:
        lines.append(
            f"| {item['name_cnpj']} | {item['simples_status']} | {item['document_count']} | {item['document_total']} |"
        )
    lines.extend(
        [
            "",
            "## Clientes CNPJ",
            "",
            "| Empresa + CNPJ | Simples | Documentos | Valor documental |",
            "|---|---|---|---:|---:|",
        ]
    )
    for item in result["_private_customers"]:
        lines.append(
            f"| {item['name_cnpj']} | {item['simples_status']} | {item['document_count']} | {item['document_total']} |"
        )
    lines.extend(
        [
            "",
            "## Clientes pessoa física",
            "",
            f"- Quantidade de vendas para CPF: {result['customer_summary']['sales_to_individuals']['document_count']}",
            f"- Valor das vendas para CPF: {result['customer_summary']['sales_to_individuals']['document_total']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _supplier_products_report(result: dict[str, Any]) -> str:
    product_summary = result["supplier_summary"]["product_mix"]
    lines = [
        "# Produtos adquiridos por fornecedor",
        "",
        f"- Competência: `{result['scope']['period']}`",
        f"- Base de produtos: `{product_summary['basis_status']}`",
        f"- Valor total de produtos: {product_summary['product_total']}",
        "- Documento de trabalho confidencial; regime é evidência documental e não conclui crédito.",
        "",
    ]
    for supplier in result["_private_supplier_products"]:
        lines.extend(
            [
                f"## {supplier['name_cnpj']}",
                "",
                f"- Regime documental: `{supplier['simples_status']}`",
                f"- Valor documental do fornecedor: {supplier['document_total']}",
                f"- Valor dos produtos: {supplier['product_total']} ({supplier['share_of_portfolio_products']}% do total)",
                f"- Linhas de produto: {supplier['product_line_count']}; produtos distintos: {supplier['product_distinct_count']}",
                "",
            ]
        )
        if not supplier["products"]:
            lines.extend(
                [
                    "Nenhum produto elegível no recorte; os documentos podem ser serviço ou transporte.",
                    "",
                ]
            )
            continue
        lines.extend(
            [
                "| Código | NCM | Descrição | Quantidade | Valor | % do fornecedor |",
                "|---|---|---|---:|---:|---:|",
            ]
        )
        for product in supplier["products"]:
            description = (
                str(product["description"]).replace("|", "/").replace("\n", " ")
            )
            lines.append(
                f"| {product['product_code']} | {product['ncm']} | {description} | {product['quantity']} | {product['item_total']} | {product['share_of_supplier_products']}% |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def write_counterparty_outputs(
    result: dict[str, Any], folder: Path | str, *, meeting_report: bool = False
) -> list[Path]:
    base = Path(folder).expanduser().resolve()
    supplier_dir = base / "05_REVISAO_AQUISICOES"
    customer_dir = base / "06_REVISAO_RECEITAS"
    supplier_dir.mkdir(parents=True, exist_ok=True)
    customer_dir.mkdir(parents=True, exist_ok=True)
    supplier_summary_path = supplier_dir / SUPPLIER_SUMMARY_FILE
    supplier_local_path = supplier_dir / SUPPLIER_LOCAL_FILE
    supplier_products_path = supplier_dir / SUPPLIER_PRODUCTS_LOCAL_FILE
    customer_summary_path = customer_dir / CUSTOMER_SUMMARY_FILE
    customer_local_path = customer_dir / CUSTOMER_LOCAL_FILE
    supplier_summary_path.write_text(
        json.dumps(
            result["supplier_summary"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    supplier_local_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in result["_private_suppliers"]
        ),
        encoding="utf-8",
    )
    supplier_products_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in result["_private_supplier_products"]
        ),
        encoding="utf-8",
    )
    customer_summary_path.write_text(
        json.dumps(
            result["customer_summary"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    customer_local_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in result["_private_customers"]
        ),
        encoding="utf-8",
    )
    written = [
        supplier_summary_path,
        supplier_local_path,
        supplier_products_path,
        customer_summary_path,
        customer_local_path,
    ]
    if meeting_report:
        meeting_dir = base / "09_APRESENTACAO_CLIENTE"
        meeting_dir.mkdir(parents=True, exist_ok=True)
        meeting_path = meeting_dir / MEETING_REPORT_FILE
        meeting_path.write_text(_meeting_report(result), encoding="utf-8")
        written.append(meeting_path)
        products_report_path = meeting_dir / SUPPLIER_PRODUCTS_REPORT_FILE
        products_report_path.write_text(
            _supplier_products_report(result), encoding="utf-8"
        )
        written.append(products_report_path)
    return written
