from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.cli import main
from fiscal_document_intake.planning_status import (
    evaluate_planning_status,
    write_planning_status_outputs,
)

PLUGIN_ROOT = Path(__file__).parents[2]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_validation(folder: Path, *, ready: bool = True) -> None:
    write_json(
        folder / "03_SAIDAS" / "validation-result.json",
        {
            "use_case": "UC-001",
            "validation_id": "VAL-SYNTHETIC",
            "blockers": [] if ready else [{"code": "MISSING_XML"}],
            "gates": {
                "planning_authorized": ready,
                "authorized_scopes": ["NFE_NFCE"] if ready else [],
            },
        },
    )


def write_content(folder: Path, *, ready: bool = True) -> None:
    write_json(
        folder / "04_CONTEUDO" / "content-summary.json",
        {
            "use_case": "UC-002",
            "content_analysis_id": "CNT-SYNTHETIC",
            "gates": {"uc003_analysis_authorized": ready},
        },
    )


def write_acquisition(folder: Path, *, analyst_review: bool = True) -> None:
    write_json(
        folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json",
        {
            "use_case": "UC-003",
            "phase": "ACQUISITION_REVIEW",
            "review_id": "ACQ-SYNTHETIC",
            "gates": {
                "uc003_execution_ready": True,
                "analyst_review_required": analyst_review,
            },
        },
    )


def write_revenue(folder: Path, *, ready: bool = True) -> None:
    write_json(
        folder / "06_REVISAO_RECEITAS" / "revenue-summary.json",
        {
            "use_case": "UC-003",
            "phase": "REVENUE_REVIEW",
            "review_id": "REV-SYNTHETIC",
            "gates": {"revenue_population_ready": ready},
        },
    )


def write_reconciliation(folder: Path, *, group_complete: bool = False) -> None:
    write_json(
        folder / "07_CONCILIACAO_SIMPLES" / "simple-reconciliation-summary.json",
        {
            "use_case": "UC-003C",
            "reconciliation_id": "SNR-SYNTHETIC",
            "revenue_review_id": "REV-SYNTHETIC",
            "coverage": {
                "missing_establishment_refs": (
                    [] if group_complete else ["ESTAB-SYNTHETIC"]
                )
            },
            "gates": {
                "documentary_scope_reconciled": True,
                "group_coverage_complete": group_complete,
            },
        },
    )


def test_status_starts_with_document_validation(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    folder.mkdir()

    result = evaluate_planning_status(folder)

    assert result["status"] == "READY_TO_CONTINUE"
    assert result["current_stage"] == "DOCUMENT_VALIDATION"
    assert [item["action"] for item in result["available_actions"]] == [
        "RUN_DOCUMENT_VALIDATION"
    ]
    assert result["required_inputs"] == []


def test_status_routes_from_validation_to_content(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    write_validation(folder)

    result = evaluate_planning_status(folder)

    assert result["completed_stages"] == ["DOCUMENT_VALIDATION"]
    assert result["current_stage"] == "CONTENT_EXTRACTION"
    assert result["available_actions"][0]["action"] == "RUN_CONTENT_EXTRACTION"


def test_status_opens_acquisition_and_revenue_reviews(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    write_validation(folder)
    write_content(folder)

    result = evaluate_planning_status(folder)

    assert result["current_stage"] == "OPERATION_REVIEWS"
    assert {item["action"] for item in result["available_actions"]} == {
        "RUN_ACQUISITION_REVIEW",
        "RUN_REVENUE_REVIEW",
    }
    assert all(item["automatic"] for item in result["available_actions"])


def test_status_requests_pgdas_without_blocking_acquisitions(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    write_validation(folder)
    write_content(folder)
    write_acquisition(folder, analyst_review=True)
    write_revenue(folder)

    result = evaluate_planning_status(folder)

    assert result["status"] == "NEEDS_USER_INPUT"
    assert result["current_stage"] == "SIMPLE_REVENUE_RECONCILIATION"
    assert {item["input_id"] for item in result["required_inputs"]} == {
        "APPROVE_ACQUISITION_CLASSIFICATIONS",
        "PROVIDE_PGDAS_FOLDER",
    }
    assert "PGDAS-D" in result["summary"]["next_step"]


def test_status_explains_partial_group_in_user_language(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    write_validation(folder)
    write_content(folder)
    write_acquisition(folder, analyst_review=True)
    write_revenue(folder)
    write_reconciliation(folder, group_complete=False)

    result = evaluate_planning_status(folder)

    assert result["status"] == "NEEDS_USER_INPUT"
    assert result["can_continue_partially"] is True
    assert {item["input_id"] for item in result["required_inputs"]} == {
        "APPROVE_ACQUISITION_CLASSIFICATIONS",
        "PROVIDE_MISSING_ESTABLISHMENT_DOCUMENTS",
    }
    assert (
        "estabelecimento analisado conciliou" in result["summary"]["situation"].lower()
    )

    written = write_planning_status_outputs(result, folder / "08_STATUS_PLANEJAMENTO")
    report = written[1].read_text(encoding="utf-8")
    for heading in (
        "## Situação atual",
        "## O que foi concluído",
        "## O que foi encontrado",
        "## Preciso de você",
        "## Por que é necessário",
        "## O que pode continuar",
        "## Próximo passo",
    ):
        assert heading in report
    assert "group_coverage_complete" not in report
    assert "ACQUISITION_PLANNING" not in report
    assert "CONSOLIDATED_GROUP" not in report


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_planning_status_launcher_prepares_runtime_then_runs_without_uv(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "company"
    folder.mkdir()
    runtime = tmp_path / "runtime"
    launcher = (
        PLUGIN_ROOT
        / "skills"
        / "planejar-reforma-tributaria"
        / "scripts"
        / "run-planning-status.ps1"
    )
    environment = os.environ.copy()
    environment["FISCAL_INTAKE_ENVIRONMENT"] = str(runtime)
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(launcher),
        "-Folder",
        str(folder),
    ]

    first = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    assert first.returncode == 0, first.stderr
    assert (folder / "08_STATUS_PLANEJAMENTO" / "planning-status.json").is_file()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "uv.cmd").write_text("@exit /b 99\n", encoding="ascii")
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
    second = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    assert second.returncode == 0, second.stderr


def test_planning_status_cli_writes_user_facing_outputs(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    folder.mkdir()

    assert main(["planning-status", str(folder)]) == 0
    result = json.loads(
        (folder / "08_STATUS_PLANEJAMENTO" / "planning-status.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["available_actions"][0]["action"] == "RUN_DOCUMENT_VALIDATION"
