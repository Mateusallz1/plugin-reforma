from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.acquisition import (
    review_acquisitions_folder,
    write_acquisition_outputs,
)
from fiscal_document_intake.core import ValidationError
from fiscal_document_intake.portfolio_review import (
    approve_portfolio_group,
    export_portfolio_review,
    review_portfolio,
)
from test_uc003 import RULESET, make_acquisition_case


def make_portfolio(tmp_path: Path) -> tuple[Path, list[Path]]:
    root = tmp_path / "portfolio"
    root.mkdir()
    companies: list[Path] = []
    for name in ("company-a", "company-b"):
        parent = root / name
        parent.mkdir()
        company = make_acquisition_case(parent)
        result = review_acquisitions_folder(company, RULESET)
        write_acquisition_outputs(result, company / "05_REVISAO_AQUISICOES")
        companies.append(company)
    return root, companies


def test_portfolio_groups_repeated_cases_without_exposing_local_details(
    tmp_path: Path,
) -> None:
    root, _ = make_portfolio(tmp_path)

    result = review_portfolio(root)

    assert result["status"] == "PENDING_REVIEW"
    assert result["group_count"] == 3
    assert result["occurrence_count"] == 6
    assert result["company_count"] == 2
    assert all(group["occurrence_count"] == 2 for group in result["groups"])
    assert all(group["company_count"] == 2 for group in result["groups"])
    public_text = str(result)
    assert "ITEM SINTETICO" not in public_text
    assert str(root) not in public_text
    local_report = Path(result["local_report"])
    assert "ITEM SINTETICO" in local_report.read_text(encoding="utf-8")
    assert (root / ".reforma-tributaria" / "revisoes-carteira.sqlite3").is_file()


def test_portfolio_approval_applies_and_reprocesses_selected_scope(
    tmp_path: Path,
) -> None:
    root, companies = make_portfolio(tmp_path)
    initial = review_portfolio(root)
    product = next(
        group for group in initial["groups"] if group["record_kind"] == "PRODUCT"
    )

    approved = approve_portfolio_group(
        root,
        group_id=product["group_id"],
        nature="MERCADORIA_REVENDA",
        scope="PORTFOLIO",
        approved_by="ANALISTA-TESTE",
        note="Decisão sintética",
        ruleset_path=RULESET,
    )

    assert approved["status"] == "APPROVED"
    assert approved["affected_occurrences"] == 2
    assert approved["affected_companies"] == 2
    assert len(approved["reprocessed_companies"]) == 2
    for company in companies:
        decision = (company / "00_CONTROLE" / "classificacao-aquisicoes.csv").read_text(
            encoding="utf-8-sig"
        )
        assert "MERCADORIA_REVENDA;APROVADO;ANALISTA-TESTE" in decision
    remaining = review_portfolio(root)
    assert remaining["group_count"] == 2
    assert remaining["occurrence_count"] == 4

    repeated = approve_portfolio_group(
        root,
        group_id=product["group_id"],
        nature="MERCADORIA_REVENDA",
        scope="PORTFOLIO",
        approved_by="ANALISTA-TESTE",
        note="Decisão sintética",
        ruleset_path=RULESET,
    )
    assert repeated == approved


def test_portfolio_company_scope_does_not_cross_company_boundary(
    tmp_path: Path,
) -> None:
    root, _ = make_portfolio(tmp_path)
    initial = review_portfolio(root)
    service = next(
        group for group in initial["groups"] if group["record_kind"] == "SERVICE"
    )
    selected_company = service["company_refs"][0]

    approved = approve_portfolio_group(
        root,
        group_id=service["group_id"],
        nature="SERVICO_OPERACIONAL",
        scope="COMPANY",
        company_ref=selected_company,
        approved_by="ANALISTA-TESTE",
        ruleset_path=RULESET,
    )

    assert approved["affected_occurrences"] == 1
    assert approved["company_refs"] == [selected_company]
    remaining = review_portfolio(root)
    service_remaining = next(
        group for group in remaining["groups"] if group["record_kind"] == "SERVICE"
    )
    assert service_remaining["occurrence_count"] == 1
    assert service_remaining["company_count"] == 1


def test_portfolio_reuses_approved_rule_for_new_compatible_occurrence(
    tmp_path: Path,
) -> None:
    root, _ = make_portfolio(tmp_path)
    initial = review_portfolio(root)
    product = next(
        group for group in initial["groups"] if group["record_kind"] == "PRODUCT"
    )
    approve_portfolio_group(
        root,
        group_id=product["group_id"],
        nature="MERCADORIA_REVENDA",
        scope="PORTFOLIO",
        approved_by="ANALISTA-TESTE",
        ruleset_path=RULESET,
    )
    parent = root / "company-c"
    parent.mkdir()
    company = make_acquisition_case(parent)
    result = review_acquisitions_folder(company, RULESET)
    write_acquisition_outputs(result, company / "05_REVISAO_AQUISICOES")

    refreshed = review_portfolio(root, ruleset_path=RULESET)

    assert refreshed["auto_applied_occurrences"] == 1
    assert refreshed["auto_applied_companies"] == 1
    assert len(refreshed["reprocessed_companies"]) == 1
    assert refreshed["group_count"] == 2
    decision = (company / "00_CONTROLE" / "classificacao-aquisicoes.csv").read_text(
        encoding="utf-8-sig"
    )
    assert "MERCADORIA_REVENDA;APROVADO;ANALISTA-TESTE" in decision


def test_portfolio_rejects_incompatible_nature_and_supports_optional_export(
    tmp_path: Path,
) -> None:
    root, _ = make_portfolio(tmp_path)
    initial = review_portfolio(root)
    product = next(
        group for group in initial["groups"] if group["record_kind"] == "PRODUCT"
    )

    with pytest.raises(ValidationError, match="incompatível"):
        approve_portfolio_group(
            root,
            group_id=product["group_id"],
            nature="SERVICO_OPERACIONAL",
            scope="PORTFOLIO",
            approved_by="ANALISTA-TESTE",
        )

    exported = export_portfolio_review(root)
    assert exported["status"] == "EXPORTED"
    assert exported["group_count"] == 3
    assert Path(exported["output"]).is_file()


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_portfolio_launcher_lists_pending_groups(tmp_path: Path) -> None:
    root, _ = make_portfolio(tmp_path)
    runtime = tmp_path / "runtime"
    plugin_root = Path(__file__).parents[2]
    launcher = (
        plugin_root
        / "skills"
        / "revisar-carteira-aquisicoes"
        / "scripts"
        / "run-portfolio-review.ps1"
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
            "List",
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
    assert response["status"] == "PENDING_REVIEW"
    assert response["group_count"] == 3
