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
from pathlib import Path
from typing import Any

from .content import CONTENT_SCHEMA_VERSION
from .core import (
    DOCUMENT_SCHEMA_VERSION,
    ValidationError,
    _format_decimal,
    _parse_decimal,
)
from .operation_classification import classify_acquisition_product_item_with_reason
from .ruleset_integrity import verify_trusted_hash

ACQUISITION_SCHEMA = "br.com.planejamento-reforma-tributaria/acquisition-review"
ACQUISITION_SCHEMA_VERSION = "1.5.0"
DECISION_FILE = Path("00_CONTROLE") / "classificacao-aquisicoes.csv"
ACQUISITION_CATEGORIES = {
    "PRODUCT": "PURCHASE_GOODS",
    "SERVICE": "PURCHASE_SERVICES",
    "TRANSPORT": "PURCHASE_TRANSPORT",
}
ALLOWED_NATURES = {
    "PRODUCT": {
        "MERCADORIA_REVENDA",
        "INSUMO",
        "ATIVO_IMOBILIZADO",
        "USO_CONSUMO",
        "OUTRA_AQUISICAO",
    },
    "SERVICE": {
        "SERVICO_OPERACIONAL",
        "SERVICO_ADMINISTRATIVO",
        "SERVICO_ATIVO",
        "OUTRO_SERVICO",
    },
    "TRANSPORT": {
        "FRETE_COMPRA",
        "FRETE_VENDA",
        "TRANSPORTE_INTERNO",
        "OUTRO_TRANSPORTE",
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"UC-003 exige {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} deve ser JSON UTF-8 válido") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} deve conter um objeto JSON")
    return value


def _load_content_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValidationError("UC-003 exige 04_CONTEUDO/normalized-items.local.jsonl")
    records: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or not record.get("item_ref"):
                raise ValidationError(
                    f"normalized-items.local.jsonl possui linha inválida: {line_number}"
                )
            records.append(record)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(
            "normalized-items.local.jsonl deve ser JSONL UTF-8 válido"
        ) from error
    item_refs = [record["item_ref"] for record in records]
    if len(item_refs) != len(set(item_refs)):
        raise ValidationError("normalized-items.local.jsonl possui item_ref duplicado")
    return records


def _load_ruleset(path: Path) -> tuple[dict[str, Any], str]:
    ruleset = _load_json(path, "snapshot oficial de CST/cClassTrib")
    if ruleset.get("schema") != (
        "br.com.planejamento-reforma-tributaria/official-tax-snapshot"
    ):
        raise ValidationError("Snapshot oficial possui schema incompatível")
    records = ruleset.get("classification_records")
    if not isinstance(records, list) or not records:
        raise ValidationError("Snapshot oficial não contém classificações")
    digest = _sha256(path)
    verify_trusted_hash(path, digest, "snapshot oficial de CST/cClassTrib")
    return ruleset, digest


def _load_cfop_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    snapshot = _load_json(path, "snapshot oficial de CFOP")
    if snapshot.get("schema") != (
        "br.com.planejamento-reforma-tributaria/official-cfop-snapshot"
    ):
        raise ValidationError("Snapshot CFOP possui schema incompatível")
    if not isinstance(snapshot.get("records"), list) or not snapshot["records"]:
        raise ValidationError("Snapshot CFOP não contém registros")
    digest = _sha256(path)
    verify_trusted_hash(path, digest, "snapshot oficial de CFOP")
    return snapshot, digest


def _load_cfop_analyst_rules(path: Path) -> tuple[dict[str, Any], str]:
    rules = _load_json(path, "ruleset de receita do analista")
    if rules.get("schema") != (
        "br.com.planejamento-reforma-tributaria/revenue-cfop-rules"
    ):
        raise ValidationError("Ruleset de receita possui schema incompatível")
    for field in ("usual_sale_cfops", "sales_return_inbound_cfops"):
        values = rules.get(field)
        if not isinstance(values, list) or any(
            re.fullmatch(r"\d{4}", str(value)) is None for value in values
        ):
            raise ValidationError(f"Ruleset de receita possui {field} inválido")
    digest = _sha256(path)
    verify_trusted_hash(path, digest, "ruleset de receita do analista")
    return rules, digest


def _load_decisions(folder: Path) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    path = folder / DECISION_FILE
    if not path.is_file():
        return {}, {"status": "ABSENT", "approved_records": 0, "source_hash": None}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(4096)
            stream.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.DictReader(stream, delimiter=delimiter)
            required = {"item_ref", "natureza", "status", "aprovado_por"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValidationError(
                    "classificacao-aquisicoes.csv exige item_ref, natureza, status e aprovado_por"
                )
            decisions: dict[str, dict[str, str]] = {}
            for line_number, row in enumerate(reader, start=2):
                status = (row.get("status") or "").strip().upper()
                if status != "APROVADO":
                    continue
                item_ref = (row.get("item_ref") or "").strip()
                nature = (row.get("natureza") or "").strip().upper()
                approved_by = (row.get("aprovado_por") or "").strip()
                if not item_ref or not nature or not approved_by:
                    raise ValidationError(
                        f"classificacao-aquisicoes.csv possui linha APROVADO inválida: {line_number}"
                    )
                decision = {
                    "nature": nature,
                    "approved_by": approved_by,
                    "note": (row.get("observacao") or "").strip(),
                }
                if item_ref in decisions and decisions[item_ref] != decision:
                    raise ValidationError(
                        "classificacao-aquisicoes.csv possui decisões conflitantes"
                    )
                decisions[item_ref] = decision
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValidationError(
            "classificacao-aquisicoes.csv deve ser CSV UTF-8 válido"
        ) from error
    return decisions, {
        "status": "LOADED",
        "approved_records": len(decisions),
        "source_hash": _sha256(path),
    }


def _period_bounds(period: str) -> tuple[date, date]:
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period) is None:
        raise ValidationError("UC-003 exige competência AAAA-MM no conteúdo")
    year, month = (int(value) for value in period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _legal_evidence_status(
    record: dict[str, Any],
    pair_index: dict[tuple[str, str], dict[str, Any]],
    period_start: date,
    period_end: date,
) -> tuple[str, str | None]:
    cst = str(record.get("ibs_cbs_cst") or "").strip()
    cclass = str(record.get("cclass_trib") or "").strip()
    if not cst or not cclass:
        return "PENDING_EVIDENCE", None
    if re.fullmatch(r"\d{3}", cst) is None or re.fullmatch(r"\d{6}", cclass) is None:
        return "INVALID_DECLARED_PAIR", None
    rule = pair_index.get((cst, cclass))
    if rule is None:
        return "INVALID_DECLARED_PAIR", None
    document_type = record["document_type"]
    if rule.get("document_applicability", {}).get(document_type) != 1:
        return "PAIR_NOT_APPLICABLE_TO_DOCUMENT", rule.get("lc214_reference")
    effective_from = date.fromisoformat(rule["effective_from"])
    effective_to_raw = rule.get("effective_to")
    effective_to = date.fromisoformat(effective_to_raw) if effective_to_raw else None
    if effective_from > period_end or (
        effective_to is not None and effective_to < period_start
    ):
        return "OUT_OF_EFFECTIVE_DATE", rule.get("lc214_reference")
    return "CONFIRMED_DECLARED", rule.get("lc214_reference")


def _sum_amounts(records: list[dict[str, Any]]) -> str:
    total = sum(
        (
            _parse_decimal(record.get("gross_amount")) or Decimal(0)
            for record in records
        ),
        Decimal(0),
    )
    return _format_decimal(total) or "0.00"


def _documentary_totals(
    validation_records: dict[str, dict[str, Any]],
    document_statuses: dict[str, str],
) -> dict[str, Any]:
    totals = {
        "gross_documentary_purchases": Decimal(0),
        "pending_purchase_treatment": Decimal(0),
        "non_purchase_entry_operations": Decimal(0),
    }
    counts = Counter()
    by_type: dict[str, Decimal] = {}
    by_group: dict[str, Decimal] = {}
    pending_count = 0
    for document_ref, status in document_statuses.items():
        document = validation_records.get(document_ref)
        if document is None:
            continue
        amount = _parse_decimal(document.get("gross_amount")) or Decimal(0)
        if status == "CONFIRMED_PURCHASE":
            totals["gross_documentary_purchases"] += amount
            counts["confirmed"] += 1
            type_key = str(document.get("document_type") or "UNKNOWN")
            group_key = str(document.get("analysis_group") or "UNKNOWN")
            by_type[type_key] = by_type.get(type_key, Decimal(0)) + amount
            by_group[group_key] = by_group.get(group_key, Decimal(0)) + amount
        elif status == "PENDING_PURCHASE_TREATMENT":
            totals["pending_purchase_treatment"] += amount
            pending_count += 1
        elif status == "NON_PURCHASE_ENTRY":
            totals["non_purchase_entry_operations"] += amount

    return {
        "amount_basis": "UNIQUE_DOCUMENT_TOTAL",
        "document_count": counts["confirmed"],
        "gross_documentary_purchases": _format_decimal(
            totals["gross_documentary_purchases"]
        )
        or "0.00",
        "pending_document_count": pending_count,
        "pending_purchase_treatment": _format_decimal(
            totals["pending_purchase_treatment"]
        )
        or "0.00",
        "non_purchase_entry_operations": _format_decimal(
            totals["non_purchase_entry_operations"]
        )
        or "0.00",
        "by_document_type": {
            key: _format_decimal(value) or "0.00"
            for key, value in sorted(by_type.items())
        },
        "by_analysis_group": {
            key: _format_decimal(value) or "0.00"
            for key, value in sorted(by_group.items())
        },
        "cross_document_linkage": "NOT_PERFORMED",
    }


def _excluded_operation_summary(
    validation_records: dict[str, dict[str, Any]],
    document_statuses: dict[str, str],
    reasons_by_document: dict[str, list[str]],
) -> dict[str, Any]:
    """Summarize excluded operations without duplicating document values."""

    excluded_documents = {
        document_ref
        for document_ref, status in document_statuses.items()
        if status == "NON_PURCHASE_ENTRY" and document_ref in validation_records
    }
    document_total = sum(
        (
            _parse_decimal(validation_records[document_ref].get("gross_amount"))
            or Decimal(0)
            for document_ref in excluded_documents
        ),
        Decimal(0),
    )
    item_total = 0
    counts: dict[str, dict[str, Any]] = {}
    reason_totals: dict[str, Decimal] = {}
    mixed_reason_documents = 0
    mixed_reason_total = Decimal(0)
    for document_ref, status in document_statuses.items():
        if status != "NON_PURCHASE_ENTRY" or document_ref not in excluded_documents:
            continue
        reasons = reasons_by_document.get(document_ref, [])
        item_total += len(reasons)
        unique_reasons = sorted(set(reasons))
        if len(unique_reasons) == 1:
            reason_totals[unique_reasons[0]] = reason_totals.get(
                unique_reasons[0], Decimal(0)
            ) + (
                _parse_decimal(validation_records[document_ref].get("gross_amount"))
                or Decimal(0)
            )
        else:
            mixed_reason_documents += 1
            mixed_reason_total += _parse_decimal(
                validation_records[document_ref].get("gross_amount")
            ) or Decimal(0)
        for reason in unique_reasons:
            entry = counts.setdefault(
                reason, {"reason_document_count": 0, "item_count": 0}
            )
            entry["reason_document_count"] += 1
            entry["item_count"] += reasons.count(reason)
    for reason, total in reason_totals.items():
        counts[reason]["document_total"] = _format_decimal(total) or "0.00"
    for entry in counts.values():
        entry.setdefault("document_total", "0.00")
    return {
        "amount_basis": "UNIQUE_DOCUMENT_TOTAL",
        "document_count": len(excluded_documents),
        "item_count": item_total,
        "document_total": _format_decimal(document_total) or "0.00",
        "by_reason": dict(sorted(counts.items())),
        "mixed_reason_documents": {
            "document_count": mixed_reason_documents,
            "document_total": _format_decimal(mixed_reason_total) or "0.00",
        },
        "reason_document_counts_may_overlap": True,
    }


def review_acquisitions_folder(
    folder: Path | str,
    ruleset_path: Path | str,
    *,
    cfop_ruleset_path: Path | str | None = None,
    analyst_rules_path: Path | str | None = None,
) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta informada não existe")
    summary_path = base / "04_CONTEUDO" / "content-summary.json"
    records_path = base / "04_CONTEUDO" / "normalized-items.local.jsonl"
    content_summary = _load_json(summary_path, "04_CONTEUDO/content-summary.json")
    if (
        content_summary.get("use_case") != "UC-002"
        or content_summary.get("schema_version") != CONTENT_SCHEMA_VERSION
    ):
        raise ValidationError(
            "content-summary.json não pertence à versão vigente do UC-002"
        )
    if not content_summary.get("gates", {}).get("uc003_analysis_authorized"):
        raise ValidationError("UC-002 não autorizou o UC-003")
    content_records = _load_content_records(records_path)
    if len(content_records) != content_summary.get("records_total"):
        raise ValidationError("Resumo e JSONL do UC-002 possuem contagens divergentes")

    validation = _load_json(
        base / "03_SAIDAS" / "validation-result.json",
        "03_SAIDAS/validation-result.json",
    )
    if (
        validation.get("use_case") != "UC-001"
        or validation.get("schema_version") != DOCUMENT_SCHEMA_VERSION
    ):
        raise ValidationError(
            "validation-result.json não pertence à versão vigente do UC-001"
        )
    if validation.get("validation_id") != content_summary.get("validation_id"):
        raise ValidationError("UC-003 exige encadeamento entre UC-001 e UC-002")
    validation_records = {
        record["document_ref"]: record
        for record in validation.get("documents", {}).get("records", [])
        if record.get("included") and record.get("authorized_for_planning")
    }

    ruleset_file = Path(ruleset_path).expanduser().resolve()
    ruleset, ruleset_hash = _load_ruleset(ruleset_file)
    ruleset_integrity = verify_trusted_hash(
        ruleset_file, ruleset_hash, "snapshot oficial de CST/cClassTrib"
    )
    decisions, decision_summary = _load_decisions(base)
    period = content_summary.get("scope", {}).get("period", "")
    period_start, period_end = _period_bounds(period)
    pair_index = {
        (record["cst"], record["cclass_trib"]): record
        for record in ruleset["classification_records"]
    }

    cfop_index: dict[str, dict[str, Any]] = {}
    inbound_return_cfops: set[str] = set()
    cfop_lock: dict[str, Any] | None = None
    if cfop_ruleset_path is not None:
        cfop_snapshot, cfop_hash = _load_cfop_snapshot(
            Path(cfop_ruleset_path).expanduser().resolve()
        )
        analyst_rules_file = (
            Path(analyst_rules_path).expanduser().resolve()
            if analyst_rules_path is not None
            else None
        )
        if analyst_rules_file is None:
            raise ValidationError(
                "Revisão de aquisições com CFOP exige ruleset do analista"
            )
        analyst_rules, analyst_rules_hash = _load_cfop_analyst_rules(analyst_rules_file)
        analyst_rules_integrity = verify_trusted_hash(
            analyst_rules_file, analyst_rules_hash, "ruleset de receita do analista"
        )
        cfop_index = {
            str(record["cfop"]): record for record in cfop_snapshot["records"]
        }
        inbound_return_cfops = {
            str(value) for value in analyst_rules["sales_return_inbound_cfops"]
        }
        cfop_lock = {
            "snapshot_id": cfop_snapshot.get("snapshot_id"),
            "snapshot_sha256": cfop_hash,
            "verified_at": cfop_snapshot.get("verified_at"),
            "source": cfop_snapshot.get("source"),
            "analyst_ruleset_id": analyst_rules.get("ruleset_id"),
            "analyst_rules_sha256": analyst_rules_hash,
            "analyst_rules_source": analyst_rules.get("source"),
            **verify_trusted_hash(
                Path(cfop_ruleset_path).expanduser().resolve(),
                cfop_hash,
                "snapshot oficial de CFOP",
            ),
            "analyst_rules_integrity": analyst_rules_integrity,
        }

    acquisition_records: list[dict[str, Any]] = []
    product_operation_by_item: dict[str, tuple[str, dict[str, Any] | None, str]] = {}
    product_operations_by_document: dict[str, list[str]] = {}
    product_operation_reasons_by_document: dict[str, list[str]] = {}
    if cfop_index:
        for source in content_records:
            if (
                source.get("direction") != "ENTRADA"
                or source.get("record_kind") != "PRODUCT"
            ):
                continue
            operation = classify_acquisition_product_item_with_reason(
                source,
                cfop_index,
                inbound_return_cfops,
                period_start,
                period_end,
            )
            product_operation_by_item[source["item_ref"]] = operation
            product_operations_by_document.setdefault(
                source["document_ref"], []
            ).append(operation[0])
            product_operation_reasons_by_document.setdefault(
                source["document_ref"], []
            ).append(operation[2])

    document_statuses: dict[str, str] = {}
    for source in content_records:
        if source.get("direction") != "ENTRADA":
            continue
        document_ref = source["document_ref"]
        if source.get("record_kind") != "PRODUCT":
            document_statuses.setdefault(document_ref, "CONFIRMED_PURCHASE")
            continue
        operations = product_operations_by_document.get(document_ref)
        if not operations:
            document_statuses.setdefault(document_ref, "CONFIRMED_PURCHASE")
        elif all(operation == "PURCHASE_CONTEXT" for operation in operations):
            document_statuses[document_ref] = "CONFIRMED_PURCHASE"
        elif all(operation == "NON_PURCHASE_ENTRY" for operation in operations):
            document_statuses[document_ref] = "NON_PURCHASE_ENTRY"
        else:
            document_statuses[document_ref] = "PENDING_PURCHASE_TREATMENT"

    acquisition_input_refs = {
        record["item_ref"]
        for record in content_records
        if record.get("direction") == "ENTRADA"
        and record.get("record_kind") in ACQUISITION_CATEGORIES
        and product_operation_by_item.get(
            record["item_ref"], ("PURCHASE_CONTEXT", None, "PURCHASE_CONTEXT")
        )[0]
        != "NON_PURCHASE_ENTRY"
    }
    unknown_decisions = sorted(set(decisions) - acquisition_input_refs)
    if unknown_decisions:
        raise ValidationError(
            "classificacao-aquisicoes.csv referencia itens ausentes no UC-002"
        )
    for source in content_records:
        if source.get("direction") != "ENTRADA":
            continue
        kind = source.get("record_kind")
        category = ACQUISITION_CATEGORIES.get(kind)
        if category is None:
            continue
        operation_name, official_operation = product_operation_by_item.get(
            source["item_ref"], ("PURCHASE_CONTEXT", None, "PURCHASE_CONTEXT")
        )[:2]
        if operation_name == "NON_PURCHASE_ENTRY":
            continue
        record = dict(source)
        record["acquisition_category"] = category
        record["purchase_operation_status"] = operation_name
        record["cfop_official"] = official_operation
        decision = decisions.get(record["item_ref"])
        if operation_name == "PENDING_PURCHASE_TREATMENT":
            nature = None
            nature_status = "PENDING_PURCHASE_TREATMENT"
        elif not record.get("eligible_for_uc003", True):
            nature = None
            nature_status = "RESTRICTED_INPUT"
        elif decision is None:
            nature = None
            nature_status = "PENDING_ANALYST_CLASSIFICATION"
        else:
            nature = decision["nature"]
            if nature not in ALLOWED_NATURES[kind]:
                raise ValidationError(
                    "classificacao-aquisicoes.csv possui natureza incompatível com o tipo do item"
                )
            nature_status = "ANALYST_APPROVED"
        evidence_status, legal_reference = _legal_evidence_status(
            record, pair_index, period_start, period_end
        )
        record["acquisition_nature"] = nature
        record["nature_status"] = nature_status
        record["legal_evidence_status"] = evidence_status
        record["legal_reference"] = legal_reference
        record["analyst_decision"] = decision
        acquisition_records.append(record)

    acquisition_records.sort(key=lambda item: item["item_ref"])
    pending_records = [
        record
        for record in acquisition_records
        if record["nature_status"] != "ANALYST_APPROVED"
    ]
    legal_pending = [
        record
        for record in acquisition_records
        if record["legal_evidence_status"] != "CONFIRMED_DECLARED"
    ]
    review_material = {
        "validation_id": validation["validation_id"],
        "content_analysis_id": content_summary["content_analysis_id"],
        "ruleset_hash": ruleset_hash,
        "decisions_hash": decision_summary["source_hash"],
        "item_refs": [record["item_ref"] for record in acquisition_records],
        "document_statuses": document_statuses,
        "operation_reasons": product_operation_reasons_by_document,
        "cfop_ruleset": cfop_lock,
        "schema_version": ACQUISITION_SCHEMA_VERSION,
    }
    review_id = (
        "ACQ-"
        + hashlib.sha256(
            json.dumps(review_material, sort_keys=True, separators=(",", ":")).encode()
        )
        .hexdigest()[:16]
        .upper()
    )
    category_counts = Counter(
        record["acquisition_category"] for record in acquisition_records
    )
    category_amounts = {
        category: _sum_amounts(
            [
                record
                for record in acquisition_records
                if record["acquisition_category"] == category
            ]
        )
        for category in sorted(category_counts)
    }
    ruleset_lock = {
        "snapshot_id": ruleset["snapshot_id"],
        "snapshot_sha256": ruleset_hash,
        "verified_at": ruleset["verified_at"],
        "source": ruleset["source"],
        "legal_sources": ruleset["legal_sources"],
        "classification_records": len(ruleset["classification_records"]),
        "cst_records": len(ruleset["cst_records"]),
        **ruleset_integrity,
    }
    if cfop_lock is not None:
        ruleset_lock["cfop"] = cfop_lock
    documentary_totals = _documentary_totals(validation_records, document_statuses)
    excluded_operation_summary = _excluded_operation_summary(
        validation_records, document_statuses, product_operation_reasons_by_document
    )
    result = {
        "schema": ACQUISITION_SCHEMA,
        "schema_version": ACQUISITION_SCHEMA_VERSION,
        "use_case": "UC-003",
        "phase": "ACQUISITION_REVIEW",
        "review_id": review_id,
        "content_analysis_id": content_summary["content_analysis_id"],
        "status": (
            "ACQUISITION_REVIEW_NO_DOCUMENT"
            if not acquisition_records
            else "ACQUISITION_REVIEW_READY_WITH_PENDING"
            if pending_records or legal_pending
            else "ACQUISITION_REVIEW_READY"
        ),
        "scope": content_summary["scope"],
        "input_records": len(content_records),
        "acquisition_records": len(acquisition_records),
        "non_acquisition_records": len(content_records) - len(acquisition_records),
        "category_counts": dict(sorted(category_counts.items())),
        "category_amounts": category_amounts,
        "documentary_totals": documentary_totals,
        "excluded_operation_summary": excluded_operation_summary,
        "purchase_operation_status_counts": dict(
            sorted(
                Counter(
                    record.get("purchase_operation_status", "PURCHASE_CONTEXT")
                    for record in acquisition_records
                ).items()
            )
        ),
        "nature_status_counts": dict(
            sorted(
                Counter(
                    record["nature_status"] for record in acquisition_records
                ).items()
            )
        ),
        "legal_evidence_status_counts": dict(
            sorted(
                Counter(
                    record["legal_evidence_status"] for record in acquisition_records
                ).items()
            )
        ),
        "decision_input": decision_summary,
        "ruleset_lock": ruleset_lock,
        "gates": {
            "uc003_execution_ready": True,
            "acquisition_review_required": bool(acquisition_records),
            "operational_classification_complete": True,
            "acquisition_review_complete": bool(acquisition_records)
            and not pending_records,
            "legal_evidence_complete": bool(acquisition_records) and not legal_pending,
            "analyst_review_required": bool(pending_records or legal_pending),
            "uc004_planning_authorized": False,
        },
        "limitations": [
            "O UC-003 inicial classifica aquisições e valida evidências declaradas; não conclui direito a crédito.",
            "CONFIRMED_DECLARED comprova apenas que CST/cClassTrib formam par vigente e aplicável ao DF-e no snapshot oficial.",
            "Ausência de evidência permanece pendente e não representa não incidência, infração ou vedação de crédito.",
            "A autorização do UC-004 dependerá de regras materiais e aprovação do analista em etapa posterior.",
        ],
        "_private_records": acquisition_records,
    }
    return result


def _markdown_report(result: dict[str, Any]) -> str:
    documentary_totals = result["documentary_totals"]
    lines = [
        "# Relatório de Revisão das Aquisições",
        "",
        f"- Revisão: `{result['review_id']}`",
        f"- Conteúdo de origem: `{result['content_analysis_id']}`",
        f"- Situação: `{result['status']}`",
        f"- Competência: `{result['scope']['period']}`",
        f"- Registros de aquisição: {result['acquisition_records']}",
        f"- Snapshot oficial: `{result['ruleset_lock']['snapshot_id']}`",
        "",
        "## Categorias",
        "",
        "| Categoria | Registros | Valor documental |",
        "|---|---:|---:|",
    ]
    if result["category_counts"]:
        for category, count in result["category_counts"].items():
            lines.append(
                f"| `{category}` | {count} | {result['category_amounts'][category]} |"
            )
    else:
        lines.append("| `SEM_DOCUMENTO` | 0 | 0.00 |")
    lines.extend(
        [
            "",
            "## Totais documentais de compras",
            "",
            "| Indicador | Valor |",
            "|---|---:|",
            f"| Documentos confirmados como compra | {documentary_totals['document_count']} |",
            f"| Total bruto documental | {documentary_totals['gross_documentary_purchases']} |",
            f"| Documentos pendentes de tratamento | {documentary_totals['pending_document_count']} |",
            f"| Valor pendente de tratamento | {documentary_totals['pending_purchase_treatment']} |",
            f"| Operações de entrada fora de compras | {documentary_totals['non_purchase_entry_operations']} |",
            f"| Vínculo econômico entre documentos | `{documentary_totals['cross_document_linkage']}` |",
            "",
            "Subtotais acima usam o total de cada documento uma única vez. Compras sem crédito permanecem incluídas; este relatório não conclui custo econômico ou direito a crédito.",
        ]
    )
    excluded_summary = result["excluded_operation_summary"]
    if excluded_summary["document_count"]:
        lines.extend(
            [
                "",
                "### Operações excluídas do total de compras",
                "",
                f"- Total de documentos excluídos: {excluded_summary['document_count']}",
                f"- Valor total dos documentos excluídos: {excluded_summary['document_total']}",
                f"- Itens excluídos: {excluded_summary['item_count']}",
                "",
                "| Motivo CFOP | Documentos por motivo | Itens | Valor documental |",
                "|---|---:|---:|---:|",
            ]
        )
        for reason, counts in excluded_summary["by_reason"].items():
            lines.append(
                f"| `{reason}` | {counts['reason_document_count']} | {counts['item_count']} | {counts['document_total']} |"
            )
        mixed = excluded_summary["mixed_reason_documents"]
        if mixed["document_count"]:
            lines.append(
                f"| `MULTIPLE_NON_PURCHASE_REASONS` | {mixed['document_count']} | — | {mixed['document_total']} |"
            )
        lines.append(
            "A contagem por motivo pode se sobrepor quando um documento possuir mais de uma operação; o valor total é contado uma única vez."
        )
    lines.extend(
        [
            "",
            "## Estados da natureza da aquisição",
            "",
        ]
    )
    for status, count in result["nature_status_counts"].items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Evidência IBS/CBS declarada", ""])
    for status, count in result["legal_evidence_status_counts"].items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- Execução pronta: `{str(result['gates']['uc003_execution_ready']).lower()}`",
            f"- Classificação operacional completa: `{str(result['gates']['operational_classification_complete']).lower()}`",
            f"- Revisão de aquisições completa: `{str(result['gates']['acquisition_review_complete']).lower()}`",
            f"- Evidência legal completa: `{str(result['gates']['legal_evidence_complete']).lower()}`",
            f"- Revisão do analista necessária: `{str(result['gates']['analyst_review_required']).lower()}`",
            f"- UC-004 autorizado: `{str(result['gates']['uc004_planning_authorized']).lower()}`",
            "",
            "## Limitações",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def _review_queue(records: list[dict[str, Any]]) -> str:
    columns = [
        "item_ref",
        "record_kind",
        "analysis_group",
        "product_code",
        "ncm",
        "cfop",
        "service_list_code",
        "cnae",
        "nbs",
        "description",
        "natureza",
        "status",
        "aprovado_por",
        "observacao",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter=";", lineterminator="\n"
    )
    writer.writeheader()
    for record in records:
        if record["nature_status"] == "ANALYST_APPROVED":
            continue
        writer.writerow(
            {
                "item_ref": record["item_ref"],
                "record_kind": record["record_kind"],
                "analysis_group": record["analysis_group"],
                "product_code": record.get("product_code") or "",
                "ncm": record.get("ncm") or "",
                "cfop": record.get("cfop") or "",
                "service_list_code": record.get("service_list_code") or "",
                "cnae": record.get("cnae") or "",
                "nbs": record.get("nbs") or "",
                "description": record.get("description") or "",
                "natureza": "",
                "status": "PENDENTE",
                "aprovado_por": "",
                "observacao": "",
            }
        )
    return stream.getvalue()


def write_acquisition_outputs(
    result: dict[str, Any], output_dir: Path | str
) -> tuple[Path, Path, Path, Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    summary_path = target / "acquisition-summary.json"
    records_path = target / "acquisition-items.local.jsonl"
    queue_path = target / "fila-revisao-aquisicoes.csv"
    lock_path = target / "ruleset-lock.json"
    report_path = target / "relatorio-revisao-aquisicoes.md"
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
        _review_queue(result["_private_records"]), encoding="utf-8-sig"
    )
    lock_path.write_text(
        json.dumps(result["ruleset_lock"], ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_markdown_report(result), encoding="utf-8")
    return summary_path, records_path, queue_path, lock_path, report_path
