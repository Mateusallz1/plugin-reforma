from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.content import extract_content_folder, write_content_outputs
from fiscal_document_intake.core import ValidationError, validate_folder, write_outputs
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

PLUGIN_ROOT = Path(__file__).parents[2]
SKILL = PLUGIN_ROOT / "skills" / "revisar-receitas"
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
        "purchase_returns_outbound": "0.00",
        "net_documentary_revenue_candidate": "1300.00",
        "excluded_non_revenue_operations": "0.00",
        "pending_revenue_treatment": "0.00",
        "unallocated_document_components": "0.00",
    }
    assert first["gates"]["revenue_population_ready"] is True
    assert first["gates"]["analyst_review_required"] is False
    assert first["gates"]["simulation_authorized"] is True
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


def test_uc003b_treats_apurated_zero_as_ready_population(tmp_path: Path) -> None:
    """Competência só com entradas apura receita zero, e zero é população pronta."""
    folder = make_folder(tmp_path, "revenue-only-purchases", document_families=["NFE"])
    purchase_key = access_key(OTHER, "55", 94)
    (folder / "01_XML" / "purchase.xml").write_text(
        nfe_xml(purchase_key, "55", OTHER, COMPANY, "2026-03-07", "300.00"),
        encoding="utf-8",
    )
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)

    assert result["status"] == "REVENUE_REVIEW_NO_DOCUMENT"
    assert result["reviewed_documents"] == 0
    assert result["totals"]["gross_operational_revenue"] == "0.00"
    assert result["gates"]["revenue_population_ready"] is True
    assert result["gates"]["revenue_review_required"] is False
    assert result["gates"]["analyst_review_required"] is False
    assert result["gates"]["simulation_authorized"] is True
    assert result["gates"]["uc004_planning_authorized"] is False


def test_uc003b_keeps_mixed_cfop_document_pending(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "mixed-revenue", document_families=["NFE"])
    key = access_key(COMPANY, "55", 97)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "100.00")
    second_item = """
    <det nItem="2"><prod><cProd>2</cProd><xProd>REMESSA SINTETICA</xProd><NCM>01012100</NCM><CFOP>5901</CFOP><qCom>1.00</qCom><vUnCom>50.00</vUnCom><vProd>50.00</vProd></prod><imposto/></det>"""
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
    registro = result["_private_records"][0]
    assert registro["unallocated_difference"] == "10.00"
    assert registro["difference_composition"] == {}
    assert registro["residual_difference"] == "10.00"
    assert result["gates"]["document_item_totals_explained"] is False
    assert result["gates"]["analyst_review_required"] is True


def _nfe_com_composicao(
    tmp_path: Path,
    nome: str,
    numero: int,
    *,
    prod: str,
    extra: str,
    vnf: str,
    total_extra: str | None = None,
) -> Path:
    folder = make_folder(tmp_path, nome, document_families=["NFE"])
    key = access_key(COMPANY, "55", numero)
    xml = nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", prod)
    xml = xml.replace(
        f"<vProd>{prod}</vProd></prod>", f"<vProd>{prod}</vProd>{extra}</prod>"
    )
    if total_extra is not None:
        xml = xml.replace(
            f"<vProd>{prod}</vProd><vNF>",
            f"<vProd>{prod}</vProd>{total_extra}<vNF>",
        )
    xml = xml.replace(f"<vNF>{prod}</vNF>", f"<vNF>{vnf}</vNF>")
    (folder / "01_XML" / f"{nome}.xml").write_text(xml, encoding="utf-8")
    prepare_content(folder)
    return folder


def test_uc003b_explains_difference_by_freight_and_discount(tmp_path: Path) -> None:
    """Diferença comprovada por componente do próprio item libera o gate."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-frete",
        95,
        prod="100.00",
        extra="<vFrete>30.00</vFrete><vDesc>10.00</vDesc>",
        vnf="120.00",
        total_extra="<vFrete>30.00</vFrete><vDesc>10.00</vDesc>",
    )

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["unallocated_difference"] == "20.00"
    assert registro["difference_composition"] == {
        "frete": "30.00",
        "desconto": "-10.00",
    }
    assert registro["explained_difference"] == "20.00"
    assert registro["residual_difference"] == "0.00"
    assert result["totals"]["unallocated_document_components"] == "0.00"
    assert result["gates"]["document_item_totals_explained"] is True
    assert result["gates"]["revenue_population_ready"] is True


def test_uc003b_explains_difference_by_ipi_and_icms_st(tmp_path: Path) -> None:
    """IPI e ICMS-ST também compõem o total do documento."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-tributos",
        96,
        prod="100.00",
        extra="",
        vnf="145.00",
        total_extra="<vST>25.00</vST><vIPI>20.00</vIPI>",
    )
    xml_path = folder / "01_XML" / "revenue-tributos.xml"
    xml = xml_path.read_text(encoding="utf-8").replace(
        "<imposto/>",
        "<imposto><ICMS><ICMS60><vICMSST>25.00</vICMSST></ICMS60></ICMS>"
        "<IPI><IPITrib><vIPI>20.00</vIPI></IPITrib></IPI></imposto>",
    )
    xml_path.write_text(xml, encoding="utf-8")
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["difference_composition"] == {"ipi": "20.00", "icms_st": "25.00"}
    assert registro["residual_difference"] == "0.00"
    assert result["gates"]["document_item_totals_explained"] is True


def test_uc003b_extracts_and_explains_insurance_fcpst_ii_and_ipi_returned(
    tmp_path: Path,
) -> None:
    """Todos os componentes normais do vNF entram na composição auditável."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-componentes-completos",
        98,
        prod="100.00",
        extra="<vSeg>10.00</vSeg>",
        vnf="125.00",
        total_extra=(
            "<vSeg>10.00</vSeg><vFCPST>5.00</vFCPST>"
            "<vII>7.00</vII><vIPIDevol>3.00</vIPIDevol>"
        ),
    )
    xml_path = folder / "01_XML" / "revenue-componentes-completos.xml"
    xml = xml_path.read_text(encoding="utf-8").replace(
        "<imposto/>",
        "<imposto><ICMS><ICMS60><vFCPST>5.00</vFCPST></ICMS60></ICMS>"
        "<II><vII>7.00</vII></II>"
        "<impostoDevol><IPI><vIPIDevol>3.00</vIPIDevol></IPI></impostoDevol></imposto>",
    )
    xml_path.write_text(xml, encoding="utf-8")
    prepare_content(folder)

    normalized = json.loads(
        (folder / "04_CONTEUDO" / "normalized-items.local.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert normalized["insurance"] == "10.00"
    assert normalized["fcp_st_amount"] == "5.00"
    assert normalized["import_duty_amount"] == "7.00"
    assert normalized["ipi_returned_amount"] == "3.00"

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["difference_composition"] == {
        "seguro": "10.00",
        "fcp_st": "5.00",
        "ii": "7.00",
        "ipi_devolvido": "3.00",
    }
    assert registro["explained_difference"] == "25.00"
    assert registro["residual_difference"] == "0.00"
    assert registro["composition_status"] == "EXPLAINED"
    assert result["gates"]["document_item_totals_explained"] is True


def test_uc003b_accepts_vnf_without_icms_deson_deduction(tmp_path: Path) -> None:
    """A representação tolerada sem deduzir vICMSDeson não cria resíduo falso."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-desonerado",
        100,
        prod="100.00",
        extra="",
        vnf="100.00",
        total_extra="<vICMSDeson>10.00</vICMSDeson>",
    )
    xml_path = folder / "01_XML" / "revenue-desonerado.xml"
    xml = xml_path.read_text(encoding="utf-8").replace(
        "<imposto/>",
        "<imposto><ICMS><ICMS20><vICMSDeson>10.00</vICMSDeson></ICMS20></ICMS></imposto>",
    )
    xml_path.write_text(xml, encoding="utf-8")
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["composition_status"] == "EXPLAINED"
    assert registro["residual_difference"] == "0.00"
    assert result["gates"]["document_item_totals_explained"] is True


def test_uc003b_does_not_double_count_document_components_across_items(
    tmp_path: Path,
) -> None:
    """Totais do documento repetidos nos itens normalizados são lidos uma vez."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-dois-itens",
        101,
        prod="100.00",
        extra="<vFrete>30.00</vFrete>",
        vnf="130.00",
        total_extra="<vFrete>30.00</vFrete>",
    )
    xml_path = folder / "01_XML" / "revenue-dois-itens.xml"
    xml = xml_path.read_text(encoding="utf-8")
    second_item = (
        '<det nItem="2"><prod><cProd>2</cProd><xProd>ITEM DOIS</xProd>'
        "<NCM>01012100</NCM><CFOP>5102</CFOP><qCom>1.00</qCom>"
        "<vUnCom>50.00</vUnCom><vProd>50.00</vProd><indTot>1</indTot>"
        "</prod><imposto/></det>"
    )
    xml = xml.replace("    <total>", f"{second_item}\n    <total>")
    xml = xml.replace(
        "<vProd>100.00</vProd><vFrete>30.00</vFrete><vNF>130.00</vNF>",
        "<vProd>150.00</vProd><vFrete>30.00</vFrete><vNF>180.00</vNF>",
    )
    xml_path.write_text(xml, encoding="utf-8")
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["item_total"] == "150.00"
    assert registro["difference_composition"] == {"frete": "30.00"}
    assert registro["explained_difference"] == "30.00"
    assert registro["residual_difference"] == "0.00"
    assert result["gates"]["document_item_totals_explained"] is True


def test_uc003b_excludes_indtot_zero_item_from_document_total_check(
    tmp_path: Path,
) -> None:
    """Item com indTot=0 não altera a base que compõe o vNF."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-indtot-zero",
        102,
        prod="100.00",
        extra="<vFrete>10.00</vFrete>",
        vnf="110.00",
        total_extra="<vFrete>10.00</vFrete>",
    )
    xml_path = folder / "01_XML" / "revenue-indtot-zero.xml"
    xml = xml_path.read_text(encoding="utf-8")
    second_item = (
        '<det nItem="2"><prod><cProd>2</cProd><xProd>ITEM FORA DO TOTAL</xProd>'
        "<NCM>01012100</NCM><CFOP>5102</CFOP><qCom>1.00</qCom>"
        "<vUnCom>50.00</vUnCom><vProd>50.00</vProd><indTot>0</indTot>"
        "</prod><imposto/></det>"
    )
    xml_path.write_text(
        xml.replace("    <total>", f"{second_item}\n    <total>"), encoding="utf-8"
    )
    prepare_content(folder)

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["item_count"] == 2
    assert registro["item_total"] == "100.00"
    assert registro["difference_composition"] == {"frete": "10.00"}
    assert registro["residual_difference"] == "0.00"
    assert result["gates"]["document_item_totals_explained"] is True


def test_uc003b_rejects_legacy_content_schema(tmp_path: Path) -> None:
    folder = make_revenue_case(tmp_path)
    summary_path = folder / "04_CONTEUDO" / "content-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["schema_version"] = "1.1.0"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValidationError, match="saídas vigentes"):
        review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)


def test_uc003b_rejects_tampered_cfop_snapshot(tmp_path: Path) -> None:
    folder = make_revenue_case(tmp_path)
    tampered_snapshot = tmp_path / CFOP_SNAPSHOT.name
    tampered_snapshot.write_bytes(CFOP_SNAPSHOT.read_bytes() + b"\n")

    with pytest.raises(ValidationError, match="Hash do snapshot oficial de CFOP"):
        review_revenue_folder(folder, tampered_snapshot, ANALYST_RULES)


def test_uc003b_keeps_residue_when_component_does_not_close(tmp_path: Path) -> None:
    """Componente parcial não fecha a diferença: o resíduo mantém o bloqueio."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-residuo",
        97,
        prod="100.00",
        extra="<vFrete>30.00</vFrete>",
        vnf="145.00",
        total_extra="<vFrete>30.00</vFrete>",
    )

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["unallocated_difference"] == "45.00"
    assert registro["difference_composition"] == {"frete": "30.00"}
    assert registro["residual_difference"] == "15.00"
    assert result["totals"]["unallocated_document_components"] == "15.00"
    assert result["gates"]["document_item_totals_explained"] is False
    assert result["gates"]["revenue_population_ready"] is False


def test_uc003b_never_distributes_the_difference_across_items(tmp_path: Path) -> None:
    """Sem rateio silencioso: a diferença fica no documento, nunca nos itens."""
    folder = _nfe_com_composicao(
        tmp_path,
        "revenue-sem-rateio",
        99,
        prod="100.00",
        extra="<vFrete>30.00</vFrete>",
        vnf="130.00",
        total_extra="<vFrete>30.00</vFrete>",
    )

    result = review_revenue_folder(folder, CFOP_SNAPSHOT, ANALYST_RULES)
    registro = result["_private_records"][0]

    assert registro["item_total"] == "100.00"
    assert registro["document_total"] == "130.00"
    assert result["totals"]["gross_revenue_goods"] == "130.00"
    itens = [
        json.loads(linha)
        for linha in (folder / "04_CONTEUDO" / "normalized-items.local.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if linha.strip()
    ]
    assert [item["gross_amount"] for item in itens] == ["100.00"]


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
