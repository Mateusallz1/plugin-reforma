from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .core import ValidationError
from .revenue import REVENUE_SCHEMA_VERSION

SIMPLE_RECONCILIATION_SCHEMA = (
    "br.com.planejamento-reforma-tributaria/simple-revenue-reconciliation"
)
SIMPLE_RECONCILIATION_SCHEMA_VERSION = "1.2.0"
RECONCILED_STATUSES = frozenset({"RECONCILED", "NO_MOVEMENT"})
MONEY_PATTERN = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
PERIOD_FOLDER_PATTERN = re.compile(
    r"(?:0[1-9]|1[0-2])-20\d{2}|20\d{2}-(?:0[1-9]|1[0-2])"
)


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return ascii_text.upper().replace("\u00a0", " ")


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    text = str(value or "0").strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise ValidationError(
            f"Valor monetário inválido no PGDAS-D: {value}"
        ) from error


def _money(value: Decimal | str | int) -> str:
    return f"{_decimal(value).quantize(Decimal('0.01')):.2f}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_ref(path: Path) -> str:
    return "PGDAS-SRC-" + _sha256(path)[:12].upper()


def _establishment_ref(taxpayer_id: str) -> str:
    digits = _digits(taxpayer_id)
    if len(digits) != 14:
        raise ValidationError("CNPJ de estabelecimento inválido no PGDAS-D")
    digest = hashlib.sha256(digits.encode()).hexdigest()[:10].upper()
    return f"ESTAB-{digest}"


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"UC-003C exige {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} deve ser JSON UTF-8 válido") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} deve conter um objeto JSON")
    return value


def discover_group_period_folders(
    portfolio_root: Path | str, period: str
) -> list[Path]:
    """Find establishment period folders already processed under one root."""

    root = Path(portfolio_root).expanduser().resolve()
    if not root.is_dir():
        raise ValidationError("A pasta da carteira informada não existe")
    if re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", period) is None:
        raise ValidationError("A competência deve estar no formato AAAA-MM")
    folders: set[Path] = set()
    for summary_path in root.rglob("revenue-summary.json"):
        folder = summary_path.parent.parent
        if not PERIOD_FOLDER_PATTERN.fullmatch(folder.name):
            continue
        normalized_period = (
            f"{folder.name[3:]}-{folder.name[:2]}"
            if re.fullmatch(r"(?:0[1-9]|1[0-2])-20\d{2}", folder.name)
            else folder.name
        )
        if normalized_period != period:
            continue
        if any(
            part in {"SN", ".reforma-tributaria"}
            for part in folder.relative_to(root).parts
        ):
            continue
        folders.add(folder)
    return sorted(folders, key=lambda item: item.as_posix().casefold())


def _read_pdf(path: Path) -> tuple[str, int]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValidationError("PGDAS-D protegido por senha não é suportado")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ValidationError:
        raise
    except Exception as error:
        raise ValidationError("Não foi possível ler um PDF do PGDAS-D") from error
    text = "\n".join(pages)
    if not text.strip():
        raise ValidationError("PDF do PGDAS-D não possui texto extraível")
    return text, len(pages)


def _source_role(path: Path) -> str:
    name = _normalized_text(path.stem)
    for role in ("DECLARACAO", "EXTRATO", "RECIBO", "DAS"):
        if role in name:
            return role
    return "AUXILIAR"


def _load_pgdas_sources(folder: Path) -> tuple[Path, str, dict[str, Any]]:
    if not folder.is_dir():
        raise ValidationError("A pasta do PGDAS-D não existe")
    pdf_paths = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not pdf_paths:
        raise ValidationError("A pasta informada não contém PDFs do PGDAS-D")

    sources: list[dict[str, Any]] = []
    declaration_candidates: list[tuple[Path, str]] = []
    for path in pdf_paths:
        text, pages = _read_pdf(path)
        role = _source_role(path)
        source = {
            "source_ref": _source_ref(path),
            "role": role,
            "sha256": _sha256(path),
            "pages": pages,
        }
        sources.append(source)
        normalized = _normalized_text(text)
        if role == "DECLARACAO" or (
            "PROGRAMA GERADOR DO DOCUMENTO DE ARRECADACAO" in normalized
            and "INFORMACOES DA DECLARACAO POR ESTABELECIMENTO" in normalized
        ):
            declaration_candidates.append((path, text))

    if not declaration_candidates:
        raise ValidationError("Declaração oficial do PGDAS-D não localizada")
    if len(declaration_candidates) > 1:
        raise ValidationError(
            "Mais de uma declaração PGDAS-D foi localizada; selecione somente a declaração vigente"
        )
    declaration_path, declaration_text = declaration_candidates[0]
    lock = {
        "authority_source_ref": _source_ref(declaration_path),
        "sources": sorted(sources, key=lambda item: (item["role"], item["source_ref"])),
    }
    return declaration_path, declaration_text, lock


def _line_with(text: str, prefix: str) -> str:
    for line in text.splitlines():
        normalized = " ".join(_normalized_text(line).split())
        if normalized.startswith(prefix):
            return normalized
    raise ValidationError(f"Campo obrigatório ausente na declaração PGDAS-D: {prefix}")


def _activity(value: str) -> str:
    normalized = _normalized_text(value)
    if "REVENDA DE MERCADORIAS" in normalized or "VENDA DE MERCADORIAS" in normalized:
        return "COMERCIO"
    if "PRESTACAO DE SERVICOS" in normalized or "LOCACAO DE BENS" in normalized:
        return "SERVICOS"
    if "TRANSPORTE" in normalized:
        return "TRANSPORTE"
    return "OUTRAS"


def _parse_declaration(text: str, authority_ref: str) -> dict[str, Any]:
    normalized = _normalized_text(text)
    compact = "\n".join(" ".join(line.split()) for line in normalized.splitlines())

    period_match = re.search(
        r"PERIODO DE APURACAO:\s*\d{2}/(\d{2})/(\d{4})\s+A\s+\d{2}/\d{2}/\d{4}",
        compact,
    )
    if not period_match:
        raise ValidationError("Competência não localizada na declaração PGDAS-D")
    period = f"{period_match.group(2)}-{period_match.group(1)}"

    regime_match = re.search(r"REGIME DE APURACAO:\s*(COMPETENCIA|CAIXA)", compact)
    if not regime_match:
        raise ValidationError("Regime de apuração não localizado no PGDAS-D")
    regime = regime_match.group(1)

    declaration_type = (
        "RETIFICADORA" if "DECLARACAO RETIFICADORA" in compact else "ORIGINAL"
    )
    declaration_number_match = re.search(r"N.? DA DECLARACAO:\s*(\d{10,})", compact)
    if not declaration_number_match:
        raise ValidationError("Número da declaração PGDAS-D não localizado")
    declaration_ref = (
        "PGDAS-DECL-"
        + hashlib.sha256(declaration_number_match.group(1).encode())
        .hexdigest()[:12]
        .upper()
    )

    revenue_line = _line_with(compact, "RECEITA BRUTA DO PA (RPA)")
    total_values = MONEY_PATTERN.findall(revenue_line)
    if len(total_values) < 3:
        raise ValidationError("Total de receita do PA não foi reconhecido no PGDAS-D")
    internal_amount, external_amount, declared_total = map(_decimal, total_values[-3:])

    establishment_pattern = re.compile(
        r"CNPJ ESTABELECIMENTO:\s*([\d./-]{14,18})(.*?)(?=CNPJ ESTABELECIMENTO:|2\.8\)|3\. INFORMACOES DA RECEPCAO|$)",
        re.DOTALL,
    )
    activity_pattern = re.compile(
        r"VALOR DO DEBITO POR TRIBUTO PARA A ATIVIDADE \(R\$\):\s*(.*?)\s*RECEITA BRUTA INFORMADA:\s*R\$\s*([\d.]+,\d{2})",
        re.DOTALL,
    )
    establishments: list[dict[str, Any]] = []
    for match in establishment_pattern.finditer(compact):
        taxpayer_id = _digits(match.group(1))
        activities: dict[str, Decimal] = defaultdict(Decimal)
        for activity_match in activity_pattern.finditer(match.group(2)):
            activities[_activity(activity_match.group(1))] += _decimal(
                activity_match.group(2)
            )
        if not activities:
            raise ValidationError(
                "Receitas por atividade não localizadas para um estabelecimento do PGDAS-D"
            )
        establishments.append(
            {
                "establishment_ref": _establishment_ref(taxpayer_id),
                "activities": {
                    key: _money(value) for key, value in sorted(activities.items())
                },
                "declared_total": _money(sum(activities.values(), Decimal(0))),
            }
        )
    if not establishments:
        raise ValidationError("Estabelecimentos não localizados na declaração PGDAS-D")

    establishments_total = sum(
        (_decimal(item["declared_total"]) for item in establishments), Decimal(0)
    )
    if establishments_total != declared_total:
        raise ValidationError(
            "Total do PGDAS-D diverge da soma das receitas por estabelecimento"
        )

    return {
        "authority_source_ref": authority_ref,
        "declaration_ref": declaration_ref,
        "declaration_type": declaration_type,
        "period": period,
        "revenue_regime": regime,
        "market_internal": _money(internal_amount),
        "market_external": _money(external_amount),
        "declared_total": _money(declared_total),
        "establishments": sorted(
            establishments, key=lambda item: item["establishment_ref"]
        ),
    }


def _documentary_activities(revenue_summary: dict[str, Any]) -> dict[str, str]:
    totals = revenue_summary.get("totals", {})
    goods = _decimal(totals.get("gross_revenue_goods")) - _decimal(
        totals.get("sales_returns_inbound")
    )
    activities = {
        "COMERCIO": _money(goods),
        "SERVICOS": _money(totals.get("gross_revenue_services")),
        "TRANSPORTE": _money(totals.get("gross_revenue_transport")),
        "OUTRAS": _money(totals.get("other_revenue")),
    }
    return {key: value for key, value in activities.items() if _decimal(value) != 0}


def _status(declared: Decimal, documentary: Decimal | None) -> str:
    if documentary is None:
        return "ESTABLISHMENT_DOCUMENTS_MISSING"
    if declared == 0 and documentary == 0:
        return "NO_MOVEMENT"
    if declared == documentary:
        return "RECONCILED"
    if declared > 0 and documentary == 0:
        return "DECLARED_WITHOUT_DOCUMENT_SUPPORT"
    if declared == 0 and documentary > 0:
        return "PGDAS_ZERO_WITH_DOCUMENT_REVENUE"
    if documentary > declared:
        return "DOCUMENTS_ABOVE_PGDAS"
    return "DECLARED_ABOVE_DOCUMENTS"


def reconcile_simple_revenue(
    folder: Path | str, pgdas_folder: Path | str
) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta empresarial informada não existe")
    revenue_summary = _load_json(
        base / "06_REVISAO_RECEITAS" / "revenue-summary.json",
        "06_REVISAO_RECEITAS/revenue-summary.json",
    )
    if (
        revenue_summary.get("use_case") != "UC-003"
        or revenue_summary.get("phase") != "REVENUE_REVIEW"
        or revenue_summary.get("schema_version") != REVENUE_SCHEMA_VERSION
    ):
        raise ValidationError(
            "UC-003C exige saída da revisão de receitas na versão vigente"
        )
    if not revenue_summary.get("gates", {}).get("revenue_population_ready"):
        raise ValidationError("A população de receitas do UC-003B não está pronta")

    pgdas_path = Path(pgdas_folder).expanduser().resolve()
    declaration_path, declaration_text, source_lock = _load_pgdas_sources(pgdas_path)
    declaration = _parse_declaration(declaration_text, _source_ref(declaration_path))
    period = revenue_summary.get("scope", {}).get("period")
    if period != declaration["period"]:
        raise ValidationError("Competência do PGDAS-D diverge da revisão de receitas")

    documentary_ref = revenue_summary.get("scope", {}).get("establishment_ref")
    if not documentary_ref:
        raise ValidationError("UC-003B não informou o estabelecimento documental")
    documentary_activities = _documentary_activities(revenue_summary)
    declared_refs = {
        establishment["establishment_ref"]
        for establishment in declaration["establishments"]
    }
    if documentary_ref not in declared_refs:
        raise ValidationError(
            "O estabelecimento documental não foi localizado na declaração PGDAS-D"
        )

    records: list[dict[str, Any]] = []
    for establishment in declaration["establishments"]:
        establishment_ref = establishment["establishment_ref"]
        declared_activities = establishment["activities"]
        activities = set(declared_activities)
        if establishment_ref == documentary_ref:
            activities.update(documentary_activities)
        for activity in sorted(activities):
            declared = _decimal(declared_activities.get(activity))
            documentary = (
                _decimal(documentary_activities.get(activity))
                if establishment_ref == documentary_ref
                else None
            )
            difference = declared - documentary if documentary is not None else declared
            records.append(
                {
                    "establishment_ref": establishment_ref,
                    "activity": activity,
                    "declared_amount": _money(declared),
                    "documentary_amount": (
                        _money(documentary) if documentary is not None else None
                    ),
                    "difference": _money(difference),
                    "status": _status(declared, documentary),
                }
            )

    matched_records = [
        record for record in records if record["establishment_ref"] == documentary_ref
    ]
    missing_establishments = sorted(declared_refs - {documentary_ref})
    documentary_scope_reconciled = all(
        record["status"] in RECONCILED_STATUSES for record in matched_records
    )
    group_coverage_complete = not missing_establishments
    analyst_review_required = (
        not documentary_scope_reconciled or not group_coverage_complete
    )

    declared_matched = sum(
        (_decimal(record["declared_amount"]) for record in matched_records), Decimal(0)
    )
    documentary_total = sum(
        (_decimal(value) for value in documentary_activities.values()), Decimal(0)
    )
    uncovered_total = sum(
        (
            _decimal(establishment["declared_total"])
            for establishment in declaration["establishments"]
            if establishment["establishment_ref"] in missing_establishments
        ),
        Decimal(0),
    )

    material = {
        "revenue_review_id": revenue_summary["review_id"],
        "declaration_hash": _sha256(declaration_path),
        "period": period,
        "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
    }
    reconciliation_id = (
        "SNR-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        )
        .hexdigest()[:16]
        .upper()
    )

    status = (
        "SIMPLE_REVENUE_RECONCILED"
        if documentary_scope_reconciled and group_coverage_complete
        else "SIMPLE_REVENUE_PARTIAL_COVERAGE"
        if documentary_scope_reconciled and not group_coverage_complete
        else "SIMPLE_REVENUE_REVIEW_REQUIRED"
    )
    warnings = [
        {
            "code": "ESTABLISHMENT_DOCUMENTS_MISSING",
            "ref": establishment_ref,
        }
        for establishment_ref in missing_establishments
    ]
    warnings.extend(
        {"code": record["status"], "ref": record["establishment_ref"]}
        for record in matched_records
        if record["status"] not in RECONCILED_STATUSES
    )
    if declaration["revenue_regime"] == "CAIXA":
        warnings.append(
            {
                "code": "REVENUE_REGIME_CAIXA",
                "ref": "PGDAS_DECLARATION",
                "severity": "WARNING",
            }
        )

    return {
        "schema": SIMPLE_RECONCILIATION_SCHEMA,
        "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
        "use_case": "UC-003C",
        "phase": "SIMPLE_REVENUE_RECONCILIATION",
        "reconciliation_id": reconciliation_id,
        "revenue_review_id": revenue_summary["review_id"],
        "status": status,
        "scope": {
            "entity_ref": revenue_summary["scope"]["entity_ref"],
            "documentary_establishment_ref": documentary_ref,
            "period": period,
            "revenue_regime": declaration["revenue_regime"],
            "pgdas_establishments": len(declaration["establishments"]),
            "documentary_establishments": 1,
        },
        "pgdas": {
            key: value for key, value in declaration.items() if key != "establishments"
        },
        "coverage": {
            "covered_establishment_refs": [documentary_ref],
            "missing_establishment_refs": missing_establishments,
        },
        "totals": {
            "pgdas_group_declared": declaration["declared_total"],
            "pgdas_matched_establishment": _money(declared_matched),
            "documentary_matched_establishment": _money(documentary_total),
            "matched_difference": _money(declared_matched - documentary_total),
            "uncovered_pgdas_revenue": _money(uncovered_total),
        },
        "status_counts": dict(
            sorted(
                {
                    value: sum(record["status"] == value for record in records)
                    for value in {record["status"] for record in records}
                }.items()
            )
        ),
        "source_lock": source_lock,
        "warnings": warnings,
        "gates": {
            "simple_reconciliation_execution_ready": True,
            "documentary_scope_reconciled": documentary_scope_reconciled,
            "group_coverage_complete": group_coverage_complete,
            "analyst_review_required": analyst_review_required,
            "non_issuance_confirmed": False,
            "uc004_planning_authorized": False,
        },
        "limitations": [
            "Ausência de documento na base fornecida não comprova não emissão de nota fiscal.",
            "A conciliação usa a receita declarada no PGDAS-D e não conclui tratamento de IBS/CBS.",
            "Deduções, diferenças temporais e declarações retificadoras exigem evidência e revisão do analista.",
            "No regime CAIXA, a comparação documental exige análise temporal específica; o aviso não bloqueia a conciliação.",
            "DAS gerado não comprova pagamento; a arrecadação não é objeto deste UC.",
        ],
        "_private_records": records,
    }


def reconcile_simple_revenue_group(
    folders: list[Path | str], pgdas_folder: Path | str
) -> dict[str, Any]:
    """Reconcile all explicitly discovered establishments in one PGDAS-D group."""

    bases = sorted({Path(folder).expanduser().resolve() for folder in folders})
    if len(bases) < 2:
        raise ValidationError(
            "A consolidação de grupo exige pelo menos dois estabelecimentos"
        )
    summaries: list[dict[str, Any]] = []
    for base in bases:
        if not base.is_dir():
            raise ValidationError("Uma pasta de estabelecimento do grupo não existe")
        summary = _load_json(
            base / "06_REVISAO_RECEITAS" / "revenue-summary.json",
            "06_REVISAO_RECEITAS/revenue-summary.json",
        )
        if (
            summary.get("use_case") != "UC-003"
            or summary.get("phase") != "REVENUE_REVIEW"
            or summary.get("schema_version") != REVENUE_SCHEMA_VERSION
        ):
            raise ValidationError(
                "A consolidação exige revisões de receitas na versão vigente"
            )
        if not summary.get("gates", {}).get("revenue_population_ready"):
            raise ValidationError(
                "A consolidação exige população de receitas pronta em todos os estabelecimentos"
            )
        summaries.append(summary)

    entity_refs = {summary.get("scope", {}).get("entity_ref") for summary in summaries}
    periods = {summary.get("scope", {}).get("period") for summary in summaries}
    establishment_refs = [
        summary.get("scope", {}).get("establishment_ref") for summary in summaries
    ]
    if None in entity_refs or len(entity_refs) != 1:
        raise ValidationError("As pastas do grupo não comprovam a mesma empresa")
    if None in periods or len(periods) != 1:
        raise ValidationError("As pastas do grupo devem ter a mesma competência")
    if any(not reference for reference in establishment_refs) or len(
        set(establishment_refs)
    ) != len(establishment_refs):
        raise ValidationError(
            "As pastas do grupo devem representar estabelecimentos distintos"
        )

    pgdas_path = Path(pgdas_folder).expanduser().resolve()
    declaration_path, declaration_text, source_lock = _load_pgdas_sources(pgdas_path)
    declaration = _parse_declaration(declaration_text, _source_ref(declaration_path))
    period = next(iter(periods))
    if period != declaration["period"]:
        raise ValidationError("Competência do PGDAS-D diverge das revisões de receitas")

    documentary_by_ref = {
        summary["scope"]["establishment_ref"]: _documentary_activities(summary)
        for summary in summaries
    }
    declared_refs = {
        establishment["establishment_ref"]
        for establishment in declaration["establishments"]
    }
    documentary_refs = set(documentary_by_ref)
    unexpected_refs = documentary_refs - declared_refs
    if unexpected_refs:
        raise ValidationError(
            "Um estabelecimento documental do grupo não foi localizado no PGDAS-D"
        )

    records: list[dict[str, Any]] = []
    for establishment in declaration["establishments"]:
        establishment_ref = establishment["establishment_ref"]
        declared_activities = establishment["activities"]
        documentary_activities = documentary_by_ref.get(establishment_ref)
        activities = set(declared_activities)
        if documentary_activities is not None:
            activities.update(documentary_activities)
        for activity in sorted(activities):
            declared = _decimal(declared_activities.get(activity))
            documentary = (
                _decimal(documentary_activities.get(activity))
                if documentary_activities is not None
                else None
            )
            records.append(
                {
                    "establishment_ref": establishment_ref,
                    "activity": activity,
                    "declared_amount": _money(declared),
                    "documentary_amount": (
                        _money(documentary) if documentary is not None else None
                    ),
                    "difference": _money(
                        declared - documentary if documentary is not None else declared
                    ),
                    "status": _status(declared, documentary),
                }
            )

    covered_records = [
        record for record in records if record["establishment_ref"] in documentary_refs
    ]
    documentary_scope_reconciled = all(
        record["status"] in RECONCILED_STATUSES for record in covered_records
    )
    group_coverage_complete = declared_refs == documentary_refs
    analyst_review_required = (
        not documentary_scope_reconciled or not group_coverage_complete
    )
    declared_matched = sum(
        (_decimal(record["declared_amount"]) for record in covered_records),
        Decimal(0),
    )
    documentary_total = sum(
        (
            _decimal(value)
            for activities in documentary_by_ref.values()
            for value in activities.values()
        ),
        Decimal(0),
    )
    uncovered_total = sum(
        (
            _decimal(establishment["declared_total"])
            for establishment in declaration["establishments"]
            if establishment["establishment_ref"] not in documentary_refs
        ),
        Decimal(0),
    )
    missing_establishments = sorted(declared_refs - documentary_refs)
    material = {
        "revenue_review_ids": sorted(
            summary["review_id"] for summary in summaries if summary.get("review_id")
        ),
        "declaration_hash": _sha256(declaration_path),
        "period": period,
        "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
    }
    reconciliation_id = (
        "SNG-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        )
        .hexdigest()[:16]
        .upper()
    )
    status = (
        "SIMPLE_REVENUE_RECONCILED"
        if documentary_scope_reconciled and group_coverage_complete
        else "SIMPLE_REVENUE_PARTIAL_COVERAGE"
        if documentary_scope_reconciled and not group_coverage_complete
        else "SIMPLE_REVENUE_REVIEW_REQUIRED"
    )
    warnings = [
        {"code": "ESTABLISHMENT_DOCUMENTS_MISSING", "ref": reference}
        for reference in missing_establishments
    ]
    warnings.extend(
        {"code": record["status"], "ref": record["establishment_ref"]}
        for record in covered_records
        if record["status"] not in RECONCILED_STATUSES
    )
    if declaration["revenue_regime"] == "CAIXA":
        warnings.append(
            {
                "code": "REVENUE_REGIME_CAIXA",
                "ref": "PGDAS_DECLARATION",
                "severity": "WARNING",
            }
        )
    return {
        "schema": SIMPLE_RECONCILIATION_SCHEMA,
        "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
        "use_case": "UC-003C",
        "phase": "SIMPLE_REVENUE_GROUP_RECONCILIATION",
        "reconciliation_id": reconciliation_id,
        "revenue_review_ids": material["revenue_review_ids"],
        "status": status,
        "scope": {
            "mode": "GROUP",
            "entity_ref": next(iter(entity_refs)),
            "documentary_establishment_ref": "GROUP",
            "period": period,
            "revenue_regime": declaration["revenue_regime"],
            "pgdas_establishments": len(declaration["establishments"]),
            "documentary_establishments": len(documentary_refs),
        },
        "pgdas": {
            key: value for key, value in declaration.items() if key != "establishments"
        },
        "coverage": {
            "covered_establishment_refs": sorted(documentary_refs),
            "missing_establishment_refs": missing_establishments,
        },
        "totals": {
            "pgdas_group_declared": declaration["declared_total"],
            "pgdas_matched_establishment": _money(declared_matched),
            "documentary_matched_establishment": _money(documentary_total),
            "matched_difference": _money(declared_matched - documentary_total),
            "uncovered_pgdas_revenue": _money(uncovered_total),
        },
        "status_counts": dict(
            sorted(
                {
                    value: sum(record["status"] == value for record in records)
                    for value in {record["status"] for record in records}
                }.items()
            )
        ),
        "source_lock": source_lock,
        "warnings": warnings,
        "gates": {
            "simple_reconciliation_execution_ready": True,
            "documentary_scope_reconciled": documentary_scope_reconciled,
            "group_coverage_complete": group_coverage_complete,
            "analyst_review_required": analyst_review_required,
            "non_issuance_confirmed": False,
            "uc004_planning_authorized": False,
        },
        "limitations": [
            "A consolidação usa somente as pastas de estabelecimentos explicitamente descobertas na raiz indicada.",
            "Ausência de documento na base fornecida não comprova não emissão.",
            "A conciliação usa a receita declarada no PGDAS-D e não conclui tratamento de IBS/CBS.",
            "No regime CAIXA, a comparação documental exige análise temporal específica; o aviso não bloqueia a conciliação.",
        ],
        "_private_records": records,
    }


def _report(result: dict[str, Any]) -> str:
    totals = result["totals"]
    gates = result["gates"]
    is_group = result.get("scope", {}).get("mode") == "GROUP"
    lines = [
        "# Relatório de Conciliação do Simples Nacional",
        "",
        f"- Conciliação: `{result['reconciliation_id']}`",
        f"- Situação: `{result['status']}`",
        f"- Competência: `{result['scope']['period']}`",
        f"- Regime de apuração: `{result['scope']['revenue_regime']}`",
        (
            f"- Estabelecimentos documentais: {result['scope']['documentary_establishments']}"
            if is_group
            else f"- Estabelecimento documental: `{result['scope']['documentary_establishment_ref']}`"
        ),
        "",
        "## Totais",
        "",
        f"- Receita declarada do grupo: R$ {totals['pgdas_group_declared']}",
        (
            f"- Receita declarada dos estabelecimentos cobertos: R$ {totals['pgdas_matched_establishment']}"
            if is_group
            else f"- Receita declarada do estabelecimento conciliado: R$ {totals['pgdas_matched_establishment']}"
        ),
        (
            f"- Receita documental dos estabelecimentos: R$ {totals['documentary_matched_establishment']}"
            if is_group
            else f"- Receita documental do estabelecimento: R$ {totals['documentary_matched_establishment']}"
        ),
        (
            f"- Diferença nos estabelecimentos cobertos: R$ {totals['matched_difference']}"
            if is_group
            else f"- Diferença no estabelecimento conciliado: R$ {totals['matched_difference']}"
        ),
        f"- Receita PGDAS-D declarada por estabelecimento fora do escopo documental analisado: R$ {totals['uncovered_pgdas_revenue']}",
        "",
        "## Cobertura",
        "",
        f"- Escopo documental conciliado: `{str(gates['documentary_scope_reconciled']).lower()}`",
        f"- Cobertura integral do grupo: `{str(gates['group_coverage_complete']).lower()}`",
        f"- Revisão do analista necessária: `{str(gates['analyst_review_required']).lower()}`",
        "",
        "## Ocorrências",
        "",
    ]
    if result["scope"]["revenue_regime"] == "CAIXA":
        lines.extend(
            [
                "> **Aviso:** o regime CAIXA exige análise temporal específica; este aviso não bloqueia a conciliação.",
                "",
            ]
        )
    if result["warnings"]:
        lines.extend(
            f"- `{warning['code']}` - `{warning['ref']}`"
            for warning in result["warnings"]
        )
    else:
        lines.append("- Nenhuma divergência identificada.")
    lines.extend(["", "## Limitações", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def _queue(records: list[dict[str, Any]]) -> str:
    columns = [
        "establishment_ref",
        "activity",
        "declared_amount",
        "documentary_amount",
        "difference",
        "automatic_status",
        "classification",
        "status",
        "aprovado_por",
        "evidence_ref",
        "observacao",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter=";", lineterminator="\n"
    )
    writer.writeheader()
    for record in records:
        if record["status"] in RECONCILED_STATUSES:
            continue
        writer.writerow(
            {
                "establishment_ref": record["establishment_ref"],
                "activity": record["activity"],
                "declared_amount": record["declared_amount"],
                "documentary_amount": record["documentary_amount"] or "",
                "difference": record["difference"],
                "automatic_status": record["status"],
                "classification": "",
                "status": "PENDENTE",
                "aprovado_por": "",
                "evidence_ref": "",
                "observacao": "",
            }
        )
    return stream.getvalue()


def write_simple_reconciliation_outputs(
    result: dict[str, Any], output_dir: Path | str
) -> tuple[Path, Path, Path, Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    summary_path = target / "simple-reconciliation-summary.json"
    records_path = target / "simple-reconciliation-items.local.jsonl"
    queue_path = target / "fila-conciliacao-simples.csv"
    lock_path = target / "pgdas-lock.json"
    report_path = target / "relatorio-conciliacao-simples.md"
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
        json.dumps(result["source_lock"], ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_report(result), encoding="utf-8")
    return summary_path, records_path, queue_path, lock_path, report_path
