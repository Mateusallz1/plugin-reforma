from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.content import extract_content_folder, write_content_outputs
from fiscal_document_intake.core import validate_folder, write_outputs
from fiscal_document_intake.revenue import review_revenue_folder, write_revenue_outputs
from test_uc001 import (
    COMPANY,
    OTHER,
    access_key,
    cte_xml,
    make_folder,
    nfe_xml,
    nfse_xml,
)

SKILL = Path(__file__).parents[4] / "revisar-receitas"
CFOP_SNAPSHOT = SKILL / "references" / "snapshots" / "cfop-2026-08-25.json"
ANALYST_RULES = SKILL / "references" / "rules" / "revenue-cfop-rules-v1.json"


def prepare_content(folder: Path) -> None:
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is True
    write_outputs(validation, folder / "03_SAIDAS")
    content = extract_content_folder(folder)
    assert content["gates"]["uc003_analysis_authorized"] is True
    write_content_outputs(content, folder / "04_CONTEUDO")


def make_revenue_case(tmp_path: Path) -> Path:
    folder = make_folder(
        tmp_path,
        "revenue",
        document_families=["NFE", "NFSE", "CTE"],
    )
    intra_key = access_key(COMPANY, "55", 90)
    inter_key = access_key(COMPANY, "55", 91)
    purchase_key = access_key(OTHER, "55", 92)
    cte_key = access_key(COMPANY, "57", 93)
    (folder / "01_XML" / "sale-intra.xml").write_text(
        nfe_xml(intra_key, "55", COMPANY, OTHER, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    interstate = nfe_xml(
        inter_key, "55", COMPANY, OTHER, "2026-03-06", "200.00"
    ).replace("<CFOP>5102</CFOP>", "<CFOP>6102</CFOP>")
    (folder / "01_XML" / "sale-inter.xml").write_text(interstate, encoding="utf-8")
    (folder / "01_XML" / "purchase.xml").write_text(
        nfe_xml(purchase_key, "55", OTHER, COMPANY, "2026-03-07", "300.00"),
        encoding="utf-8",
    )
    (folder / "01_XML" / "nfse.xml").write_text(
        nfse_xml(
            [
                ("9001", "VERIF-I001", COMPANY, OTHER, "400.00", "1"),
                ("9002", "VERIF-I002", OTHER, COMPANY, "500.00", "1"),
            ]
        ),
        encoding="utf-8",
    )
    (folder / "01_XML" / "cte.xml").write_text(
        cte_xml(cte_key, COMPANY, OTHER, OTHER, "600.00", taker_code="0"),
        encoding="utf-8",
    )
    prepare_content(folder)
    return folder


def test_uc003b_reviews_revenue_deterministically_and_uses_document_totals(
    tmp_path: Path,
) -> None:
    folder = make_revenue_case(tmp_path)

    first = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    second = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)

    assert first == second
    assert first["status"] == "REVENUE_REVIEW_READY"
    assert first["reviewed_documents"] == 4
    assert first["classification_counts"] == {
        "REVENUE_GOODS": 2,
        "REVENUE_SERVICES": 1,
        "REVENUE_TRANSPORT": 1,
    }
    assert first["totals"] == {
        "gross_revenue_goods": "300.00",
        "gross_revenue_services": "400.00",
        "gross_revenue_transport": "600.00",
        "other_revenue": "0.00",
        "gross_operational_revenue": "1300.00",
        "sales_returns_inbound": "0.00",
        "net_documentary_revenue_candidate": "1300.00",
        "excluded_non_revenue_operations": "0.00",
        "pending_revenue_treatment": "0.00",
        "unallocated_document_components": "0.00",
    }
    assert first["gates"]["revenue_population_ready"] is True
    assert first["gates"]["analyst_review_required"] is False
    assert first["gates"]["uc004_planning_authorized"] is False
    assert set(first["cfop_summary"]) == {"5102", "6102"}
    assert first["cfop_summary"]["5102"]["item_amount"] == "100.00"

    summary, records, queue, lock, report = write_revenue_outputs(
        first, folder / "06_REVISAO_RECEITAS"
    )
    public = (
        summary.read_text(encoding="utf-8")
        + lock.read_text(encoding="utf-8")
        + report.read_text(encoding="utf-8")
    )
    local = records.read_text(encoding="utf-8")
    assert "ITEM SINTETICO" not in public
    assert COMPANY not in public + local
    assert OTHER not in public + local
    assert queue.read_text(encoding="utf-8-sig").count("\n") == 1


def test_uc003b_separates_sales_returns_purchase_returns_and_remittances(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "returns", document_families=["NFE"])
    inbound_key = access_key(OTHER, "55", 94)
    outbound_key = access_key(COMPANY, "55", 95)
    remittance_key = access_key(COMPANY, "55", 96)
    inbound = nfe_xml(
        inbound_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"
    ).replace("<CFOP>5102</CFOP>", "<CFOP>1202</CFOP>")
    outbound = nfe_xml(
        outbound_key, "55", COMPANY, OTHER, "2026-03-06", "200.00"
    ).replace("<CFOP>5102</CFOP>", "<CFOP>5202</CFOP>")
    remittance = nfe_xml(
        remittance_key, "55", COMPANY, OTHER, "2026-03-07", "300.00"
    ).replace("<CFOP>5102</CFOP>", "<CFOP>5901</CFOP>")
    for name, xml in (
        ("inbound-return.xml", inbound),
        ("outbound-return.xml", outbound),
        ("remittance.xml", remittance),
    ):
        (folder / "01_XML" / name).write_text(xml, encoding="utf-8")
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)

    assert result["classification_counts"] == {
        "NON_REVENUE_REMITTANCE": 1,
        "PURCHASE_RETURN_OUTBOUND": 1,
        "SALES_RETURN_INBOUND": 1,
    }
    assert result["totals"]["gross_operational_revenue"] == "0.00"
    assert result["totals"]["sales_returns_inbound"] == "100.00"
    assert result["totals"]["net_documentary_revenue_candidate"] == "-100.00"
    assert result["totals"]["excluded_non_revenue_operations"] == "500.00"


def test_uc003b_keeps_mixed_cfop_document_pending(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "mixed-revenue", document_families=["NFE"])
    key = access_key(COMPANY, "55", 97)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00")
    second_item = """
    <det nItem="2"><prod><cProd>2</cProd><xProd>REMESSA SINTETICA</xProd><NCM>00000000</NCM><CFOP>5901</CFOP><qCom>1.00</qCom><vUnCom>50.00</vUnCom><vProd>50.00</vProd></prod><imposto/></det>"""
    xml = xml.replace("    <total>", second_item + "\n    <total>")
    xml = xml.replace(
        "<total><ICMSTot><vProd>100.00</vProd><vNF>100.00</vNF>",
        "<total><ICMSTot><vProd>150.00</vProd><vNF>150.00</vNF>",
    )
    (folder / "01_XML" / "mixed.xml").write_text(xml, encoding="utf-8")
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)

    assert result["classification_counts"] == {"MIXED_DOCUMENT_PENDING_ALLOCATION": 1}
    assert result["totals"]["pending_revenue_treatment"] == "150.00"
    assert result["gates"]["cfop_classification_complete"] is False
    assert result["gates"]["revenue_population_ready"] is False


def test_uc003b_preserves_document_item_difference(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "revenue-difference", document_families=["NFE"])
    key = access_key(COMPANY, "55", 98)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00")
    xml = xml.replace("<vProd>100.00</vProd>", "<vProd>90.00</vProd>", 1)
    (folder / "01_XML" / "difference.xml").write_text(xml, encoding="utf-8")
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)

    assert result["totals"]["gross_revenue_goods"] == "100.00"
    assert result["totals"]["unallocated_document_components"] == "10.00"
    assert result["gates"]["document_item_totals_explained"] is False
    assert result["gates"]["analyst_review_required"] is True


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_uc003b_launcher_prepares_runtime_then_runs_without_uv(tmp_path: Path) -> None:
    folder = make_revenue_case(tmp_path)
    runtime = tmp_path / "runtime"
    launcher = SKILL / "scripts" / "run-revenue-review.ps1"
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
    assert (folder / "06_REVISAO_RECEITAS" / "revenue-summary.json").is_file()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "uv.cmd").write_text("@exit /b 99\n", encoding="ascii")
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
    second = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    assert second.returncode == 0, second.stderr
