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


def test_uc002_extracts_deterministically_and_preserves_privacy(
    tmp_path: Path,
) -> None:
    folder, nfe_key, cte_key = make_authorized_content_case(tmp_path)

    first = extract_content_folder(folder)
    second = extract_content_folder(folder)

    assert first == second
    assert first["status"] == "CONTENT_REVIEW_REQUIRED"
    assert first["gates"] == {
        "content_extraction_ready": True,
        "lcp214_classification_ready": False,
        "analyst_review_required": True,
    }
    assert first["records_total"] == 3
    assert first["record_kind_counts"] == {
        "PRODUCT": 1,
        "SERVICE": 1,
        "TRANSPORT": 1,
    }
    assert first["analysis_group_counts"] == {
        "CTE_TOMADOS": 1,
        "NFE_SAIDAS": 1,
        "NFSE_PRESTADOS": 1,
    }
    assert first["component_count"] == 1
    assert first["document_reconciliation"]["status_counts"] == {"MATCHED": 1}
    review_codes = {finding["code"] for finding in first["review_findings"]}
    assert review_codes == {"CCLASSTRIB_MISSING", "NBS_MISSING"}

    summary_path, records_path, report_path = write_content_outputs(
        first, folder / "04_CONTEUDO"
    )
    summary = summary_path.read_text(encoding="utf-8")
    records = records_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
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


def test_uc002_blocks_product_total_mismatch(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "content-mismatch", document_families=["NFE"])
    key = access_key(COMPANY, "55", 73)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00")
    xml = xml.replace("<vProd>100.00</vProd><vNF>", "<vProd>99.00</vProd><vNF>")
    (folder / "01_XML" / "mismatch.xml").write_text(xml, encoding="utf-8")
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is True
    write_outputs(validation, folder / "03_SAIDAS")

    result = extract_content_folder(folder)

    assert result["status"] == "CONTENT_BLOCKED"
    assert result["gates"]["content_extraction_ready"] is False
    assert "DOCUMENT_PRODUCT_TOTAL_MISMATCH" in {
        finding["code"] for finding in result["blockers"]
    }
    assert main(["extract-content", str(folder)]) == 2


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_uc002_launcher_prepares_production_runtime_then_runs_without_uv(
    tmp_path: Path,
) -> None:
    folder, _, _ = make_authorized_content_case(tmp_path)
    runtime = tmp_path / "runtime"
    launcher = (
        Path(__file__).parents[4]
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
