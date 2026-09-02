from __future__ import annotations

import json
from pathlib import Path

from fiscal_document_intake.cli import main
from fiscal_document_intake.content import extract_content_folder
from fiscal_document_intake.core import validate_folder, write_outputs
from fiscal_document_intake.counterparties import (
    review_counterparties_folder,
    write_counterparty_outputs,
)
from test_uc001 import COMPANY, OTHER, access_key, make_folder, nfe_xml


def _prepare(folder: Path) -> None:
    validation = validate_folder(folder)
    assert validation["gates"]["planning_authorized"] is True
    write_outputs(validation, folder / "03_SAIDAS")
    content = extract_content_folder(folder)
    assert content["gates"]["uc003_analysis_authorized"] is True


def test_counterparties_separate_suppliers_cnpj_customers_and_cpf_sales(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "counterparties", document_families=["NFE"])
    supplier_key = access_key(OTHER, "55", 120)
    customer_key = access_key(COMPANY, "55", 121)
    cpf_key = access_key(COMPANY, "55", 122)
    supplier_xml = nfe_xml(
        supplier_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"
    ).replace("</emit>", "<CRT>1</CRT></emit>")
    customer_xml = nfe_xml(
        customer_key, "55", COMPANY, OTHER, "2026-03-06", "200.00"
    ).replace("</emit>", "<CRT>1</CRT></emit>")
    cpf_xml = nfe_xml(cpf_key, "55", COMPANY, "12345678901", "2026-03-07", "300.00")
    (folder / "01_XML" / "supplier.xml").write_text(supplier_xml, encoding="utf-8")
    (folder / "01_XML" / "customer.xml").write_text(customer_xml, encoding="utf-8")
    (folder / "01_XML" / "cpf.xml").write_text(cpf_xml, encoding="utf-8")
    _prepare(folder)

    result = review_counterparties_folder(folder)

    assert result["supplier_summary"]["by_simples_status"] == {
        "OPTANTE_SIMPLES": {
            "counterparty_count": 1,
            "document_count": 1,
            "document_total": "100.00",
        }
    }
    assert result["customer_summary"]["cnpj_by_simples_status"] == {
        "UNKNOWN": {
            "counterparty_count": 1,
            "document_count": 1,
            "document_total": "200.00",
        }
    }
    assert result["customer_summary"]["sales_to_individuals"] == {
        "document_count": 1,
        "document_total": "300.00",
    }
    assert result["_private_customers"][0]["evidence_sources"] == []

    written = write_counterparty_outputs(result, folder, meeting_report=True)
    supplier_local = next(
        path
        for path in written
        if path.name.endswith("regime.local.jsonl") and "fornecedores" in path.name
    )
    customer_local = next(
        path
        for path in written
        if path.name.endswith("regime.local.jsonl") and "clientes" in path.name
    )
    meeting = next(
        path for path in written if path.name == "contrapartes-regime.local.md"
    )
    public = "\n".join(
        path.read_text(encoding="utf-8")
        for path in written
        if path.name.endswith("summary.json")
    )
    assert OTHER in supplier_local.read_text(encoding="utf-8")
    assert OTHER in customer_local.read_text(encoding="utf-8")
    assert COMPANY not in public
    assert OTHER not in public
    assert "12345678901" not in public
    meeting_text = meeting.read_text(encoding="utf-8")
    assert OTHER in meeting_text
    assert "12345678901" not in meeting_text
    assert (
        json.loads(
            (
                folder / "05_REVISAO_AQUISICOES" / "fornecedores-regime-summary.json"
            ).read_text(encoding="utf-8")
        )["supplier_count"]
        == 1
    )
    assert main(["review-counterparties", str(folder)]) == 0


def test_counterparties_resolve_cnpj_customer_from_local_registry(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "registry", document_families=["NFE"])
    customer_id = "11122233000144"
    customer_key = access_key(COMPANY, "55", 123)
    customer_xml = nfe_xml(
        customer_key, "55", COMPANY, customer_id, "2026-03-06", "200.00"
    )
    (folder / "01_XML" / "customer.xml").write_text(customer_xml, encoding="utf-8")
    (folder / "00_CONTROLE" / "simples-registry.local.jsonl").write_text(
        json.dumps(
            {
                "cnpj": customer_id,
                "status": "OPTANTE_SIMPLES",
                "effective_from": "2026-01-01",
                "effective_to": "9999-12-31",
                "source": "RFB_SNAPSHOT",
                "verified_at": "2026-09-02",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _prepare(folder)

    result = review_counterparties_folder(folder)
    customer = result["_private_customers"][0]

    assert customer["simples_status"] == "OPTANTE_SIMPLES"
    assert "RFB_SNAPSHOT" in customer["evidence_sources"]


def test_counterparties_accept_batch_identity_without_period_scope(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "batch-identity", document_families=["NFE"])
    sale_key = access_key(COMPANY, "55", 126)
    sale_dir = folder / "01_XML" / "NFE" / "SAIDA"
    sale_dir.mkdir(parents=True)
    (sale_dir / "sale.xml").write_text(
        nfe_xml(sale_key, "55", COMPANY, OTHER, "2026-03-07", "300.00"),
        encoding="utf-8",
    )
    _prepare(folder)
    (folder / "00_CONTROLE" / "escopo.json").unlink()

    result = review_counterparties_folder(
        folder,
        scope_identity={
            "entity_ref": "EMPRESA-001",
            "establishment_ref": "ESTAB-001",
            "entity_taxpayer_ids": [COMPANY],
        },
    )

    assert result["customer_summary"]["sales_to_individuals"]["document_count"] == 0
    assert result["customer_summary"]["cnpj_customer_count"] == 1


def test_counterparties_preserve_distinct_crt_values_in_one_competence(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "crt-conflict", document_families=["NFE"])
    first_key = access_key(OTHER, "55", 124)
    second_key = access_key(OTHER, "55", 125)
    first_xml = nfe_xml(
        first_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"
    ).replace("</emit>", "<CRT>1</CRT></emit>")
    second_xml = nfe_xml(
        second_key, "55", OTHER, COMPANY, "2026-03-06", "200.00"
    ).replace("</emit>", "<CRT>2</CRT></emit>")
    (folder / "01_XML" / "first.xml").write_text(first_xml, encoding="utf-8")
    (folder / "01_XML" / "second.xml").write_text(second_xml, encoding="utf-8")
    _prepare(folder)

    result = review_counterparties_folder(folder)
    supplier = result["_private_suppliers"][0]

    assert supplier["crt_values"] == ["1", "2"]
    assert supplier["simples_status"] == "DIVERGENTE_NO_PERIODO"
