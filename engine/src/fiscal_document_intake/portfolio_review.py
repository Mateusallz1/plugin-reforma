from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .acquisition import (
    ALLOWED_NATURES,
    _load_decisions,
    review_acquisitions_folder,
    write_acquisition_outputs,
)
from .core import ValidationError, _format_decimal

PORTFOLIO_FOLDER = ".reforma-tributaria"
DATABASE_FILE = "revisoes-carteira.sqlite3"
LOCAL_REPORT_FILE = "fila-revisao-carteira.local.md"
SUMMARY_FILE = "resumo-revisao-carteira.json"
EXPORT_FILE = "fila-revisao-carteira.csv"
SCOPES = {"ITEM", "COMPANY", "PORTFOLIO"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_ref(prefix: str, value: str, length: int = 16) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length].upper()
    return f"{prefix}-{digest}"


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).upper()


def _signature(record: dict[str, Any]) -> tuple[str, dict[str, str]]:
    fields = {
        "record_kind": _normalized(record.get("record_kind")),
        "product_code": _normalized(record.get("product_code")),
        "ncm": _normalized(record.get("ncm")),
        "cfop": _normalized(record.get("cfop")),
        "service_list_code": _normalized(record.get("service_list_code")),
        "cnae": _normalized(record.get("cnae")),
        "nbs": _normalized(record.get("nbs")),
        "municipal_tax_code": _normalized(record.get("municipal_tax_code")),
        "transport_modal": _normalized(record.get("transport_modal")),
        "description": _normalized(record.get("description")),
    }
    material = json.dumps(
        fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _hash_ref("GRP", material), fields


def _portfolio_paths(portfolio_root: Path | str) -> tuple[Path, Path, Path, Path]:
    root = Path(portfolio_root).expanduser().resolve()
    if not root.is_dir():
        raise ValidationError("A pasta da carteira informada não existe")
    state = root / PORTFOLIO_FOLDER
    state.mkdir(parents=True, exist_ok=True)
    return root, state / DATABASE_FILE, state / LOCAL_REPORT_FILE, state / SUMMARY_FILE


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS occurrences (
            occurrence_ref TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            company_ref TEXT NOT NULL,
            company_path TEXT NOT NULL,
            item_ref TEXT NOT NULL,
            record_kind TEXT NOT NULL,
            period TEXT NOT NULL,
            gross_amount TEXT NOT NULL,
            legal_evidence_status TEXT NOT NULL,
            signature_json TEXT NOT NULL,
            details_json TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            indexed_at TEXT NOT NULL,
            UNIQUE(company_ref, item_ref)
        );
        CREATE INDEX IF NOT EXISTS occurrences_group_active
            ON occurrences(group_id, active);
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            occurrence_ref TEXT NOT NULL,
            group_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            company_ref TEXT NOT NULL,
            item_ref TEXT NOT NULL,
            nature TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            note TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            UNIQUE(occurrence_ref)
        );
        CREATE TABLE IF NOT EXISTS approval_batches (
            request_id TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS decision_rules (
            rule_id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            selector TEXT NOT NULL,
            nature TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            note TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(group_id, scope, selector)
        );
        CREATE INDEX IF NOT EXISTS decision_rules_group_active
            ON decision_rules(group_id, active);
        """
    )
    return connection


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} deve ser JSON UTF-8 válido") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} deve conter um objeto JSON")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not value.get("item_ref"):
                raise ValidationError(
                    f"acquisition-items.local.jsonl possui linha inválida: {line_number}"
                )
            records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(
            "acquisition-items.local.jsonl deve ser JSONL UTF-8 válido"
        ) from error
    return records


def _company_ref(root: Path, company: Path, period: str) -> str:
    identity = company
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        year, month = period.split("-")
        period_names = {period, f"{month}-{year}", f"{year}{month}"}
        if company.name.casefold() in {name.casefold() for name in period_names}:
            identity = company.parent
    relative = identity.relative_to(root).as_posix().casefold()
    return _hash_ref("EMP", relative)


def _find_pending_occurrences(root: Path) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    pattern = f"05_REVISAO_AQUISICOES/{'acquisition-items.local.jsonl'}"
    for records_path in sorted(root.rglob("acquisition-items.local.jsonl")):
        if records_path.as_posix().casefold().endswith(pattern.casefold()) is False:
            continue
        company = records_path.parents[1]
        summary_path = records_path.parent / "acquisition-summary.json"
        if not summary_path.is_file():
            continue
        summary = _load_json(summary_path, "acquisition-summary.json")
        if summary.get("phase") != "ACQUISITION_REVIEW":
            continue
        approved, _ = _load_decisions(company)
        period = str(summary.get("scope", {}).get("period") or "")
        company_ref = _company_ref(root, company, period)
        for record in _load_jsonl(records_path):
            item_ref = str(record["item_ref"])
            if (
                record.get("nature_status") == "ANALYST_APPROVED"
                or item_ref in approved
            ):
                continue
            if record.get("nature_status") == "RESTRICTED_INPUT":
                continue
            group_id, signature = _signature(record)
            occurrence_ref = _hash_ref("OCO", f"{company_ref}:{item_ref}")
            details = {
                **signature,
                "analysis_group": _normalized(record.get("analysis_group")),
                "gross_amount": str(record.get("gross_amount") or "0.00"),
                "legal_evidence_status": _normalized(
                    record.get("legal_evidence_status")
                ),
            }
            occurrences.append(
                {
                    "occurrence_ref": occurrence_ref,
                    "group_id": group_id,
                    "company_ref": company_ref,
                    "company_path": str(company),
                    "item_ref": item_ref,
                    "record_kind": signature["record_kind"],
                    "period": period,
                    "gross_amount": details["gross_amount"],
                    "legal_evidence_status": details["legal_evidence_status"],
                    "signature_json": json.dumps(
                        signature,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "details_json": json.dumps(
                        details,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
    return occurrences


def _matching_rule(
    row: dict[str, Any], rules: list[dict[str, Any]]
) -> dict[str, Any] | None:
    matches = []
    priorities = {"PORTFOLIO": 1, "COMPANY": 2, "ITEM": 3}
    for rule in rules:
        if rule["group_id"] != row["group_id"]:
            continue
        if rule["scope"] == "COMPANY" and rule["selector"] != row["company_ref"]:
            continue
        if rule["scope"] == "ITEM" and rule["selector"] != row["occurrence_ref"]:
            continue
        matches.append(rule)
    if not matches:
        return None
    highest = max(priorities[rule["scope"]] for rule in matches)
    preferred = [rule for rule in matches if priorities[rule["scope"]] == highest]
    if len({rule["nature"] for rule in preferred}) != 1:
        raise ValidationError(
            "Existem regras conflitantes para uma ocorrência da carteira"
        )
    return max(preferred, key=lambda rule: rule["rule_id"])


def _apply_saved_rules(
    database: Path,
    rows: list[dict[str, Any]],
    ruleset_path: Path | str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with _connect(database) as connection:
        rules = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM decision_rules WHERE active = 1"
            ).fetchall()
        ]
    assignments: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        rule = _matching_rule(row, rules)
        if rule is not None:
            assignments.append((row, rule))
    if not assignments:
        return rows, {
            "auto_applied_occurrences": 0,
            "auto_applied_companies": 0,
            "reprocessed_companies": [],
            "reprocess_errors": [],
        }

    by_rule: dict[str, list[dict[str, Any]]] = {}
    rule_index: dict[str, dict[str, Any]] = {}
    for row, rule in assignments:
        by_rule.setdefault(rule["rule_id"], []).append(row)
        rule_index[rule["rule_id"]] = rule
    for rule_id, members in by_rule.items():
        rule = rule_index[rule_id]
        _write_decision_files(
            members,
            nature=rule["nature"],
            approved_by=rule["approved_by"],
            note=rule["note"],
        )

    reprocessed: list[str] = []
    reprocess_errors: list[str] = []
    if ruleset_path is not None:
        ruleset = Path(ruleset_path).expanduser().resolve()
        if not ruleset.is_file():
            raise ValidationError("O snapshot oficial informado não existe")
        companies = {
            row["company_ref"]: Path(row["company_path"]) for row, _ in assignments
        }
        for company_ref, company_path in sorted(companies.items()):
            try:
                result = review_acquisitions_folder(company_path, ruleset)
                write_acquisition_outputs(
                    result, company_path / "05_REVISAO_AQUISICOES"
                )
                reprocessed.append(company_ref)
            except (OSError, ValidationError):
                reprocess_errors.append(company_ref)

    applied_at = _utc_now()
    with _connect(database) as connection:
        for row, rule in assignments:
            connection.execute(
                """
                INSERT OR IGNORE INTO decisions (
                    request_id, occurrence_ref, group_id, scope, company_ref,
                    item_ref, nature, approved_by, note, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule["rule_id"],
                    row["occurrence_ref"],
                    row["group_id"],
                    rule["scope"],
                    row["company_ref"],
                    row["item_ref"],
                    rule["nature"],
                    rule["approved_by"],
                    rule["note"],
                    applied_at,
                ),
            )
            connection.execute(
                "UPDATE occurrences SET active = 0 WHERE occurrence_ref = ?",
                (row["occurrence_ref"],),
            )
    applied_refs = {row["occurrence_ref"] for row, _ in assignments}
    return [row for row in rows if row["occurrence_ref"] not in applied_refs], {
        "auto_applied_occurrences": len(assignments),
        "auto_applied_companies": len({row["company_ref"] for row, _ in assignments}),
        "reprocessed_companies": reprocessed,
        "reprocess_errors": reprocess_errors,
    }


def _index_portfolio(
    root: Path,
    database: Path,
    ruleset_path: Path | str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    occurrences = _find_pending_occurrences(root)
    indexed_at = _utc_now()
    with _connect(database) as connection:
        connection.execute("UPDATE occurrences SET active = 0")
        for item in occurrences:
            connection.execute(
                """
                INSERT INTO occurrences (
                    occurrence_ref, group_id, company_ref, company_path, item_ref,
                    record_kind, period, gross_amount, legal_evidence_status,
                    signature_json, details_json, active, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(occurrence_ref) DO UPDATE SET
                    group_id = excluded.group_id,
                    company_path = excluded.company_path,
                    record_kind = excluded.record_kind,
                    period = excluded.period,
                    gross_amount = excluded.gross_amount,
                    legal_evidence_status = excluded.legal_evidence_status,
                    signature_json = excluded.signature_json,
                    details_json = excluded.details_json,
                    active = 1,
                    indexed_at = excluded.indexed_at
                """,
                (
                    item["occurrence_ref"],
                    item["group_id"],
                    item["company_ref"],
                    item["company_path"],
                    item["item_ref"],
                    item["record_kind"],
                    item["period"],
                    item["gross_amount"],
                    item["legal_evidence_status"],
                    item["signature_json"],
                    item["details_json"],
                    indexed_at,
                ),
            )
        rows = connection.execute(
            "SELECT * FROM occurrences WHERE active = 1 ORDER BY group_id, occurrence_ref"
        ).fetchall()
    return _apply_saved_rules(database, [dict(row) for row in rows], ruleset_path)


def _amount_total(rows: list[dict[str, Any]]) -> str:
    total = Decimal(0)
    for row in rows:
        try:
            total += Decimal(str(row.get("gross_amount") or "0"))
        except InvalidOperation:
            continue
    return _format_decimal(total) or "0.00"


def _group_occurrences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["group_id"], []).append(row)
    result: list[dict[str, Any]] = []
    for group_id, members in grouped.items():
        kind = members[0]["record_kind"]
        details = json.loads(members[0]["details_json"])
        result.append(
            {
                "group_id": group_id,
                "record_kind": kind,
                "occurrence_count": len(members),
                "company_count": len({item["company_ref"] for item in members}),
                "company_refs": sorted({item["company_ref"] for item in members}),
                "occurrence_refs": [item["occurrence_ref"] for item in members],
                "periods": sorted({item["period"] for item in members}),
                "gross_amount": _amount_total(members),
                "evidence_status_counts": dict(
                    sorted(
                        Counter(
                            item["legal_evidence_status"] for item in members
                        ).items()
                    )
                ),
                "allowed_natures": sorted(ALLOWED_NATURES.get(kind, set())),
                "details": details,
                "members": members,
            }
        )
    return sorted(result, key=lambda item: item["group_id"])


def _public_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        key: group[key]
        for key in (
            "group_id",
            "record_kind",
            "occurrence_count",
            "company_count",
            "company_refs",
            "occurrence_refs",
            "periods",
            "gross_amount",
            "evidence_status_counts",
            "allowed_natures",
        )
    }


def _write_local_report(groups: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Fila local de revisão da carteira",
        "",
        "Este arquivo contém detalhes comerciais locais. Não o copie para o Git ou para serviços externos.",
        "",
    ]
    if not groups:
        lines.append("Nenhuma classificação de aquisição está pendente.")
    for group in groups:
        details = group["details"]
        lines.extend(
            [
                f"## {group['group_id']}",
                "",
                f"- Tipo: `{group['record_kind']}`",
                f"- Empresas: {group['company_count']}",
                f"- Ocorrências: {group['occurrence_count']}",
                f"- Valor documental: {group['gross_amount']}",
                f"- Descrição: {details.get('description') or 'não informada'}",
                f"- Código do produto: {details.get('product_code') or 'não informado'}",
                f"- NCM: {details.get('ncm') or 'não informado'}",
                f"- CFOP: {details.get('cfop') or 'não informado'}",
                f"- Item da lista de serviços: {details.get('service_list_code') or 'não informado'}",
                f"- CNAE: {details.get('cnae') or 'não informado'}",
                f"- NBS: {details.get('nbs') or 'não informado'}",
                f"- Naturezas permitidas: {', '.join(group['allowed_natures'])}",
                f"- Referências de empresa: {', '.join(group['company_refs'])}",
                f"- Referências de ocorrência: {', '.join(group['occurrence_refs'])}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def review_portfolio(
    portfolio_root: Path | str,
    *,
    page: int = 1,
    page_size: int = 10,
    ruleset_path: Path | str | None = None,
) -> dict[str, Any]:
    if page < 1 or not 1 <= page_size <= 100:
        raise ValidationError(
            "Página deve ser positiva e o tamanho deve ficar entre 1 e 100"
        )
    root, database, report_path, summary_path = _portfolio_paths(portfolio_root)
    rows, automatic = _index_portfolio(root, database, ruleset_path)
    groups = _group_occurrences(rows)
    start = (page - 1) * page_size
    selected = groups[start : start + page_size]
    result = {
        "status": "PENDING_REVIEW" if groups else "NO_PENDING_REVIEW",
        "group_count": len(groups),
        "occurrence_count": len(rows),
        "company_count": len({row["company_ref"] for row in rows}),
        "page": page,
        "page_size": page_size,
        "has_more": start + page_size < len(groups),
        "groups": [_public_group(group) for group in selected],
        "local_report": str(report_path),
        **automatic,
    }
    _write_local_report(groups, report_path)
    summary_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _read_decision_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    required = ["item_ref", "natureza", "status", "aprovado_por", "observacao"]
    if not path.is_file():
        return required, []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(4096)
            stream.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.DictReader(stream, delimiter=delimiter)
            fieldnames = list(reader.fieldnames or [])
            if not {"item_ref", "natureza", "status", "aprovado_por"}.issubset(
                fieldnames
            ):
                raise ValidationError(
                    "classificacao-aquisicoes.csv possui colunas incompatíveis"
                )
            for field in required:
                if field not in fieldnames:
                    fieldnames.append(field)
            return fieldnames, [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValidationError(
            "classificacao-aquisicoes.csv deve ser CSV UTF-8 válido"
        ) from error


def _decision_content(
    path: Path,
    selected: list[dict[str, Any]],
    *,
    nature: str,
    approved_by: str,
    note: str,
) -> str:
    fieldnames, rows = _read_decision_rows(path)
    selected_by_ref = {item["item_ref"]: item for item in selected}
    seen: set[str] = set()
    for row in rows:
        item_ref = (row.get("item_ref") or "").strip()
        if item_ref not in selected_by_ref:
            continue
        status = (row.get("status") or "").strip().upper()
        existing_nature = (row.get("natureza") or "").strip().upper()
        if status == "APROVADO" and existing_nature and existing_nature != nature:
            raise ValidationError(
                "Existe decisão local conflitante para uma ocorrência selecionada"
            )
        row.update(
            {
                "natureza": nature,
                "status": "APROVADO",
                "aprovado_por": approved_by,
                "observacao": note,
            }
        )
        seen.add(item_ref)
    for item_ref in sorted(set(selected_by_ref) - seen):
        row = {field: "" for field in fieldnames}
        row.update(
            {
                "item_ref": item_ref,
                "natureza": nature,
                "status": "APROVADO",
                "aprovado_por": approved_by,
                "observacao": note,
            }
        )
        rows.append(row)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=fieldnames, delimiter=";", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _write_decision_files(
    selected: list[dict[str, Any]],
    *,
    nature: str,
    approved_by: str,
    note: str,
) -> list[Path]:
    by_company: dict[str, list[dict[str, Any]]] = {}
    for item in selected:
        by_company.setdefault(item["company_path"], []).append(item)
    prepared: list[tuple[Path, str, bytes | None]] = []
    for company_path, members in by_company.items():
        path = Path(company_path) / "00_CONTROLE" / "classificacao-aquisicoes.csv"
        original = path.read_bytes() if path.is_file() else None
        content = _decision_content(
            path,
            members,
            nature=nature,
            approved_by=approved_by,
            note=note,
        )
        prepared.append((path, content, original))
    written: list[Path] = []
    try:
        for path, content, _ in prepared:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(content, encoding="utf-8-sig")
            temporary.replace(path)
            written.append(path)
    except OSError:
        for path, _, original in prepared:
            if path not in written:
                continue
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    return written


def _request_id(material: dict[str, str]) -> str:
    value = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _hash_ref("APR", value, 24)


def approve_portfolio_group(
    portfolio_root: Path | str,
    *,
    group_id: str,
    nature: str,
    scope: str,
    approved_by: str,
    note: str = "",
    company_ref: str | None = None,
    occurrence_ref: str | None = None,
    ruleset_path: Path | str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    group_id = _normalized(group_id)
    nature = _normalized(nature)
    scope = _normalized(scope)
    approved_by = str(approved_by or "").strip()
    note = str(note or "").strip()
    if scope not in SCOPES:
        raise ValidationError("O alcance deve ser ITEM, COMPANY ou PORTFOLIO")
    if not approved_by:
        raise ValidationError("A aprovação exige a identificação do analista")
    request_material = {
        "group_id": group_id,
        "nature": nature,
        "scope": scope,
        "approved_by": approved_by,
        "company_ref": _normalized(company_ref),
        "occurrence_ref": _normalized(occurrence_ref),
    }
    request_id = _normalized(request_id) or _request_id(request_material)
    root, database, _, _ = _portfolio_paths(portfolio_root)
    with _connect(database) as connection:
        previous = connection.execute(
            "SELECT result_json FROM approval_batches WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if previous is not None:
            return json.loads(previous["result_json"])

    if ruleset_path is not None:
        ruleset = Path(ruleset_path).expanduser().resolve()
        if not ruleset.is_file():
            raise ValidationError("O snapshot oficial informado não existe")
    rows, _ = _index_portfolio(root, database, ruleset_path)
    selected = [row for row in rows if row["group_id"] == group_id]
    if not selected:
        raise ValidationError("O grupo informado não está pendente nesta carteira")
    kind = selected[0]["record_kind"]
    if nature not in ALLOWED_NATURES.get(kind, set()):
        raise ValidationError("A natureza informada é incompatível com o tipo do grupo")
    if scope == "COMPANY":
        if not company_ref:
            raise ValidationError("O alcance COMPANY exige company_ref")
        selected = [
            row for row in selected if row["company_ref"] == _normalized(company_ref)
        ]
    elif scope == "ITEM":
        if not occurrence_ref:
            raise ValidationError("O alcance ITEM exige occurrence_ref")
        selected = [
            row
            for row in selected
            if row["occurrence_ref"] == _normalized(occurrence_ref)
        ]
    if not selected:
        raise ValidationError(
            "O alcance informado não selecionou ocorrências pendentes"
        )

    selector = (
        selected[0]["occurrence_ref"]
        if scope == "ITEM"
        else selected[0]["company_ref"]
        if scope == "COMPANY"
        else ""
    )
    with _connect(database) as connection:
        conflicting_rule = connection.execute(
            """
            SELECT nature FROM decision_rules
            WHERE group_id = ? AND scope = ? AND selector = ? AND active = 1
            """,
            (group_id, scope, selector),
        ).fetchone()
        if conflicting_rule is not None and conflicting_rule["nature"] != nature:
            raise ValidationError("Existe regra ativa conflitante para o mesmo alcance")

    _write_decision_files(selected, nature=nature, approved_by=approved_by, note=note)
    approved_at = _utc_now()
    reprocessed: list[str] = []
    reprocess_errors: list[str] = []
    if ruleset_path is not None:
        companies = {row["company_ref"]: Path(row["company_path"]) for row in selected}
        for selected_company_ref, company_path in sorted(companies.items()):
            try:
                result = review_acquisitions_folder(company_path, ruleset)
                write_acquisition_outputs(
                    result, company_path / "05_REVISAO_AQUISICOES"
                )
                reprocessed.append(selected_company_ref)
            except (OSError, ValidationError):
                reprocess_errors.append(selected_company_ref)

    result = {
        "status": (
            "APPROVED_WITH_REPROCESS_ERRORS" if reprocess_errors else "APPROVED"
        ),
        "request_id": request_id,
        "group_id": group_id,
        "nature": nature,
        "scope": scope,
        "affected_occurrences": len(selected),
        "affected_companies": len({row["company_ref"] for row in selected}),
        "company_refs": sorted({row["company_ref"] for row in selected}),
        "reprocessed_companies": reprocessed,
        "reprocess_errors": reprocess_errors,
        "approved_by": approved_by,
        "approved_at": approved_at,
    }
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
    with _connect(database) as connection:
        for row in selected:
            connection.execute(
                """
                INSERT OR IGNORE INTO decisions (
                    request_id, occurrence_ref, group_id, scope, company_ref,
                    item_ref, nature, approved_by, note, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    row["occurrence_ref"],
                    group_id,
                    scope,
                    row["company_ref"],
                    row["item_ref"],
                    nature,
                    approved_by,
                    note,
                    approved_at,
                ),
            )
            connection.execute(
                "UPDATE occurrences SET active = 0 WHERE occurrence_ref = ?",
                (row["occurrence_ref"],),
            )
        connection.execute(
            "INSERT INTO approval_batches (request_id, result_json, created_at) VALUES (?, ?, ?)",
            (request_id, serialized, approved_at),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO decision_rules (
                rule_id, group_id, scope, selector, nature, approved_by,
                note, approved_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                request_id,
                group_id,
                scope,
                selector,
                nature,
                approved_by,
                note,
                approved_at,
            ),
        )
    return result


def export_portfolio_review(portfolio_root: Path | str) -> dict[str, Any]:
    root, database, _, _ = _portfolio_paths(portfolio_root)
    rows, _ = _index_portfolio(root, database)
    groups = _group_occurrences(rows)
    export_path = root / PORTFOLIO_FOLDER / EXPORT_FILE
    columns = [
        "group_id",
        "record_kind",
        "company_count",
        "occurrence_count",
        "gross_amount",
        "description",
        "product_code",
        "ncm",
        "cfop",
        "service_list_code",
        "cnae",
        "nbs",
        "allowed_natures",
    ]
    with export_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=";")
        writer.writeheader()
        for group in groups:
            details = group["details"]
            writer.writerow(
                {
                    "group_id": group["group_id"],
                    "record_kind": group["record_kind"],
                    "company_count": group["company_count"],
                    "occurrence_count": group["occurrence_count"],
                    "gross_amount": group["gross_amount"],
                    "description": details.get("description") or "",
                    "product_code": details.get("product_code") or "",
                    "ncm": details.get("ncm") or "",
                    "cfop": details.get("cfop") or "",
                    "service_list_code": details.get("service_list_code") or "",
                    "cnae": details.get("cnae") or "",
                    "nbs": details.get("nbs") or "",
                    "allowed_natures": ",".join(group["allowed_natures"]),
                }
            )
    return {
        "status": "EXPORTED",
        "group_count": len(groups),
        "output": str(export_path),
    }
