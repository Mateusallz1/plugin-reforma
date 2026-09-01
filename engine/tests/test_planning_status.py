from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.acquisition import ACQUISITION_SCHEMA_VERSION
from fiscal_document_intake.cli import main
from fiscal_document_intake.content import CONTENT_SCHEMA_VERSION
from fiscal_document_intake.core import DOCUMENT_SCHEMA_VERSION
from fiscal_document_intake.planning_status import (
    evaluate_planning_status,
    write_planning_status_outputs,
)
from fiscal_document_intake.revenue import REVENUE_SCHEMA_VERSION
from fiscal_document_intake.simple_reconciliation import (
    SIMPLE_RECONCILIATION_SCHEMA_VERSION,
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
            "schema_version": DOCUMENT_SCHEMA_VERSION,
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
            "schema_version": CONTENT_SCHEMA_VERSION,
            "content_analysis_id": "CNT-SYNTHETIC",
            "gates": {"uc003_analysis_authorized": ready},
        },
    )


def write_acquisition(folder: Path, *, analyst_review: bool = True) -> None:
    write_json(
        folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json",
        {
            "use_case": "UC-003",
            "schema_version": ACQUISITION_SCHEMA_VERSION,
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
            "schema_version": REVENUE_SCHEMA_VERSION,
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
            "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
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


def test_status_exposes_preliminary_documentary_summary(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    write_json(
        folder / "03_SAIDAS" / "validation-result.json",
        {
            "use_case": "UC-001",
            "schema_version": DOCUMENT_SCHEMA_VERSION,
            "status": "DOCUMENT_BASE_READY",
            "validation_id": "VAL-SYNTHETIC",
            "documents": {
                "xml_files_found": 4,
                "fiscal_documents_found": 4,
                "included": 3,
                "excluded": 1,
                "reported": 4,
                "document_type_counts": {"NFE": 2, "NFSE": 1},
                "direction_counts": {"ENTRADA": 1, "SAIDA": 2},
                "direction_gross_amounts": {
                    "ENTRADA": "125.00",
                    "SAIDA": "875.00",
                },
                "analysis_groups": {
                    "NFE_ENTRADAS": {
                        "label": "NF-e de entrada",
                        "direction": "ENTRADA",
                        "document_status": "COM_DOCUMENTO",
                        "detected_count": 1,
                        "count": 1,
                        "gross_amount": "125.00",
                    },
                    "NFE_SAIDAS": {
                        "label": "NF-e de saída",
                        "direction": "SAIDA",
                        "document_status": "COM_DOCUMENTO",
                        "detected_count": 2,
                        "count": 2,
                        "gross_amount": "875.00",
                    },
                },
            },
            "pdf_evidence": {"pdf_files_found": 2},
            "gates": {
                "planning_authorized": True,
                "authorized_scopes": ["NFE_NFCE"],
            },
        },
    )
    write_json(
        folder / "04_CONTEUDO" / "content-summary.json",
        {
            "use_case": "UC-002",
            "schema_version": CONTENT_SCHEMA_VERSION,
            "content_analysis_id": "CNT-SYNTHETIC",
            "records_total": 5,
            "record_kind_counts": {"PRODUCT": 3, "SERVICE": 2},
            "component_count": 7,
            "uc003_eligibility": {"eligible_records": 5, "restricted_records": 0},
            "gates": {"uc003_analysis_authorized": True},
        },
    )
    write_json(
        folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json",
        {
            "use_case": "UC-003",
            "schema_version": ACQUISITION_SCHEMA_VERSION,
            "phase": "ACQUISITION_REVIEW",
            "review_id": "ACQ-SYNTHETIC",
            "acquisition_records": 2,
            "category_counts": {"MERCADORIA": 1, "SERVICO": 1},
            "category_amounts": {"MERCADORIA": "100.00", "SERVICO": "25.00"},
            "gates": {
                "uc003_execution_ready": True,
                "analyst_review_required": True,
            },
        },
    )
    write_json(
        folder / "06_REVISAO_RECEITAS" / "revenue-summary.json",
        {
            "use_case": "UC-003",
            "schema_version": REVENUE_SCHEMA_VERSION,
            "phase": "REVENUE_REVIEW",
            "review_id": "REV-SYNTHETIC",
            "reviewed_documents": 2,
            "totals": {
                "gross_revenue_goods": "500.00",
                "gross_revenue_services": "375.00",
                "gross_revenue_transport": "0.00",
                "gross_operational_revenue": "875.00",
                "sales_returns_inbound": "0.00",
                "excluded_non_revenue_operations": "0.00",
                "pending_revenue_treatment": "0.00",
                "unallocated_document_components": "0.00",
            },
            "gates": {
                "revenue_population_ready": True,
                "cfop_classification_complete": True,
            },
        },
    )

    result = evaluate_planning_status(folder)
    documentary = result["documentary_summary"]

    assert documentary["status"] == "APURADO"
    assert documentary["flows"]["ENTRADA"] == {
        "document_count": 1,
        "gross_amount": "125.00",
    }
    assert documentary["flows"]["SAIDA"]["gross_amount"] == "875.00"
    assert documentary["content"]["record_kind_counts"] == {
        "PRODUCT": 3,
        "SERVICE": 2,
    }
    assert documentary["acquisitions"]["nature_status"] == "PENDENTE_ANALISTA"
    assert documentary["revenue"]["totals"]["gross_operational_revenue"] == "875.00"

    written = write_planning_status_outputs(result, folder / "08_STATUS_PLANEJAMENTO")
    report = written[1].read_text(encoding="utf-8")
    assert "## Resumo documental preliminar" in report
    assert "| Entradas | 1 | 125.00 |" in report
    assert "| Saídas | 2 | 875.00 |" in report
    assert "Natureza econômica: Pendente de aprovação do analista." in report
    assert "não conclui receita tributável" in report


def test_status_routes_legacy_document_schema_to_reprocessing(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    write_json(
        folder / "03_SAIDAS" / "validation-result.json",
        {
            "use_case": "UC-001",
            "schema_version": "1.8.0",
            "validation_id": "VAL-LEGACY",
            "gates": {"planning_authorized": True},
        },
    )

    result = evaluate_planning_status(folder)

    assert result["current_stage"] == "DOCUMENT_VALIDATION"
    assert result["available_actions"][0]["action"] == "RUN_DOCUMENT_VALIDATION"


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
