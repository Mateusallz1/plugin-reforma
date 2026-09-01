from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from .acquisition import (
    ACQUISITION_SCHEMA_VERSION,
    review_acquisitions_folder,
    write_acquisition_outputs,
)
from .content import (
    CONTENT_SCHEMA_VERSION,
    extract_content_folder,
    write_content_outputs,
)
from .core import (
    DOCUMENT_SCHEMA_VERSION,
    ValidationError,
    _parse_xml_file,
    validate_folder,
    write_outputs,
)
from .planning_status import (
    PLANNING_STATUS_SCHEMA_VERSION,
    evaluate_planning_status,
    write_planning_status_outputs,
)
from .portfolio_review import review_portfolio
from .revenue import (
    REVENUE_SCHEMA_VERSION,
    review_revenue_folder,
    write_revenue_outputs,
)
from .simple_reconciliation import (
    reconcile_simple_revenue,
    write_simple_reconciliation_outputs,
)

BATCH_SCHEMA_VERSION = "1.2.0"
STATE_FOLDER = ".reforma-tributaria"
MANIFEST_FILE = "processamento-lote-manifest.json"
CONFIG_FILE = "configuracao-lote.local.json"
STATUS_FILE = "processamento-lote-status.json"
REPORT_FILE = "relatorio-processamento-lote.md"
OUTPUT_DIRECTORIES = {
    "03_SAIDAS",
    "04_CONTEUDO",
    "05_REVISAO_AQUISICOES",
    "06_REVISAO_RECEITAS",
    "07_CONCILIACAO_SIMPLES",
    "08_STATUS_PLANEJAMENTO",
    STATE_FOLDER,
}
SOURCE_SUFFIXES = {".xml", ".pdf", ".csv", ".xlsx", ".json"}


def _period_from_name(name: str) -> str | None:
    match = re.fullmatch(r"(0[1-9]|1[0-2])-(20\d{2})", name)
    if match:
        return f"{match.group(2)}-{match.group(1)}"
    match = re.fullmatch(r"(20\d{2})-(0[1-9]|1[0-2])", name)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _period_ref(root: Path, folder: Path, period: str) -> str:
    relative = folder.relative_to(root).as_posix().casefold()
    digest = hashlib.sha256(f"{relative}:{period}".encode()).hexdigest()[:16]
    return f"PER-{digest.upper()}"


def _source_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for path in folder.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(folder)
        if any(part in OUTPUT_DIRECTORIES for part in relative.parts[:-1]):
            continue
        if path.suffix.casefold() in SOURCE_SUFFIXES:
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix().casefold())


def discover_periods(portfolio_root: Path | str) -> list[dict[str, Any]]:
    root = Path(portfolio_root).expanduser().resolve()
    if not root.is_dir():
        raise ValidationError("A pasta da carteira informada não existe")
    periods: list[dict[str, Any]] = []
    for folder in root.rglob("*"):
        if not folder.is_dir() or folder.is_symlink():
            continue
        period = _period_from_name(folder.name)
        if period is None:
            continue
        xml_files = [
            path for path in _source_files(folder) if path.suffix.casefold() == ".xml"
        ]
        if not xml_files:
            continue
        establishment = folder.parent
        pgdas_candidates = [
            root / "SN" / folder.name,
            root / "SN" / period,
        ]
        pgdas = next((path for path in pgdas_candidates if path.is_dir()), None)
        periods.append(
            {
                "period_ref": _period_ref(root, folder, period),
                "period": period,
                "folder": folder,
                "establishment_path": establishment,
                "establishment_key": establishment.relative_to(root)
                .as_posix()
                .casefold(),
                "pgdas_folder": pgdas,
                "xml_count": len(xml_files),
            }
        )
    return sorted(periods, key=lambda item: (item["establishment_key"], item["period"]))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"Arquivo local inválido: {path.name}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"Arquivo local deve conter objeto JSON: {path.name}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(folder: Path | None) -> list[dict[str, Any]]:
    if folder is None:
        return []
    return [
        {
            "path": path.relative_to(folder).as_posix(),
            "size": path.stat().st_size,
            "modified_ns": path.stat().st_mtime_ns,
            "sha256": _sha256(path),
        }
        for path in _source_files(folder)
    ]


def _fingerprint(
    item: dict[str, Any],
    identity: dict[str, Any] | None,
    rule_hashes: dict[str, str],
) -> str:
    material = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "period": item["period"],
        "files": _inventory(item["folder"]),
        "pgdas_files": _inventory(item["pgdas_folder"]),
        "identity": identity,
        "rules": rule_hashes,
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _document_families(xml_files: list[Path]) -> list[str]:
    families: set[str] = set()
    for path in xml_files:
        documents, event, error = _parse_xml_file(path)
        families.update(
            document["document_type"]
            for document in documents
            if document.get("document_type") in {"NFE", "NFCE", "NFSE", "CTE"}
        )
        if event is not None:
            families.add("NFE")
        if error is not None:
            scope = error.get("analysis_scope")
            if scope == "NFE_NFCE":
                families.add("NFE")
            elif scope in {"NFSE", "CTE"}:
                families.add(scope)
    if not families:
        raise ValidationError(
            "Nenhuma família fiscal reconhecida na competência do lote"
        )
    return sorted(families)


def _scope_from_identity(
    item: dict[str, Any], identity: dict[str, Any]
) -> dict[str, Any]:
    xml_files = [
        path
        for path in _source_files(item["folder"])
        if path.suffix.casefold() == ".xml"
    ]
    cutoff = max(path.stat().st_mtime for path in xml_files)
    return {
        "schema_version": "1.0",
        "entity_ref": identity["entity_ref"],
        "establishment_ref": identity["establishment_ref"],
        "entity_taxpayer_ids": identity["entity_taxpayer_ids"],
        "period": item["period"],
        "objective": "VALIDATE_DOCUMENT_BASE",
        "document_families": _document_families(xml_files),
        "validation_policy": "DOCUMENTARY_INITIAL",
        "report_population_policy": "COMPLEMENTARY",
        "analysis_cutoff": datetime.fromtimestamp(cutoff)
        .astimezone()
        .isoformat(timespec="seconds"),
    }


def _identity_from_scope(scope: dict[str, Any]) -> dict[str, Any] | None:
    required = {"entity_ref", "establishment_ref", "entity_taxpayer_ids"}
    if not required <= set(scope):
        return None
    taxpayers = scope.get("entity_taxpayer_ids")
    if not isinstance(taxpayers, list) or not taxpayers:
        return None
    return {
        "entity_ref": scope["entity_ref"],
        "establishment_ref": scope["establishment_ref"],
        "entity_taxpayer_ids": taxpayers,
    }


def _known_identity(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        validation = _load_json(item["folder"] / "03_SAIDAS" / "validation-result.json")
        identity = _identity_from_scope(validation.get("scope", {}))
        if identity:
            return identity
        scope = _load_json(item["folder"] / "00_CONTROLE" / "escopo.json")
        identity = _identity_from_scope(scope)
        if identity:
            return identity
    return None


def _bootstrap_identity(
    items: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    known = _known_identity(items)
    if known:
        return known, {}
    validations: dict[str, dict[str, Any]] = {}
    for item in items:
        try:
            result = validate_folder(item["folder"])
        except ValidationError:
            continue
        identity = _identity_from_scope(result.get("_private_scope_identity", {}))
        if identity:
            validations[item["period_ref"]] = result
            return identity, validations
    return None, {}


def _outputs_coherent(folder: Path) -> bool:
    try:
        validation = _load_json(folder / "03_SAIDAS" / "validation-result.json")
        content = _load_json(folder / "04_CONTEUDO" / "content-summary.json")
        acquisition = _load_json(
            folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json"
        )
        revenue = _load_json(folder / "06_REVISAO_RECEITAS" / "revenue-summary.json")
        planning = _load_json(
            folder / "08_STATUS_PLANEJAMENTO" / "planning-status.json"
        )
    except ValidationError:
        return False
    if not all((validation, content, acquisition, revenue, planning)):
        return False
    if (
        validation.get("use_case") != "UC-001"
        or validation.get("schema_version") != DOCUMENT_SCHEMA_VERSION
        or not validation.get("validation_id")
    ):
        return False
    if (
        content.get("use_case") != "UC-002"
        or content.get("schema_version") != CONTENT_SCHEMA_VERSION
        or content.get("validation_id") != validation.get("validation_id")
        or not content.get("content_analysis_id")
    ):
        return False
    if (
        acquisition.get("use_case") != "UC-003"
        or acquisition.get("schema_version") != ACQUISITION_SCHEMA_VERSION
        or acquisition.get("phase") != "ACQUISITION_REVIEW"
        or acquisition.get("content_analysis_id") != content.get("content_analysis_id")
        or not acquisition.get("review_id")
    ):
        return False
    if (
        revenue.get("use_case") != "UC-003"
        or revenue.get("schema_version") != REVENUE_SCHEMA_VERSION
        or revenue.get("phase") != "REVENUE_REVIEW"
        or revenue.get("validation_id") != validation.get("validation_id")
        or revenue.get("content_analysis_id") != content.get("content_analysis_id")
        or not revenue.get("review_id")
    ):
        return False
    return (
        planning.get("use_case") == "PLANNING_COORDINATION"
        and planning.get("schema_version") == PLANNING_STATUS_SCHEMA_VERSION
        and bool(planning.get("state_id"))
        and {
            "DOCUMENT_VALIDATION",
            "CONTENT_EXTRACTION",
            "ACQUISITION_REVIEW",
            "REVENUE_REVIEW",
        }.issubset(set(planning.get("completed_stages", [])))
    )


def _process_period(
    item: dict[str, Any],
    identity: dict[str, Any],
    acquisition_ruleset: Path,
    cfop_ruleset: Path,
    analyst_rules: Path,
    prevalidated: dict[str, Any] | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    folder = item["folder"]
    try:
        validation = prevalidated or validate_folder(
            folder, scope_override=_scope_from_identity(item, identity)
        )
        write_outputs(validation, folder / "03_SAIDAS")
        if not validation["gates"]["planning_authorized"]:
            raise ValidationError("A validação documental não autorizou o planejamento")

        content = extract_content_folder(folder)
        write_content_outputs(content, folder / "04_CONTEUDO")
        if not content["gates"]["uc003_analysis_authorized"]:
            raise ValidationError("A extração não autorizou as revisões operacionais")

        acquisition = review_acquisitions_folder(folder, acquisition_ruleset)
        write_acquisition_outputs(acquisition, folder / "05_REVISAO_AQUISICOES")
        revenue = review_revenue_folder(folder, cfop_ruleset, analyst_rules)
        write_revenue_outputs(revenue, folder / "06_REVISAO_RECEITAS")

        if (
            item["pgdas_folder"] is not None
            and revenue["gates"]["revenue_population_ready"]
        ):
            reconciliation = reconcile_simple_revenue(folder, item["pgdas_folder"])
            write_simple_reconciliation_outputs(
                reconciliation, folder / "07_CONCILIACAO_SIMPLES"
            )

        status = evaluate_planning_status(folder, item["pgdas_folder"])
        write_planning_status_outputs(status, folder / "08_STATUS_PLANEJAMENTO")
        return {
            "period_ref": item["period_ref"],
            "period": item["period"],
            "establishment_ref": identity["establishment_ref"],
            "status": "PROCESSED",
            "planning_status": status["status"],
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": None,
        }
    except (OSError, ValidationError) as error:
        return {
            "period_ref": item["period_ref"],
            "period": item["period"],
            "establishment_ref": identity["establishment_ref"],
            "status": "FAILED",
            "planning_status": None,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": str(error),
        }


def _local_report(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# Processamento em lote da carteira",
        "",
        f"- Competências encontradas: {result['periods_found']}",
        f"- Processadas: {result['processed']}",
        f"- Reaproveitadas: {result['skipped']}",
        f"- Falhas: {result['failed']}",
        f"- Tempo total: {result['elapsed_seconds']:.3f} s",
        "",
        "| Estabelecimento | Competência | Situação | Tempo | Motivo |",
        "|---|---|---|---:|---|",
    ]
    for item in result["periods"]:
        lines.append(
            "| {establishment_ref} | {period} | {status} | {elapsed_seconds:.3f} s | {error} |".format(
                **{**item, "error": item.get("error") or ""}
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_portfolio_periods(
    portfolio_root: Path | str,
    *,
    acquisition_ruleset: Path | str,
    cfop_ruleset: Path | str,
    analyst_rules: Path | str,
    workers: int = 2,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    if not 1 <= workers <= 4:
        raise ValidationError("O lote aceita de 1 a 4 trabalhadores")
    root = Path(portfolio_root).expanduser().resolve()
    periods = discover_periods(root)
    if not periods:
        raise ValidationError("Nenhuma competência fiscal com XML foi encontrada")
    rules = {
        "acquisition": Path(acquisition_ruleset).expanduser().resolve(),
        "cfop": Path(cfop_ruleset).expanduser().resolve(),
        "analyst": Path(analyst_rules).expanduser().resolve(),
    }
    if any(not path.is_file() for path in rules.values()):
        raise ValidationError("Um dos arquivos de regras do lote não foi encontrado")
    rule_hashes = {name: _sha256(path) for name, path in rules.items()}
    state = root / STATE_FOLDER
    manifest_path = state / MANIFEST_FILE
    config_path = state / CONFIG_FILE
    status_path = state / STATUS_FILE
    report_path = state / REPORT_FILE
    manifest = _load_json(manifest_path)
    manifest_periods = manifest.get("periods", {})
    if not isinstance(manifest_periods, dict):
        manifest_periods = {}
    config = _load_json(config_path)
    configured = config.get("establishments", {})
    if not isinstance(configured, dict):
        configured = {}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in periods:
        grouped.setdefault(item["establishment_key"], []).append(item)
    identities: dict[str, dict[str, Any]] = {}
    prevalidated: dict[str, dict[str, Any]] = {}
    unresolved: set[str] = set()
    if dry_run:
        for key, identity in configured.items():
            if isinstance(identity, dict) and _identity_from_scope(identity):
                identities[key] = identity
    if not dry_run:
        state.mkdir(parents=True, exist_ok=True)
        for key, items in grouped.items():
            identity = configured.get(key)
            if not isinstance(identity, dict) or _identity_from_scope(identity) is None:
                identity, bootstrap = _bootstrap_identity(items)
                prevalidated.update(bootstrap)
            if identity is None:
                unresolved.add(key)
                continue
            identities[key] = identity
            configured[key] = identity
        _write_json(
            config_path,
            {
                "schema_version": BATCH_SCHEMA_VERSION,
                "establishments": configured,
            },
        )

    pending: list[tuple[dict[str, Any], str]] = []
    skipped_results: list[dict[str, Any]] = []
    for item in periods:
        identity = identities.get(item["establishment_key"])
        fingerprint = _fingerprint(item, identity, rule_hashes)
        previous = manifest_periods.get(item["period_ref"], {})
        unchanged = (
            not force
            and identity is not None
            and previous.get("fingerprint") == fingerprint
            and _outputs_coherent(item["folder"])
        )
        if unchanged:
            skipped_results.append(
                {
                    "period_ref": item["period_ref"],
                    "period": item["period"],
                    "establishment_ref": identity["establishment_ref"],
                    "status": "SKIPPED_UNCHANGED",
                    "planning_status": previous.get("planning_status"),
                    "elapsed_seconds": 0.0,
                    "error": None,
                }
            )
        else:
            pending.append((item, fingerprint))

    if dry_run:
        return {
            "status": "DRY_RUN",
            "periods_found": len(periods),
            "pending": len(pending),
            "skipped": len(skipped_results),
            "workers": workers,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }

    results = list(skipped_results)
    runnable = [
        (item, fingerprint)
        for item, fingerprint in pending
        if item["establishment_key"] not in unresolved
    ]
    for item, _ in pending:
        if item["establishment_key"] in unresolved:
            results.append(
                {
                    "period_ref": item["period_ref"],
                    "period": item["period"],
                    "establishment_ref": "ESTAB-NAO-IDENTIFICADO",
                    "status": "FAILED",
                    "planning_status": None,
                    "elapsed_seconds": 0.0,
                    "error": "Não foi possível identificar o estabelecimento para o lote",
                }
            )

    fingerprints = {item["period_ref"]: value for item, value in runnable}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _process_period,
                item,
                identities[item["establishment_key"]],
                rules["acquisition"],
                rules["cfop"],
                rules["analyst"],
                prevalidated.get(item["period_ref"]),
            ): item
            for item, _ in runnable
        }
        for future in as_completed(futures):
            results.append(future.result())

    for item in results:
        if item["status"] == "FAILED":
            continue
        if item["status"] == "PROCESSED":
            manifest_periods[item["period_ref"]] = {
                "fingerprint": fingerprints[item["period_ref"]],
                "planning_status": item["planning_status"],
                "processed_at": datetime.now()
                .astimezone()
                .isoformat(timespec="seconds"),
            }
    _write_json(
        manifest_path,
        {
            "schema_version": BATCH_SCHEMA_VERSION,
            "rule_hashes": rule_hashes,
            "periods": manifest_periods,
        },
    )

    portfolio = review_portfolio(root, ruleset_path=rules["acquisition"])
    results.sort(key=lambda item: (item["establishment_ref"], item["period"]))
    processed = sum(item["status"] == "PROCESSED" for item in results)
    skipped = sum(item["status"] == "SKIPPED_UNCHANGED" for item in results)
    failed = sum(item["status"] == "FAILED" for item in results)
    public_periods = [
        {
            key: item[key]
            for key in (
                "period_ref",
                "period",
                "establishment_ref",
                "status",
                "planning_status",
                "elapsed_seconds",
                "error",
            )
        }
        for item in results
    ]
    result = {
        "status": "COMPLETED" if not failed else "COMPLETED_WITH_FAILURES",
        "periods_found": len(periods),
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "workers": workers,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "portfolio_review_groups": portfolio["group_count"],
        "periods": public_periods,
        "local_report": f"{STATE_FOLDER}/{REPORT_FILE}",
    }
    _write_json(status_path, result)
    _local_report(result, report_path)
    return result
