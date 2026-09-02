from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.acquisition import (
    review_acquisitions_folder,
    write_acquisition_outputs,
)
from fiscal_document_intake.cli import main
from fiscal_document_intake.content import extract_content_folder, write_content_outputs
from fiscal_document_intake.core import ValidationError, validate_folder, write_outputs
from test_uc001 import (
    COMPANY,
    OTHER,
    access_key,
    cte_xml,
    make_folder,
    nfe_xml,
    nfse_xml,
)

PLUGIN_ROOT = Path(__file__).parents[2]
RULESET = (
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


def make_acquisition_case(tmp_path: Path) -> Path:
    folder = make_folder(
        tmp_path,
        "acquisitions",
        document_families=["NFE", "NFSE", "CTE"],
    )
    nfe_key = access_key(OTHER, "55", 80)
    cte_key = access_key(OTHER, "57", 81)
    (folder / "01_XML" / "nfe-entry.xml").write_text(
        nfe_xml(nfe_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    (folder / "01_XML" / "nfse-taken.xml").write_text(
        nfse_xml([("8001", "VERIF-H001", OTHER, COMPANY, "200.00", "1")]),
        encoding="utf-8",
    )
    (folder / "01_XML" / "cte-taken.xml").write_text(
        cte_xml(cte_key, OTHER, OTHER, COMPANY, "300.00"),
        encoding="utf-8",
    )
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is True
    write_outputs(validation, folder / "03_SAIDAS")
    content = extract_content_folder(folder)
    assert content["gates"]["uc003_analysis_authorized"] is True
    write_content_outputs(content, folder / "04_CONTEUDO")
    return folder


def test_uc003_reviews_acquisitions_deterministically_and_preserves_privacy(
    tmp_path: Path,
) -> None:
    folder = make_acquisition_case(tmp_path)

    first = review_acquisitions_folder(folder, RULESET)
    second = review_acquisitions_folder(folder, RULESET)

    assert first == second
    assert first["status"] == "ACQUISITION_REVIEW_READY_WITH_PENDING"
    assert first["acquisition_records"] == 3
    assert first["non_acquisition_records"] == 0
    assert first["category_counts"] == {
        "PURCHASE_GOODS": 1,
        "PURCHASE_SERVICES": 1,
        "PURCHASE_TRANSPORT": 1,
    }
    assert first["category_amounts"] == {
        "PURCHASE_GOODS": "100.00",
        "PURCHASE_SERVICES": "200.00",
        "PURCHASE_TRANSPORT": "300.00",
    }
    assert first["nature_status_counts"] == {"PENDING_ANALYST_CLASSIFICATION": 3}
    assert first["legal_evidence_status_counts"] == {
        "CONFIRMED_DECLARED": 1,
        "PENDING_EVIDENCE": 2,
    }
    assert first["gates"] == {
        "uc003_execution_ready": True,
        "acquisition_review_required": True,
        "operational_classification_complete": True,
        "acquisition_review_complete": False,
        "legal_evidence_complete": False,
        "analyst_review_required": True,
        "uc004_planning_authorized": False,
    }
    assert first["ruleset_lock"]["classification_records"] == 164
    assert first["ruleset_lock"]["cst_records"] == 18

    summary_path, records_path, queue_path, lock_path, report_path = (
        write_acquisition_outputs(first, folder / "05_REVISAO_AQUISICOES")
    )
    public_output = (
        summary_path.read_text(encoding="utf-8")
        + lock_path.read_text(encoding="utf-8")
        + report_path.read_text(encoding="utf-8")
    )
    local_output = records_path.read_text(encoding="utf-8") + queue_path.read_text(
        encoding="utf-8-sig"
    )
    for description in ("ITEM SINTETICO", "SERVICO SINTETICO", "CARGA SINTETICA"):
        assert description not in public_output
        assert description in local_output
    assert COMPANY not in public_output + local_output
    assert OTHER not in public_output + local_output
    assert main(["review-acquisitions", str(folder), "--ruleset", str(RULESET)]) == 0


def test_uc003_documentary_totals_use_unique_document_values(tmp_path: Path) -> None:
    folder = make_acquisition_case(tmp_path)
    result = review_acquisitions_folder(
        folder,
        RULESET,
        cfop_ruleset_path=CFOP_RULESET,
        analyst_rules_path=ANALYST_RULES,
    )

    assert result["documentary_totals"] == {
        "amount_basis": "UNIQUE_DOCUMENT_TOTAL",
        "document_count": 3,
        "gross_documentary_purchases": "600.00",
        "pending_document_count": 0,
        "pending_purchase_treatment": "0.00",
        "non_purchase_entry_operations": "0.00",
        "by_document_type": {"CTE": "300.00", "NFE": "100.00", "NFSE": "200.00"},
        "by_analysis_group": {
            "CTE_TOMADOS": "300.00",
            "NFE_ENTRADAS": "100.00",
            "NFSE_TOMADOS": "200.00",
        },
        "cross_document_linkage": "NOT_PERFORMED",
    }


def test_uc003_does_not_count_sales_return_as_purchase(tmp_path: Path) -> None:
    folder = make_acquisition_case(tmp_path)
    return_key = access_key(OTHER, "55", 82)
    return_xml = nfe_xml(
        return_key, "55", OTHER, COMPANY, "2026-03-06", "50.00"
    ).replace("<CFOP>5102</CFOP>", "<CFOP>1202</CFOP>")
    (folder / "01_XML" / "sales-return.xml").write_text(return_xml, encoding="utf-8")
    validation = validate_folder(folder)
    write_outputs(validation, folder / "03_SAIDAS")
    content = extract_content_folder(folder)
    write_content_outputs(content, folder / "04_CONTEUDO")

    result = review_acquisitions_folder(
        folder,
        RULESET,
        cfop_ruleset_path=CFOP_RULESET,
        analyst_rules_path=ANALYST_RULES,
    )

    assert result["acquisition_records"] == 3
    assert result["non_acquisition_records"] == 1
    assert result["documentary_totals"]["gross_documentary_purchases"] == "600.00"
    assert result["documentary_totals"]["non_purchase_entry_operations"] == "50.00"


def test_uc003_applies_only_approved_compatible_analyst_decisions(
    tmp_path: Path,
) -> None:
    folder = make_acquisition_case(tmp_path)
    initial = review_acquisitions_folder(folder, RULESET)
    nature_by_kind = {
        "PRODUCT": "MERCADORIA_REVENDA",
        "SERVICE": "SERVICO_OPERACIONAL",
        "TRANSPORT": "FRETE_COMPRA",
    }
    lines = ["item_ref;natureza;status;aprovado_por;observacao"]
    for record in initial["_private_records"]:
        lines.append(
            f"{record['item_ref']};{nature_by_kind[record['record_kind']]};"
            "APROVADO;ANALISTA-SINTETICO;Teste"
        )
    (folder / "00_CONTROLE" / "classificacao-aquisicoes.csv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    result = review_acquisitions_folder(folder, RULESET)

    assert result["review_id"] != initial["review_id"]
    assert result["nature_status_counts"] == {"ANALYST_APPROVED": 3}
    assert result["gates"]["acquisition_review_complete"] is True
    assert result["gates"]["legal_evidence_complete"] is False
    assert result["gates"]["uc004_planning_authorized"] is False


def test_uc003_rejects_incompatible_or_unknown_analyst_decisions(
    tmp_path: Path,
) -> None:
    folder = make_acquisition_case(tmp_path)
    initial = review_acquisitions_folder(folder, RULESET)
    product = next(
        record
        for record in initial["_private_records"]
        if record["record_kind"] == "PRODUCT"
    )
    decision_path = folder / "00_CONTROLE" / "classificacao-aquisicoes.csv"
    decision_path.write_text(
        "item_ref;natureza;status;aprovado_por;observacao\n"
        f"{product['item_ref']};SERVICO_OPERACIONAL;APROVADO;ANALISTA;Teste\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="natureza incompatível"):
        review_acquisitions_folder(folder, RULESET)

    decision_path.write_text(
        "item_ref;natureza;status;aprovado_por;observacao\n"
        "ITEM-INEXISTENTE;INSUMO;APROVADO;ANALISTA;Teste\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="itens ausentes"):
        review_acquisitions_folder(folder, RULESET)


def test_uc003_requires_authorized_uc002_outputs(tmp_path: Path) -> None:
    folder = tmp_path / "missing-content"
    folder.mkdir()
    with pytest.raises(ValidationError, match="content-summary.json"):
        review_acquisitions_folder(folder, RULESET)


def test_uc003_handles_period_without_acquisitions(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "sales-only", document_families=["NFE"])
    key = access_key(COMPANY, "55", 82)
    (folder / "01_XML" / "sale.xml").write_text(
        nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    validation = validate_folder(folder)
    write_outputs(validation, folder / "03_SAIDAS")
    content = extract_content_folder(folder)
    write_content_outputs(content, folder / "04_CONTEUDO")

    result = review_acquisitions_folder(folder, RULESET)

    assert result["status"] == "ACQUISITION_REVIEW_NO_DOCUMENT"
    assert result["acquisition_records"] == 0
    assert result["gates"]["uc003_execution_ready"] is True
    assert result["gates"]["acquisition_review_required"] is False
    assert result["gates"]["analyst_review_required"] is False


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_uc003_launcher_prepares_runtime_then_runs_without_uv(tmp_path: Path) -> None:
    folder = make_acquisition_case(tmp_path)
    runtime = tmp_path / "runtime"
    launcher = (
        PLUGIN_ROOT
        / "skills"
        / "revisar-aquisicoes"
        / "scripts"
        / "run-acquisition-review.ps1"
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
    assert (folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json").is_file()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "uv.cmd").write_text("@exit /b 99\n", encoding="ascii")
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

    second = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )

    assert second.returncode == 0, second.stderr
