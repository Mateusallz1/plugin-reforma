from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .content import CONTENT_SCHEMA_VERSION
from .core import ValidationError, _format_decimal, _parse_decimal
from .operation_classification import classify_product_item as _classify_product_item
from .ruleset_integrity import verify_trusted_hash

REVENUE_SCHEMA = "br.com.planejamento-reforma-tributaria/revenue-review"
REVENUE_SCHEMA_VERSION = "1.6.0"
DECISION_FILE = Path("00_CONTROLE") / "classificacao-receitas.csv"
PENDING_CLASSES = {
    "INVALID_CFOP_PENDING",
    "MIXED_DOCUMENT_PENDING_ALLOCATION",
    "PENDING_REVENUE_TREATMENT",
    "RETURN_INBOUND_PENDING_ORIGIN",
}
ALLOWED_OVERRIDES = {
    "REVENUE_GOODS",
    "REVENUE_SERVICES",
    "REVENUE_TRANSPORT",
    "SALES_RETURN_INBOUND",
    "PURCHASE_RETURN_OUTBOUND",
    "NON_REVENUE_REMITTANCE",
    "NON_REVENUE_RETURN",
    "NON_REVENUE_ANNULMENT",
    "NON_REVENUE_OPERATION",
    "OTHER_REVENUE",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"UC-003B exige {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} deve ser JSON UTF-8 válido") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} deve conter um objeto JSON")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValidationError("UC-003B exige 04_CONTEUDO/normalized-items.local.jsonl")
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
    return records


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


def _load_analyst_rules(path: Path) -> tuple[dict[str, Any], str]:
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
            required = {"document_ref", "classificacao", "status", "aprovado_por"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValidationError(
                    "classificacao-receitas.csv exige document_ref, classificacao, status e aprovado_por"
                )
            decisions: dict[str, dict[str, str]] = {}
            for line_number, row in enumerate(reader, start=2):
                status = (row.get("status") or "").strip().upper()
                if status != "APROVADO":
                    continue
                document_ref = (row.get("document_ref") or "").strip()
                classification = (row.get("classificacao") or "").strip().upper()
                approved_by = (row.get("aprovado_por") or "").strip()
                if (
                    not document_ref
                    or classification not in ALLOWED_OVERRIDES
                    or not approved_by
                ):
                    raise ValidationError(
                        f"classificacao-receitas.csv possui linha APROVADO inválida: {line_number}"
                    )
                decision = {
                    "classification": classification,
                    "approved_by": approved_by,
                    "note": (row.get("observacao") or "").strip(),
                }
                if document_ref in decisions and decisions[document_ref] != decision:
                    raise ValidationError(
                        "classificacao-receitas.csv possui decisões conflitantes"
                    )
                decisions[document_ref] = decision
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValidationError(
            "classificacao-receitas.csv deve ser CSV UTF-8 válido"
        ) from error
    return decisions, {
        "status": "LOADED",
        "approved_records": len(decisions),
        "source_hash": _sha256(path),
    }


def _period_bounds(period: str) -> tuple[date, date]:
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period) is None:
        raise ValidationError("UC-003B exige competência AAAA-MM")
    year, month = (int(value) for value in period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _decimal(value: Any) -> Decimal:
    return _parse_decimal(value) or Decimal(0)


def _sum(records: list[dict[str, Any]], field: str) -> Decimal:
    return sum((_decimal(record.get(field)) for record in records), Decimal(0))


def _document_composition(
    items: list[dict[str, Any]], document_total: Decimal, item_total: Decimal
) -> tuple[dict[str, str], Decimal, Decimal, str]:
    """Explain ``vNF`` from the document-level NF-e totals.

    Item-level values remain evidence, but the official composition uses the
    totals in ``ICMSTot``/``ISSQNtot``. This avoids double counting and avoids
    inventing an allocation when a component was not supplied by the issuer.
    """

    raw_totals = next(
        (
            item.get("document_total_components")
            for item in items
            if isinstance(item.get("document_total_components"), dict)
        ),
        None,
    )
    raw_components = (
        raw_totals.get("components") if isinstance(raw_totals, dict) else None
    )
    if not isinstance(raw_components, dict):
        residual = document_total - item_total
        status = (
            "EXPLAINED_BY_ITEM_TOTAL" if residual == 0 else "COMPONENTS_UNAVAILABLE"
        )
        return {}, Decimal(0), residual, status

    component_rules = (
        ("discount", "desconto", -1),
        ("icms_exempt", "icms_desonerado", -1),
        ("icms_st", "icms_st", 1),
        ("fcp_st", "fcp_st", 1),
        ("freight", "frete", 1),
        ("insurance", "seguro", 1),
        ("other_expenses", "outras_despesas", 1),
        ("import_duty", "ii", 1),
        ("ipi", "ipi", 1),
        ("ipi_returned", "ipi_devolvido", 1),
        ("services", "servicos", 1),
    )
    excluded_for_rule = (
        {"icms_st", "fcp_st", "ipi_returned"}
        if raw_totals.get("rule") == "FATURAMENTO_DIRETO"
        else set()
    )
    if raw_totals.get("rule") == "PADRAO_SEM_DEDUCAO_ICMS_DESON":
        excluded_for_rule.add("icms_exempt")
    expected = _decimal(raw_components.get("product"))
    composition: dict[str, str] = {}
    for field, label, sign in component_rules:
        if field in excluded_for_rule:
            continue
        value = _decimal(raw_components.get(field))
        if value:
            signed = value * sign
            composition[label] = _money(signed)
            expected += signed
    explained = expected - item_total
    document_residual = document_total - expected
    item_product_difference = _decimal(raw_components.get("product")) - item_total
    residual = document_residual if document_residual != 0 else item_product_difference
    declared_status = str(raw_totals.get("status") or "")
    if declared_status == "UNAVAILABLE":
        status = "COMPONENTS_UNAVAILABLE"
    elif document_residual != 0:
        status = "RESIDUAL"
    elif item_product_difference != 0:
        status = "ITEM_TOTAL_MISMATCH"
    else:
        status = "EXPLAINED"
    return composition, explained, residual, status


def _money(value: Decimal) -> str:
    return _format_decimal(value) or "0.00"


def review_revenue_folder(
    folder: Path | str,
    cfop_snapshot_path: Path | str,
    analyst_rules_path: Path | str,
) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta informada não existe")
    validation = _load_json(
        base / "03_SAIDAS" / "validation-result.json",
        "03_SAIDAS/validation-result.json",
    )
    content_summary = _load_json(
        base / "04_CONTEUDO" / "content-summary.json",
        "04_CONTEUDO/content-summary.json",
    )
    if (
        validation.get("use_case") != "UC-001"
        or content_summary.get("use_case") != "UC-002"
        or content_summary.get("schema_version") != CONTENT_SCHEMA_VERSION
    ):
        raise ValidationError(
            "UC-003B exige saídas vigentes e coerentes dos UC-001 e UC-002"
        )
    if not content_summary.get("gates", {}).get("uc003_analysis_authorized"):
        raise ValidationError("UC-002 não autorizou o UC-003")
    content_records = _load_jsonl(base / "04_CONTEUDO" / "normalized-items.local.jsonl")
    if len(content_records) != content_summary.get("records_total"):
        raise ValidationError("Resumo e JSONL do UC-002 possuem contagens divergentes")

    cfop_snapshot_file = Path(cfop_snapshot_path).expanduser().resolve()
    analyst_rules_file = Path(analyst_rules_path).expanduser().resolve()
    snapshot, snapshot_hash = _load_cfop_snapshot(cfop_snapshot_file)
    analyst_rules, analyst_rules_hash = _load_analyst_rules(analyst_rules_file)
    snapshot_integrity = verify_trusted_hash(
        cfop_snapshot_file, snapshot_hash, "snapshot oficial de CFOP"
    )
    analyst_rules_integrity = verify_trusted_hash(
        analyst_rules_file, analyst_rules_hash, "ruleset de receita do analista"
    )
    decisions, decision_summary = _load_decisions(base)
    cfop_index = {record["cfop"]: record for record in snapshot["records"]}
    sale_cfops = set(analyst_rules["usual_sale_cfops"])
    inbound_return_cfops = set(analyst_rules["sales_return_inbound_cfops"])
    period = content_summary.get("scope", {}).get("period", "")
    period_start, period_end = _period_bounds(period)

    validation_records = {
        record["document_ref"]: record
        for record in validation.get("documents", {}).get("records", [])
        if record.get("included") and record.get("authorized_for_planning")
    }
    products_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in content_records:
        if record.get("record_kind") == "PRODUCT":
            products_by_document[record["document_ref"]].append(record)

    revenue_records: list[dict[str, Any]] = []
    cfop_items: list[dict[str, Any]] = []
    for document_ref, items in products_by_document.items():
        item_classes: set[str] = set()
        for item in items:
            item_class, official = _classify_product_item(
                item,
                cfop_index,
                sale_cfops,
                inbound_return_cfops,
                period_start,
                period_end,
            )
            item_classes.add(item_class)
            cfop_items.append(
                {
                    "document_ref": document_ref,
                    "item_ref": item["item_ref"],
                    "direction": item["direction"],
                    "cfop": item.get("cfop"),
                    "item_amount": item.get("gross_amount"),
                    "classification": item_class,
                    "official_indicators": official,
                }
            )
        if item_classes == {"PURCHASE_CONTEXT"}:
            continue
        document = validation_records.get(document_ref)
        if document is None:
            raise ValidationError("UC-003B não localizou documento do UC-001")
        automatic_class = (
            next(iter(item_classes))
            if len(item_classes) == 1
            else "MIXED_DOCUMENT_PENDING_ALLOCATION"
        )
        decision = decisions.get(document_ref)
        final_class = decision["classification"] if decision else automatic_class
        document_total = _decimal(document.get("gross_amount"))
        included_items = [
            item for item in items if item.get("includes_document_total") != "0"
        ]
        item_total = _sum(included_items, "gross_amount")
        difference = document_total - item_total
        composition, explained, residual, composition_status = _document_composition(
            items, document_total, item_total
        )
        revenue_records.append(
            {
                "document_ref": document_ref,
                "document_type": document["document_type"],
                "direction": document["direction"],
                "analysis_group": document["analysis_group"],
                "automatic_classification": automatic_class,
                "final_classification": final_class,
                "classification_source": "ANALYST_APPROVED" if decision else "RULESET",
                "document_total": _money(document_total),
                "item_total": _money(item_total),
                "unallocated_difference": _money(difference),
                "difference_composition": composition,
                "explained_difference": _money(explained),
                "residual_difference": _money(residual),
                "composition_status": composition_status,
                "item_count": len(items),
                "cfops": sorted({str(item.get("cfop") or "") for item in items}),
                "analyst_decision": decision,
            }
        )

    for item in content_records:
        if item.get("direction") != "SAIDA" or item.get("record_kind") == "PRODUCT":
            continue
        if item.get("record_kind") == "SERVICE":
            classification = "REVENUE_SERVICES"
        elif item.get("record_kind") == "TRANSPORT":
            classification = "REVENUE_TRANSPORT"
        else:
            continue
        decision = decisions.get(item["document_ref"])
        revenue_records.append(
            {
                "document_ref": item["document_ref"],
                "document_type": item["document_type"],
                "direction": item["direction"],
                "analysis_group": item["analysis_group"],
                "automatic_classification": classification,
                "final_classification": (
                    decision["classification"] if decision else classification
                ),
                "classification_source": "ANALYST_APPROVED" if decision else "RULESET",
                "document_total": item.get("gross_amount") or "0.00",
                "item_total": item.get("gross_amount") or "0.00",
                "unallocated_difference": "0.00",
                "difference_composition": {},
                "explained_difference": "0.00",
                "residual_difference": "0.00",
                "composition_status": "NOT_APPLICABLE",
                "item_count": 1,
                "cfops": [item.get("cfop")] if item.get("cfop") else [],
                "analyst_decision": decision,
            }
        )

    revenue_records.sort(key=lambda record: record["document_ref"])
    review_refs = {record["document_ref"] for record in revenue_records}
    unknown_decisions = sorted(set(decisions) - review_refs)
    if unknown_decisions:
        raise ValidationError(
            "classificacao-receitas.csv referencia documentos ausentes da revisão"
        )
    pending = [
        record
        for record in revenue_records
        if record["final_classification"] in PENDING_CLASSES
    ]
    unexplained = [
        record
        for record in revenue_records
        if _decimal(record["residual_difference"]) != 0
        or record.get("composition_status")
        in {"COMPONENTS_UNAVAILABLE", "ITEM_TOTAL_MISMATCH"}
    ]

    def total_for(*classes: str) -> Decimal:
        return sum(
            (
                _decimal(record["document_total"])
                for record in revenue_records
                if record["final_classification"] in classes
            ),
            Decimal(0),
        )

    revenue_goods = total_for("REVENUE_GOODS")
    revenue_services = total_for("REVENUE_SERVICES")
    revenue_transport = total_for("REVENUE_TRANSPORT")
    other_revenue = total_for("OTHER_REVENUE")
    gross_operational = (
        revenue_goods + revenue_services + revenue_transport + other_revenue
    )
    sales_returns = total_for("SALES_RETURN_INBOUND")
    purchase_returns = total_for("PURCHASE_RETURN_OUTBOUND")
    net_candidate = gross_operational - sales_returns
    excluded_operations = total_for(
        "PURCHASE_RETURN_OUTBOUND",
        "NON_REVENUE_REMITTANCE",
        "NON_REVENUE_RETURN",
        "NON_REVENUE_ANNULMENT",
        "NON_REVENUE_OPERATION",
    )
    pending_amount = total_for(*PENDING_CLASSES)

    cfop_summary: dict[str, dict[str, Any]] = {}
    reviewed_cfop_items = [
        item for item in cfop_items if item["document_ref"] in review_refs
    ]
    for cfop in sorted({str(item["cfop"] or "") for item in reviewed_cfop_items}):
        selected = [
            item for item in reviewed_cfop_items if str(item["cfop"] or "") == cfop
        ]
        cfop_summary[cfop] = {
            "items": len(selected),
            "documents": len({item["document_ref"] for item in selected}),
            "item_amount": _money(_sum(selected, "item_amount")),
            "classifications": sorted({item["classification"] for item in selected}),
        }

    review_material = {
        "validation_id": validation["validation_id"],
        "content_analysis_id": content_summary["content_analysis_id"],
        "cfop_snapshot_hash": snapshot_hash,
        "analyst_rules_hash": analyst_rules_hash,
        "decisions_hash": decision_summary["source_hash"],
        "document_refs": [record["document_ref"] for record in revenue_records],
        "schema_version": REVENUE_SCHEMA_VERSION,
    }
    review_id = (
        "REV-"
        + hashlib.sha256(
            json.dumps(review_material, sort_keys=True, separators=(",", ":")).encode()
        )
        .hexdigest()[:16]
        .upper()
    )
    ruleset_lock = {
        "cfop_snapshot_id": snapshot["snapshot_id"],
        "cfop_snapshot_sha256": snapshot_hash,
        "cfop_verified_at": snapshot["verified_at"],
        "cfop_source": snapshot["source"],
        "cfop_records": len(snapshot["records"]),
        "cfop_integrity": snapshot_integrity,
        "analyst_ruleset_id": analyst_rules["ruleset_id"],
        "analyst_rules_sha256": analyst_rules_hash,
        "analyst_rules_source": analyst_rules["source"],
        "analyst_rules_approved_at": analyst_rules["approved_at"],
        "analyst_rules_integrity": analyst_rules_integrity,
    }
    uc003_revenue_execution_ready = bool(
        ruleset_lock.get("cfop_snapshot_id")
        and ruleset_lock.get("cfop_snapshot_sha256")
        and ruleset_lock.get("cfop_integrity", {}).get("integrity_status") == "VERIFIED"
        and ruleset_lock.get("analyst_ruleset_id")
        and ruleset_lock.get("analyst_rules_sha256")
        and ruleset_lock.get("analyst_rules_integrity", {}).get("integrity_status")
        == "VERIFIED"
    )
    revenue_population_ready = not pending and not unexplained
    simulation_authorized = bool(
        uc003_revenue_execution_ready and revenue_population_ready
    )
    result = {
        "schema": REVENUE_SCHEMA,
        "schema_version": REVENUE_SCHEMA_VERSION,
        "use_case": "UC-003",
        "phase": "REVENUE_REVIEW",
        "review_id": review_id,
        "validation_id": validation["validation_id"],
        "content_analysis_id": content_summary["content_analysis_id"],
        "status": (
            "REVENUE_REVIEW_NO_DOCUMENT"
            if not revenue_records
            else "REVENUE_REVIEW_READY_WITH_PENDING"
            if pending or unexplained
            else "REVENUE_REVIEW_READY"
        ),
        "scope": content_summary["scope"],
        "reviewed_documents": len(revenue_records),
        "classification_counts": dict(
            sorted(
                Counter(
                    record["final_classification"] for record in revenue_records
                ).items()
            )
        ),
        "cfop_summary": cfop_summary,
        "totals": {
            "gross_revenue_goods": _money(revenue_goods),
            "gross_revenue_services": _money(revenue_services),
            "gross_revenue_transport": _money(revenue_transport),
            "other_revenue": _money(other_revenue),
            "gross_operational_revenue": _money(gross_operational),
            "sales_returns_inbound": _money(sales_returns),
            "purchase_returns_outbound": _money(purchase_returns),
            "net_documentary_revenue_candidate": _money(net_candidate),
            "excluded_non_revenue_operations": _money(excluded_operations),
            "pending_revenue_treatment": _money(pending_amount),
            "unallocated_document_components": _money(
                sum(
                    (_decimal(record["residual_difference"]) for record in unexplained),
                    Decimal(0),
                )
            ),
        },
        "decision_input": decision_summary,
        "ruleset_lock": ruleset_lock,
        "gates": {
            "uc003_revenue_execution_ready": uc003_revenue_execution_ready,
            "revenue_review_required": bool(revenue_records),
            "cfop_classification_complete": not pending,
            "document_item_totals_explained": not unexplained,
            "revenue_population_ready": revenue_population_ready,
            "analyst_review_required": bool(pending or unexplained),
            "simulation_authorized": simulation_authorized,
            "uc004_planning_authorized": False,
        },
        "limitations": [
            "A revisão usa o total documental e o CFOP dos itens; não conclui receita tributável de IBS/CBS.",
            "CFOPs usuais de venda vêm do checklist do analista e não representam lista exaustiva.",
            "Devoluções e remessas usam indicadores oficiais; o efeito contábil ou tributário final exige regras posteriores.",
            "A autorização do UC-004 depende da revisão de aquisições, regras materiais e aprovação do analista.",
        ],
        "_private_records": revenue_records,
        "_private_cfop_items": cfop_items,
    }
    return result


def _report(result: dict[str, Any]) -> str:
    totals = result["totals"]
    lines = [
        "# Relatório de Revisão das Receitas",
        "",
        f"- Revisão: `{result['review_id']}`",
        f"- Situação: `{result['status']}`",
        f"- Competência: `{result['scope']['period']}`",
        f"- Documentos revisados: {result['reviewed_documents']}",
        f"- Snapshot CFOP: `{result['ruleset_lock']['cfop_snapshot_id']}`",
        "",
        "## Totais documentais",
        "",
        f"- Receita bruta de mercadorias: {totals['gross_revenue_goods']}",
        f"- Receita bruta de serviços: {totals['gross_revenue_services']}",
        f"- Receita bruta de transportes: {totals['gross_revenue_transport']}",
        f"- Receita operacional documental: {totals['gross_operational_revenue']}",
        f"- Devoluções de venda recebidas: {totals['sales_returns_inbound']}",
        f"- Receita documental líquida candidata: {totals['net_documentary_revenue_candidate']}",
        f"- Devoluções de compra emitidas: {totals['purchase_returns_outbound']}",
        f"- Operações fora da receita: {totals['excluded_non_revenue_operations']}",
        f"- Tratamento pendente: {totals['pending_revenue_treatment']}",
        f"- Resíduo documental não comprovado: {totals['unallocated_document_components']}",
        "",
        "## Classificações",
        "",
    ]
    for classification, count in result["classification_counts"].items():
        lines.append(f"- `{classification}`: {count}")
    lines.extend(
        [
            "",
            "## CFOPs",
            "",
            "| CFOP | Itens | Documentos | Valor dos itens | Classe |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for cfop, summary in result["cfop_summary"].items():
        lines.append(
            f"| `{cfop}` | {summary['items']} | {summary['documents']} | "
            f"{summary['item_amount']} | {', '.join(summary['classifications'])} |"
        )
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- Execução pronta: `{str(result['gates']['uc003_revenue_execution_ready']).lower()}`",
            f"- CFOP completo: `{str(result['gates']['cfop_classification_complete']).lower()}`",
            f"- Totais explicados: `{str(result['gates']['document_item_totals_explained']).lower()}`",
            f"- População de receita pronta: `{str(result['gates']['revenue_population_ready']).lower()}`",
            f"- Revisão do analista necessária: `{str(result['gates']['analyst_review_required']).lower()}`",
            f"- Simulação do UC-004 autorizada: `{str(result['gates']['simulation_authorized']).lower()}`",
            f"- UC-004 autorizado: `{str(result['gates']['uc004_planning_authorized']).lower()}`",
            "",
            "## Limitações",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def _queue(records: list[dict[str, Any]]) -> str:
    columns = [
        "document_ref",
        "document_type",
        "direction",
        "cfops",
        "automatic_classification",
        "document_total",
        "item_total",
        "unallocated_difference",
        "composicao_da_diferenca",
        "diferenca_explicada",
        "residuo_nao_comprovado",
        "classificacao",
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
        if (
            record["final_classification"] not in PENDING_CLASSES
            and _decimal(record["residual_difference"]) == 0
        ):
            continue
        writer.writerow(
            {
                "document_ref": record["document_ref"],
                "document_type": record["document_type"],
                "direction": record["direction"],
                "cfops": ",".join(record["cfops"]),
                "automatic_classification": record["automatic_classification"],
                "document_total": record["document_total"],
                "item_total": record["item_total"],
                "unallocated_difference": record["unallocated_difference"],
                "composicao_da_diferenca": " ".join(
                    f"{label}={value}"
                    for label, value in sorted(record["difference_composition"].items())
                ),
                "diferenca_explicada": record["explained_difference"],
                "residuo_nao_comprovado": record["residual_difference"],
                "classificacao": "",
                "status": "PENDENTE",
                "aprovado_por": "",
                "observacao": "",
            }
        )
    return stream.getvalue()


def write_revenue_outputs(
    result: dict[str, Any], output_dir: Path | str
) -> tuple[Path, Path, Path, Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    summary_path = target / "revenue-summary.json"
    records_path = target / "revenue-documents.local.jsonl"
    queue_path = target / "fila-revisao-receitas.csv"
    lock_path = target / "cfop-ruleset-lock.json"
    report_path = target / "relatorio-revisao-receitas.md"
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
    queue_path.write_text(_queue(result["_private_records"]), encoding="utf-8-sig")
    lock_path.write_text(
        json.dumps(result["ruleset_lock"], ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_report(result), encoding="utf-8")
    return summary_path, records_path, queue_path, lock_path, report_path
