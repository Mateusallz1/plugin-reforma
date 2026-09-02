from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
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


def make_authorized_content_case(tmp_path: Path) -> tuple[Path, str, str]:
    folder = make_folder(
        tmp_path,
        "content-ready",
        document_families=["NFE", "NFSE", "CTE"],
    )
    nfe_key = access_key(COMPANY, "55", 70)
    cte_key = access_key(OTHER, "57", 71)
    (folder / "01_XML" / "nfe.xml").write_text(
        nfe_xml(nfe_key, "55", COMPANY, OTHER, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    (folder / "01_XML" / "nfse.xml").write_text(
        nfse_xml([("7001", "VERIF-F001", COMPANY, OTHER, "200.00", "1")]),
        encoding="utf-8",
    )
    (folder / "01_XML" / "cte.xml").write_text(
        cte_xml(cte_key, OTHER, OTHER, COMPANY, "300.00"),
        encoding="utf-8",
    )
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is True
    write_outputs(validation, folder / "03_SAIDAS")
    return folder, nfe_key, cte_key


def write_product_ncm_catalog(folder: Path, approved_ncm: str) -> None:
    (folder / "00_CONTROLE" / "catalogo-produtos-ncm.csv").write_text(
        f"codigo_produto;ncm_aprovado;status\n1;{approved_ncm};APROVADO\n",
        encoding="utf-8",
    )


def test_uc002_extracts_deterministically_and_preserves_privacy(
    tmp_path: Path,
) -> None:
    folder, nfe_key, cte_key = make_authorized_content_case(tmp_path)

    first = extract_content_folder(folder)
    second = extract_content_folder(folder)

    assert first == second
    assert first["status"] == "CONTENT_READY_WITH_OBSERVATIONS"
    assert first["gates"] == {
        "content_extraction_ready": True,
        "uc003_analysis_authorized": True,
        "uc003_full_population_ready": True,
        "lcp214_classification_ready": False,
        "analyst_review_required": True,
    }
    assert first["uc003_eligibility"] == {
        "eligible_records": 3,
        "restricted_records": 0,
        "restriction_counts_by_scope": {},
    }
    assert first["records_total"] == 3
    assert first["record_kind_counts"] == {
        "PRODUCT": 1,
        "SERVICE": 1,
        "TRANSPORT": 1,
    }
    product = next(
        record
        for record in first["_private_records"]
        if record["record_kind"] == "PRODUCT"
    )
    assert product["nature_operation"] == "VENDA"
    assert first["analysis_group_counts"] == {
        "CTE_TOMADOS": 1,
        "NFE_SAIDAS": 1,
        "NFSE_PRESTADOS": 1,
    }
    assert first["component_count"] == 1
    assert first["document_reconciliation"]["status_counts"] == {"MATCHED": 1}
    assert first["ncm_snapshot"]["status"] == "LOADED"
    assert first["ncm_description_status_counts"] == {"INCONCLUSIVE": 1}
    observation_codes = {finding["code"] for finding in first["observations"]}
    assert observation_codes == {
        "CCLASSTRIB_MISSING",
        "NBS_MISSING",
        "PRODUCT_NCM_CATALOG_ABSENT",
    }
    assert first["restrictions"] == []

    summary_path, records_path, report_path, queue_path, ncm_review_path = (
        write_content_outputs(first, folder / "04_CONTEUDO")
    )
    summary = summary_path.read_text(encoding="utf-8")
    records = records_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    assert queue_path.is_file()
    assert ncm_review_path.is_file()
    public_output = summary + report
    assert "ITEM SINTETICO" not in public_output
    assert "SERVICO SINTETICO" not in public_output
    assert "CARGA SINTETICA" not in public_output
    assert "ITEM SINTETICO" in records
    assert "SERVICO SINTETICO" in records
    assert "CARGA SINTETICA" in records
    for private_value in (COMPANY, OTHER, nfe_key, cte_key):
        assert private_value not in summary + records + report
    assert json.loads(summary)["use_case"] == "UC-002"
    assert main(["extract-content", str(folder)]) == 0


def test_uc002_requires_uc001_authorization(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "content-without-validation")
    with pytest.raises(ValidationError, match="validation-result.json"):
        extract_content_folder(folder)

    key = access_key(COMPANY, "55", 72)
    (folder / "01_XML" / "bare.xml").write_text(
        nfe_xml(
            key,
            "55",
            COMPANY,
            OTHER,
            "2026-03-05",
            "100.00",
            protocol=False,
        ),
        encoding="utf-8",
    )
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is False
    write_outputs(validation, folder / "03_SAIDAS")
    with pytest.raises(ValidationError, match="escopo autorizado"):
        extract_content_folder(folder)


def test_uc002_rejects_legacy_uc001_schema(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "legacy-validation", document_families=["NFE"])
    key = access_key(COMPANY, "55", 71)
    (folder / "01_XML" / "sale.xml").write_text(
        nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    validation = validate_folder(folder)
    write_outputs(validation, folder / "03_SAIDAS")
    validation_path = folder / "03_SAIDAS" / "validation-result.json"
    legacy = json.loads(validation_path.read_text(encoding="utf-8"))
    legacy["schema_version"] = "1.8.0"
    validation_path.write_text(json.dumps(legacy), encoding="utf-8")

    with pytest.raises(ValidationError, match="versão vigente"):
        extract_content_folder(folder)


def test_uc002_ignores_duplicate_document_representations(tmp_path: Path) -> None:
    folder = make_folder(
        tmp_path,
        "duplicate-nfse",
        document_families=["NFSE"],
    )
    content = nfse_xml([("7101", "VERIF-DUPLICATE", COMPANY, OTHER, "200.00", "1")])
    (folder / "01_XML" / "first.xml").write_text(content, encoding="utf-8")
    (folder / "01_XML" / "duplicate.xml").write_text(content, encoding="utf-8")
    validation = validate_folder(folder)
    write_outputs(validation, folder / "03_SAIDAS")

    result = extract_content_folder(folder)

    assert result["records_total"] == 1
    assert result["record_kind_counts"] == {"SERVICE": 1}


def test_uc002_observes_product_total_mismatch_without_blocking(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "content-mismatch", document_families=["NFE"])
    key = access_key(COMPANY, "55", 73)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00")
    xml = xml.replace("<vProd>100.00</vProd><vNF>", "<vProd>99.00</vProd><vNF>")
    (folder / "01_XML" / "mismatch.xml").write_text(xml, encoding="utf-8")
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is True
    write_outputs(validation, folder / "03_SAIDAS")

    result = extract_content_folder(folder)

    assert result["status"] == "CONTENT_READY_WITH_OBSERVATIONS"
    assert result["gates"]["content_extraction_ready"] is True
    assert result["gates"]["uc003_analysis_authorized"] is True
    assert "DOCUMENT_PRODUCT_TOTAL_MISMATCH" in {
        finding["code"] for finding in result["observations"]
    }
    assert main(["extract-content", str(folder)]) == 0


def test_uc002_validates_product_ncm_from_approved_catalog(tmp_path: Path) -> None:
    folder, _, _ = make_authorized_content_case(tmp_path)
    write_product_ncm_catalog(folder, "01012100")

    result = extract_content_folder(folder)
    product = next(
        record
        for record in result["_private_records"]
        if record["record_kind"] == "PRODUCT"
    )

    assert result["product_ncm_catalog"]["status"] == "LOADED"
    assert result["product_ncm_catalog"]["approved_entries"] == 1
    assert product["product_ncm_validation"] == {
        "status": "VALIDATED",
        "source": "ANALYST_APPROVED_CATALOG",
    }
    assert product["eligible_for_uc003"] is True
    assert result["gates"]["uc003_full_population_ready"] is True


def test_uc002_restricts_only_product_with_confirmed_ncm_mismatch(
    tmp_path: Path,
) -> None:
    folder, _, _ = make_authorized_content_case(tmp_path)
    write_product_ncm_catalog(folder, "12345678")

    result = extract_content_folder(folder)
    product = next(
        record
        for record in result["_private_records"]
        if record["record_kind"] == "PRODUCT"
    )

    assert result["status"] == "CONTENT_READY_WITH_RESTRICTIONS"
    assert result["gates"]["content_extraction_ready"] is True
    assert result["gates"]["uc003_analysis_authorized"] is True
    assert result["gates"]["uc003_full_population_ready"] is False
    assert result["uc003_eligibility"]["eligible_records"] == 2
    assert result["uc003_eligibility"]["restricted_records"] == 1
    assert product["eligible_for_uc003"] is False
    assert product["product_ncm_validation"]["status"] == "MISMATCH"
    assert product["restriction_codes"] == ["PRODUCT_NCM_MISMATCH"]
    assert {finding["code"] for finding in result["restrictions"]} == {
        "PRODUCT_NCM_MISMATCH"
    }


def test_uc002_restricts_invalid_ncm_without_blocking_extraction(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "invalid-ncm", document_families=["NFE"])
    key = access_key(COMPANY, "55", 74)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00")
    xml = xml.replace("<NCM>01012100</NCM>", "<NCM>INVALIDO</NCM>")
    (folder / "01_XML" / "invalid-ncm.xml").write_text(xml, encoding="utf-8")
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is True
    write_outputs(validation, folder / "03_SAIDAS")

    result = extract_content_folder(folder)

    assert result["gates"]["content_extraction_ready"] is True
    assert result["gates"]["uc003_analysis_authorized"] is False
    assert result["uc003_eligibility"]["restricted_records"] == 1
    assert {finding["code"] for finding in result["restrictions"]} == {"NCM_INVALID"}
    assert main(["extract-content", str(folder)]) == 0


def test_uc002_restricts_ncm_not_effective_in_current_snapshot(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "ncm-not-effective", document_families=["NFE"])
    key = access_key(COMPANY, "55", 75)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00")
    xml = xml.replace("<NCM>01012100</NCM>", "<NCM>99999999</NCM>")
    (folder / "01_XML" / "ncm-not-effective.xml").write_text(xml, encoding="utf-8")
    validation = validate_folder(folder)
    write_outputs(validation, folder / "03_SAIDAS")

    result = extract_content_folder(folder)
    product = result["_private_records"][0]

    assert product["ncm_description_review"]["status"] == "UNVERIFIABLE"
    assert product["ncm_description_review"]["reason_codes"] == ["NCM_NOT_EFFECTIVE"]
    assert product["eligible_for_uc003"] is False
    assert {finding["code"] for finding in result["restrictions"]} == {
        "NCM_NOT_EFFECTIVE"
    }


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_uc002_launcher_prepares_production_runtime_then_runs_without_uv(
    tmp_path: Path,
) -> None:
    folder, _, _ = make_authorized_content_case(tmp_path)
    runtime = tmp_path / "runtime"
    launcher = (
        PLUGIN_ROOT
        / "skills"
        / "extrair-conteudo-fiscal"
        / "scripts"
        / "run-content-extractor.ps1"
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
    assert (runtime / "Scripts" / "fiscal-document-intake.exe").is_file()
    assert (folder / "04_CONTEUDO" / "content-summary.json").is_file()
    assert (folder / "04_CONTEUDO" / "normalized-items.local.jsonl").is_file()
    assert (folder / "04_CONTEUDO" / "relatorio-qualidade-conteudo.md").is_file()
    site_packages = runtime / "Lib" / "site-packages"
    assert not (site_packages / "pytest").exists()
    assert not (site_packages / "reportlab").exists()
    assert not (site_packages / "ruff").exists()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "uv.cmd").write_text("@exit /b 99\n", encoding="ascii")
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

    second = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )

    assert second.returncode == 0, second.stderr
