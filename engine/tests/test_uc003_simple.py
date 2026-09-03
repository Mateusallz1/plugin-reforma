from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from fiscal_document_intake.cli import main
from fiscal_document_intake.core import ValidationError
from fiscal_document_intake.revenue import REVENUE_SCHEMA_VERSION
from fiscal_document_intake.simple_reconciliation import (
    discover_group_period_folders,
    reconcile_simple_revenue,
    reconcile_simple_revenue_group,
    write_simple_reconciliation_outputs,
)
from reportlab.pdfgen import canvas

PLUGIN_ROOT = Path(__file__).parents[2]
MATRIX = "12345678000195"
BRANCH = "98765432000198"


def establishment_ref(taxpayer_id: str) -> str:
    digest = hashlib.sha256(taxpayer_id.encode()).hexdigest()[:10].upper()
    return f"ESTAB-{digest}"


def formatted_cnpj(value: str) -> str:
    return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"


def write_revenue_summary(
    folder: Path,
    *,
    period: str = "2026-01",
    goods: str = "100.00",
    services: str = "200.00",
    status: str = "REVENUE_REVIEW_READY",
    establishment_id: str = MATRIX,
    entity_ref: str = "EMPRESA-SYNTHETIC",
    reviewed_documents: int | None = None,
) -> None:
    target = folder / "06_REVISAO_RECEITAS"
    target.mkdir(parents=True)
    payload = {
        "schema": "br.com.planejamento-reforma-tributaria/revenue-review",
        "schema_version": REVENUE_SCHEMA_VERSION,
        "use_case": "UC-003",
        "phase": "REVENUE_REVIEW",
        "review_id": "REV-SYNTHETIC000001",
        "status": status,
        "scope": {
            "entity_ref": entity_ref,
            "establishment_ref": establishment_ref(establishment_id),
            "period": period,
        },
        "totals": {
            "gross_revenue_goods": goods,
            "gross_revenue_services": services,
            "gross_revenue_transport": "0.00",
            "other_revenue": "0.00",
            "sales_returns_inbound": "0.00",
        },
        "gates": {"revenue_population_ready": True},
    }
    if reviewed_documents is not None:
        payload["reviewed_documents"] = reviewed_documents
    (target / "revenue-summary.json").write_text(json.dumps(payload), encoding="utf-8")


def write_pgdas_declaration(
    folder: Path,
    *,
    period: str = "01/2026",
    matrix_goods: str = "100,00",
    matrix_services: str = "200,00",
    branch_goods: str | None = "50,00",
    revenue_regime: str = "Competencia",
) -> Path:
    folder.mkdir(parents=True)
    path = folder / "PGDASD-DECLARACAO-SINTETICA.pdf"

    def _amount(value: str) -> Decimal:
        return Decimal(value.replace(".", "").replace(",", "."))

    total = _amount(matrix_goods) + _amount(matrix_services)
    if branch_goods is not None:
        total += _amount(branch_goods)
    declared_total = (
        f"{total:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    )
    lines = [
        "Programa Gerador do Documento de Arrecadacao do Simples Nacional - Declaratorio",
        "Declaracao Original",
        f"Periodo de Apuracao: 01/{period} a 31/{period}",
        f"CNPJ Matriz: {formatted_cnpj(MATRIX)}",
        f"Regime de Apuracao: {revenue_regime}",
        "No da Declaracao: 12345678901234567",
        f"Receita Bruta do PA (RPA) - Competencia {declared_total} 0,00 {declared_total}",
        "2.7) Informacoes da Declaracao por Estabelecimento",
        f"CNPJ Estabelecimento: {formatted_cnpj(MATRIX)}",
        "Valor do Debito por Tributo para a Atividade (R$):",
        "Revenda de mercadorias, exceto para o exterior",
        f"Receita Bruta Informada: R$ {matrix_goods}",
        "Valor do Debito por Tributo para a Atividade (R$):",
        "Prestacao de Servicos, exceto para o exterior",
        f"Receita Bruta Informada: R$ {matrix_services}",
    ]
    if branch_goods is not None:
        lines.extend(
            [
                f"CNPJ Estabelecimento: {formatted_cnpj(BRANCH)}",
                "Valor do Debito por Tributo para a Atividade (R$):",
                "Revenda de mercadorias, exceto para o exterior",
                f"Receita Bruta Informada: R$ {branch_goods}",
            ]
        )
    lines.append("2.8) Total Geral da Empresa")

    document = canvas.Canvas(str(path))
    y = 810
    for line in lines:
        if y < 50:
            document.showPage()
            y = 810
        document.drawString(40, y, line)
        y -= 22
    document.save()
    return path


def test_uc003c_reconciles_matrix_and_preserves_partial_group_coverage(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "company"
    pgdas = tmp_path / "pgdas"
    write_revenue_summary(folder)
    write_pgdas_declaration(pgdas)

    result = reconcile_simple_revenue(folder, pgdas)

    assert result["status"] == "SIMPLE_REVENUE_PARTIAL_COVERAGE"
    assert result["gates"]["documentary_scope_reconciled"] is True
    assert result["gates"]["group_coverage_complete"] is False
    assert result["gates"]["analyst_review_required"] is True
    assert result["gates"]["non_issuance_confirmed"] is False
    assert result["totals"]["matched_difference"] == "0.00"
    assert result["totals"]["uncovered_pgdas_revenue"] == "50.00"
    assert result["status_counts"] == {
        "ESTABLISHMENT_DOCUMENTS_MISSING": 1,
        "RECONCILED": 2,
    }

    written = write_simple_reconciliation_outputs(
        result, folder / "07_CONCILIACAO_SIMPLES"
    )
    assert len(written) == 5
    for path in written:
        assert path.is_file()
    combined = "\n".join(path.read_text(encoding="utf-8-sig") for path in written)
    assert MATRIX not in combined
    assert BRANCH not in combined
    assert "12345678901234567" not in combined
    report = written[4].read_text(encoding="utf-8")
    assert (
        "Receita PGDAS-D declarada por estabelecimento fora do escopo documental analisado"
        in report
    )
    assert "Receita declarada fora da cobertura documental" not in report


def test_uc003c_consolidates_matrix_and_branch_from_one_portfolio_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "portfolio"
    matrix_folder = root / "MATRIZ" / "01-2026"
    branch_folder = root / "FILIAL" / "01-2026"
    pgdas = root / "SN" / "01-2026"
    write_revenue_summary(matrix_folder, establishment_id=MATRIX)
    write_revenue_summary(
        branch_folder,
        goods="50.00",
        services="0.00",
        establishment_id=BRANCH,
    )
    write_pgdas_declaration(pgdas, branch_goods="50,00")

    assert discover_group_period_folders(root, "2026-01") == sorted(
        [matrix_folder, branch_folder], key=lambda item: item.as_posix().casefold()
    )
    result = reconcile_simple_revenue_group([matrix_folder, branch_folder], pgdas)

    assert result["phase"] == "SIMPLE_REVENUE_GROUP_RECONCILIATION"
    assert result["status"] == "SIMPLE_REVENUE_RECONCILED"
    assert result["scope"]["documentary_establishments"] == 2
    assert result["scope"]["pgdas_establishments"] == 2
    assert result["gates"]["group_coverage_complete"] is True
    assert result["gates"]["documentary_scope_reconciled"] is True
    assert result["totals"]["matched_difference"] == "0.00"


def test_uc003c_group_marks_zero_document_establishment_as_missing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "portfolio-zero-documents"
    matrix_folder = root / "MATRIZ" / "01-2026"
    branch_folder = root / "FILIAL" / "01-2026"
    pgdas = root / "SN" / "01-2026"
    write_revenue_summary(matrix_folder, establishment_id=MATRIX)
    write_revenue_summary(
        branch_folder,
        goods="0.00",
        services="0.00",
        status="REVENUE_REVIEW_NO_DOCUMENT",
        establishment_id=BRANCH,
        reviewed_documents=0,
    )
    write_pgdas_declaration(pgdas, branch_goods="50,00")

    result = reconcile_simple_revenue_group([matrix_folder, branch_folder], pgdas)

    assert result["status"] == "SIMPLE_REVENUE_PARTIAL_COVERAGE"
    assert result["scope"]["documentary_establishments"] == 1
    assert result["coverage"]["missing_establishment_refs"] == [
        establishment_ref(BRANCH)
    ]
    assert result["status_counts"] == {
        "ESTABLISHMENT_DOCUMENTS_MISSING": 1,
        "RECONCILED": 2,
    }
    assert result["totals"]["uncovered_pgdas_revenue"] == "50.00"


def test_uc003c_accepts_explicit_group_identity_for_distinct_establishment_refs(
    tmp_path: Path,
) -> None:
    matrix_folder = tmp_path / "MATRIZ" / "01-2026"
    branch_folder = tmp_path / "FILIAL" / "01-2026"
    pgdas = tmp_path / "pgdas"
    write_revenue_summary(
        matrix_folder, establishment_id=MATRIX, entity_ref="EMPRESA-MATRIZ"
    )
    write_revenue_summary(
        branch_folder, establishment_id=BRANCH, entity_ref="EMPRESA-FILIAL"
    )
    write_pgdas_declaration(pgdas)

    result = reconcile_simple_revenue_group(
        [matrix_folder, branch_folder], pgdas, group_entity_ref="GRUPO-SYNTHETIC"
    )

    assert result["scope"]["entity_ref"] == "GRUPO-SYNTHETIC"
    assert result["gates"]["group_coverage_complete"] is True


def test_uc003c_reads_month_from_period_start_date(tmp_path: Path) -> None:
    folder = tmp_path / "company-february"
    pgdas = tmp_path / "pgdas-february"
    write_revenue_summary(folder, period="2026-02")
    write_pgdas_declaration(pgdas, period="02/2026")

    result = reconcile_simple_revenue(folder, pgdas)

    assert result["scope"]["period"] == "2026-02"


def test_uc003c_warns_on_cash_regime_without_blocking(tmp_path: Path) -> None:
    folder = tmp_path / "company-cash"
    pgdas = tmp_path / "pgdas-cash"
    write_revenue_summary(folder)
    write_pgdas_declaration(pgdas, branch_goods=None, revenue_regime="Caixa")

    result = reconcile_simple_revenue(folder, pgdas)

    assert result["scope"]["revenue_regime"] == "CAIXA"
    assert {warning["code"] for warning in result["warnings"]} == {
        "REVENUE_REGIME_CAIXA"
    }
    assert result["gates"]["simple_reconciliation_execution_ready"] is True
    assert result["gates"]["documentary_scope_reconciled"] is True
    report = write_simple_reconciliation_outputs(
        result, folder / "07_CONCILIACAO_SIMPLES"
    )[4].read_text(encoding="utf-8")
    assert "regime CAIXA exige análise temporal específica" in report


def test_uc003c_marks_declared_revenue_without_document_support(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "company"
    pgdas = tmp_path / "pgdas"
    write_revenue_summary(folder, services="0.00")
    write_pgdas_declaration(pgdas, branch_goods=None)

    result = reconcile_simple_revenue(folder, pgdas)

    assert result["status"] == "SIMPLE_REVENUE_REVIEW_REQUIRED"
    assert result["gates"]["documentary_scope_reconciled"] is False
    assert result["gates"]["non_issuance_confirmed"] is False
    assert result["status_counts"]["DECLARED_WITHOUT_DOCUMENT_SUPPORT"] == 1
    assert (
        main(
            [
                "reconcile-simple-revenue",
                str(folder),
                "--pgdas-folder",
                str(pgdas),
            ]
        )
        == 2
    )


def test_uc003c_marks_zero_document_establishment_as_missing_support(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "company-zero-documents"
    pgdas = tmp_path / "pgdas-zero-documents"
    write_revenue_summary(
        folder,
        goods="0.00",
        services="0.00",
        status="REVENUE_REVIEW_NO_DOCUMENT",
        reviewed_documents=0,
    )
    write_pgdas_declaration(
        pgdas,
        matrix_goods="15778,00",
        matrix_services="0,00",
        branch_goods=None,
    )

    result = reconcile_simple_revenue(folder, pgdas)

    assert result["status"] == "SIMPLE_REVENUE_REVIEW_REQUIRED"
    assert result["status_counts"] == {
        "ESTABLISHMENT_DOCUMENTS_MISSING": 1,
        "NO_MOVEMENT": 1,
    }
    assert result["totals"]["pgdas_matched_establishment"] == "15778.00"
    assert result["totals"]["documentary_matched_establishment"] == "0.00"
    assert result["totals"]["matched_difference"] == "15778.00"
    assert result["gates"]["non_issuance_confirmed"] is False


def test_uc003c_reconciles_month_without_any_fiscal_document(
    tmp_path: Path,
) -> None:
    """Ausência de documento não impede a conciliação: zero é valor apurado."""
    folder = tmp_path / "company-no-documents"
    pgdas = tmp_path / "pgdas-no-documents"
    write_revenue_summary(
        folder,
        goods="0.00",
        services="0.00",
        status="REVENUE_REVIEW_NO_DOCUMENT",
        reviewed_documents=0,
    )
    write_pgdas_declaration(pgdas, branch_goods=None)

    result = reconcile_simple_revenue(folder, pgdas)

    assert result["status"] == "SIMPLE_REVENUE_REVIEW_REQUIRED"
    assert result["gates"]["documentary_scope_reconciled"] is False
    assert result["gates"]["non_issuance_confirmed"] is False
    assert result["status_counts"] == {"ESTABLISHMENT_DOCUMENTS_MISSING": 2}
    assert result["totals"]["documentary_matched_establishment"] == "0.00"
    assert result["totals"]["pgdas_matched_establishment"] == "300.00"
    assert (
        main(["reconcile-simple-revenue", str(folder), "--pgdas-folder", str(pgdas)])
        == 2
    )


def test_uc003c_confirms_no_movement_only_against_the_declaration(
    tmp_path: Path,
) -> None:
    """Sem documento e sem receita declarada, o não movimento é conclusão das duas fontes."""
    folder = tmp_path / "company-idle"
    pgdas = tmp_path / "pgdas-idle"
    write_revenue_summary(
        folder,
        goods="0.00",
        services="0.00",
        status="REVENUE_REVIEW_NO_DOCUMENT",
    )
    write_pgdas_declaration(
        pgdas, matrix_goods="0,00", matrix_services="0,00", branch_goods=None
    )

    result = reconcile_simple_revenue(folder, pgdas)

    assert result["status"] == "SIMPLE_REVENUE_RECONCILED"
    assert result["gates"]["documentary_scope_reconciled"] is True
    assert result["gates"]["group_coverage_complete"] is True
    assert result["gates"]["analyst_review_required"] is False
    assert result["gates"]["non_issuance_confirmed"] is False
    assert result["gates"]["simulation_authorized"] is True
    assert result["gates"]["uc004_planning_authorized"] is False
    assert set(result["status_counts"]) == {"NO_MOVEMENT"}
    assert result["warnings"] == []
    written = write_simple_reconciliation_outputs(
        result, folder / "07_CONCILIACAO_SIMPLES"
    )
    assert len(written[2].read_text(encoding="utf-8-sig").splitlines()) == 1
    assert (
        main(["reconcile-simple-revenue", str(folder), "--pgdas-folder", str(pgdas)])
        == 0
    )


def test_uc003c_rejects_period_mismatch(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    pgdas = tmp_path / "pgdas"
    write_revenue_summary(folder, period="2026-02")
    write_pgdas_declaration(pgdas)

    with pytest.raises(ValidationError, match="Competência"):
        reconcile_simple_revenue(folder, pgdas)


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_uc003c_launcher_prepares_runtime_then_runs_without_uv(tmp_path: Path) -> None:
    folder = tmp_path / "company"
    pgdas = tmp_path / "pgdas"
    write_revenue_summary(folder)
    write_pgdas_declaration(pgdas)
    runtime = tmp_path / "runtime"
    launcher = (
        PLUGIN_ROOT
        / "skills"
        / "conciliar-faturamento-simples"
        / "scripts"
        / "run-simple-reconciliation.ps1"
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
        "-PgdasFolder",
        str(pgdas),
    ]

    first = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    assert first.returncode == 0, first.stderr
    assert (
        folder / "07_CONCILIACAO_SIMPLES" / "simple-reconciliation-summary.json"
    ).is_file()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "uv.cmd").write_text("@exit /b 99\n", encoding="ascii")
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
    second = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    assert second.returncode == 0, second.stderr
