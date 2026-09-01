from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.portfolio_batch import (
    discover_periods,
    process_portfolio_periods,
)
from test_uc001 import COMPANY, OTHER, access_key, make_folder, nfe_xml

PLUGIN_ROOT = Path(__file__).parents[2]
ACQUISITION_RULESET = (
    PLUGIN_ROOT
    / "skills"
    / "revisar-aquisicoes"
    / "references"
    / "snapshots"
    / "cclass-trib-2026-06-22.json"
)
CFOP_RULESET = (
    PLUGIN_ROOT
    / "skills"
    / "revisar-receitas"
    / "references"
    / "snapshots"
    / "cfop-2026-08-25.json"
)
ANALYST_RULES = (
    PLUGIN_ROOT
    / "skills"
    / "revisar-receitas"
    / "references"
    / "rules"
    / "revenue-cfop-rules-v1.json"
)


def make_period(root: Path, establishment: str, month: int, number: int) -> Path:
    folder = make_folder(
        root / establishment,
        f"{month:02d}-2026",
        document_families=["NFE"],
    )
    scope_path = folder / "00_CONTROLE" / "escopo.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope["period"] = f"2026-{month:02d}"
    scope["analysis_cutoff"] = f"2026-{month:02d}-28T23:59:59-03:00"
    scope_path.write_text(json.dumps(scope, indent=2), encoding="utf-8")
    key = access_key(COMPANY, "55", number)
    (folder / "01_XML" / "sale.xml").write_text(
        nfe_xml(
            key,
            "55",
            COMPANY,
            OTHER,
            f"2026-{month:02d}-05",
            "100.00",
        ),
        encoding="utf-8",
    )
    return folder


def run_batch(root: Path, **overrides: object) -> dict[str, object]:
    arguments = {
        "acquisition_ruleset": ACQUISITION_RULESET,
        "cfop_ruleset": CFOP_RULESET,
        "analyst_rules": ANALYST_RULES,
        "workers": 2,
        **overrides,
    }
    return process_portfolio_periods(root, **arguments)


def test_batch_discovers_and_processes_multiple_periods_incrementally(
    tmp_path: Path,
) -> None:
    root = tmp_path / "portfolio"
    first = make_period(root, "MATRIZ", 3, 301)
    make_period(root, "MATRIZ", 4, 401)

    plan = run_batch(root, dry_run=True)
    initial = run_batch(root)
    repeated = run_batch(root)

    assert plan["status"] == "DRY_RUN"
    assert plan["periods_found"] == 2
    assert initial["status"] == "COMPLETED"
    assert initial["processed"] == 2
    assert initial["skipped"] == 0
    assert initial["failed"] == 0
    assert repeated["processed"] == 0
    assert repeated["skipped"] == 2
    assert (first / "08_STATUS_PLANEJAMENTO" / "planning-status.json").is_file()
    assert (root / ".reforma-tributaria" / "processamento-lote-manifest.json").is_file()


def test_batch_reprocesses_only_changed_period(tmp_path: Path) -> None:
    root = tmp_path / "portfolio"
    first = make_period(root, "MATRIZ", 3, 302)
    make_period(root, "MATRIZ", 4, 402)
    run_batch(root)
    xml = first / "01_XML" / "sale.xml"
    current = xml.stat().st_mtime_ns
    os.utime(xml, ns=(current + 1_000_000_000, current + 1_000_000_000))

    result = run_batch(root)

    assert result["processed"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0


def test_batch_isolates_period_failure(tmp_path: Path) -> None:
    root = tmp_path / "portfolio"
    make_period(root, "MATRIZ", 3, 303)
    invalid = make_period(root, "MATRIZ", 4, 403)
    (invalid / "01_XML" / "sale.xml").write_text("<invalid>", encoding="utf-8")

    result = run_batch(root)

    assert result["status"] == "COMPLETED_WITH_FAILURES"
    assert result["processed"] == 1
    assert result["failed"] == 1
    statuses = {item["period"]: item["status"] for item in result["periods"]}
    assert statuses == {"2026-03": "PROCESSED", "2026-04": "FAILED"}


def test_batch_discovery_ignores_pgdas_only_periods(tmp_path: Path) -> None:
    root = tmp_path / "portfolio"
    make_period(root, "MATRIZ", 3, 304)
    pgdas = root / "SN" / "03-2026"
    pgdas.mkdir(parents=True)
    (pgdas / "declaracao.pdf").write_bytes(b"synthetic")

    periods = discover_periods(root)

    assert len(periods) == 1
    assert periods[0]["period"] == "2026-03"
    assert periods[0]["pgdas_folder"] == pgdas


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_batch_launcher_plans_without_writing_client_outputs(tmp_path: Path) -> None:
    root = tmp_path / "portfolio"
    make_period(root, "MATRIZ", 3, 305)
    runtime = tmp_path / "runtime"
    launcher = (
        PLUGIN_ROOT
        / "skills"
        / "processar-periodos-carteira"
        / "scripts"
        / "run-portfolio-batch.ps1"
    )
    environment = os.environ.copy()
    environment["FISCAL_INTAKE_ENVIRONMENT"] = str(runtime)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            "-Action",
            "Plan",
            "-PortfolioFolder",
            str(root),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    response = json.loads(completed.stdout.splitlines()[-1])
    assert response["status"] == "DRY_RUN"
    assert response["periods_found"] == 1
    assert not (root / ".reforma-tributaria").exists()
