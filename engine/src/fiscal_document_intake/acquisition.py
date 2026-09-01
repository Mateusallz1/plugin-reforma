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

from .core import ValidationError, _format_decimal, _parse_decimal

ACQUISITION_SCHEMA = "br.com.planejamento-reforma-tributaria/acquisition-review"
ACQUISITION_SCHEMA_VERSION = "1.1.0"
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
    return ruleset, _sha256(path)


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


def review_acquisitions_folder(
    folder: Path | str, ruleset_path: Path | str
) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta informada não existe")
    summary_path = base / "04_CONTEUDO" / "content-summary.json"
    records_path = base / "04_CONTEUDO" / "normalized-items.local.jsonl"
    content_summary = _load_json(summary_path, "04_CONTEUDO/content-summary.json")
    if content_summary.get("use_case") != "UC-002":
        raise ValidationError("content-summary.json não pertence ao UC-002")
    if not content_summary.get("gates", {}).get("uc003_analysis_authorized"):
        raise ValidationError("UC-002 não autorizou o UC-003")
    content_records = _load_content_records(records_path)
    if len(content_records) != content_summary.get("records_total"):
        raise ValidationError("Resumo e JSONL do UC-002 possuem contagens divergentes")

    ruleset_file = Path(ruleset_path).expanduser().resolve()
    ruleset, ruleset_hash = _load_ruleset(ruleset_file)
    decisions, decision_summary = _load_decisions(base)
    period = content_summary.get("scope", {}).get("period", "")
    period_start, period_end = _period_bounds(period)
    pair_index = {
        (record["cst"], record["cclass_trib"]): record
        for record in ruleset["classification_records"]
    }

    acquisition_records: list[dict[str, Any]] = []
    acquisition_input_refs = {
        record["item_ref"]
        for record in content_records
        if record.get("direction") == "ENTRADA"
        and record.get("record_kind") in ACQUISITION_CATEGORIES
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
        record = dict(source)
        record["acquisition_category"] = category
        decision = decisions.get(record["item_ref"])
        if not record.get("eligible_for_uc003", True):
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
        "content_analysis_id": content_summary["content_analysis_id"],
        "ruleset_hash": ruleset_hash,
        "decisions_hash": decision_summary["source_hash"],
        "item_refs": [record["item_ref"] for record in acquisition_records],
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
    }
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
