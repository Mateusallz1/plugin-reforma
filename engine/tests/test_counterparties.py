from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from fiscal_document_intake.cli import main
from fiscal_document_intake.content import extract_content_folder
from fiscal_document_intake.core import validate_folder, write_outputs
from fiscal_document_intake.counterparties import (
    SUPPLIER_PRODUCTS_LOCAL_FILE,
    SUPPLIER_PRODUCTS_REPORT_FILE,
    SUPPLIER_SUMMARY_FILE,
    _document_party_details,
    _document_regime_evidence,
    _generic_issuer_regime,
    _load_xml_contexts,
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
    assert "Documentos de entrada" in meeting_text
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


def test_counterparties_treat_mei_as_compatible_with_simples_registry(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "mei-registry", document_families=["NFE"])
    supplier_key = access_key(OTHER, "55", 133)
    supplier_xml = nfe_xml(
        supplier_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"
    ).replace("</emit>", "<CRT>4</CRT></emit>")
    (folder / "01_XML" / "supplier.xml").write_text(supplier_xml, encoding="utf-8")
    (folder / "00_CONTROLE" / "simples-registry.local.jsonl").write_text(
        json.dumps(
            {
                "cnpj": OTHER,
                "status": "OPTANTE_SIMPLES",
                "effective_from": "2026-01-01",
                "effective_to": "9999-12-31",
                "source": "RFB_SNAPSHOT",
                "verified_at": "2026-09-03",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _prepare(folder)

    result = review_counterparties_folder(folder)

    supplier = result["_private_suppliers"][0]
    assert supplier["document_regime_status"] == "MEI"
    assert supplier["simples_status"] == "MEI"
    assert "EVIDENCIA_CONFLITANTE" not in supplier["simples_status"]
    assert "RFB_SNAPSHOT" in supplier["evidence_sources"]
    assert (
        result["supplier_summary"]["by_simples_status"]["MEI"]["counterparty_count"]
        == 1
    )


def test_counterparties_generic_crt_is_scoped_to_document_key() -> None:
    root = ET.fromstring(
        """
        <root>
          <NFe><infNFe Id="NFe111"><emit><CRT>4</CRT></emit></infNFe></NFe>
          <NFe><infNFe Id="NFe222"><emit><CRT>3</CRT></emit></infNFe></NFe>
        </root>
        """
    )

    assert _generic_issuer_regime(root, "NFE", "111") == (
        "4",
        "DOCUMENT_CRT",
    )
    assert _generic_issuer_regime(root, "NFE", "222") == (
        "3",
        "DOCUMENT_CRT",
    )
    assert _generic_issuer_regime(root, "NFE") == (None, None)
    assert _generic_issuer_regime(root, "NFE", "999") == (None, None)


def test_counterparties_reuse_one_xml_parse_context(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "one.xml"
    path.write_text("<root />", encoding="utf-8")
    calls = 0

    def fake_parse_xml_file_with_root(candidate: Path):
        nonlocal calls
        calls += 1
        return ([{"document_ref": "DOC-1"}], None, None, ET.fromstring("<root />"))

    monkeypatch.setattr(
        "fiscal_document_intake.counterparties._xml_paths",
        lambda folder: [path],
    )
    monkeypatch.setattr(
        "fiscal_document_intake.counterparties._parse_xml_file_with_root",
        fake_parse_xml_file_with_root,
    )

    contexts = _load_xml_contexts(tmp_path)
    documents = {"DOC-1": {"document_ref": "DOC-1", "document_type": "NFE"}}

    _document_regime_evidence(contexts, documents)
    _document_party_details(contexts, documents)

    assert calls == 1


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


def test_counterparties_publish_supplier_product_mix_only_in_local_artifacts(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "product-mix", document_families=["NFE"])
    first_key = access_key(OTHER, "55", 127)
    second_key = access_key(OTHER, "55", 128)
    first_xml = nfe_xml(
        first_key, "55", OTHER, COMPANY, "2026-03-05", "150.00"
    ).replace("</emit>", "<CRT>1</CRT></emit>")
    second_xml = nfe_xml(
        second_key, "55", OTHER, COMPANY, "2026-03-06", "300.00"
    ).replace("</emit>", "<CRT>1</CRT></emit>")
    (folder / "01_XML" / "first.xml").write_text(first_xml, encoding="utf-8")
    (folder / "01_XML" / "second.xml").write_text(second_xml, encoding="utf-8")
    _prepare(folder)
    acquisition_dir = folder / "05_REVISAO_AQUISICOES"
    acquisition_dir.mkdir(exist_ok=True)
    items = [
        {
            "document_ref": "DOC-NOT-USED",
            "record_kind": "PRODUCT",
            "direction": "ENTRADA",
            "eligible_for_uc003": True,
            "purchase_operation_status": "PURCHASE_CONTEXT",
            "product_code": "1",
            "ncm": "01012100",
            "description": "ITEM A",
            "unit": "UN",
            "quantity": "2.0000",
            "gross_amount": "100.00",
        }
    ]
    first_ref = json.loads(
        (folder / "03_SAIDAS" / "validation-result.json").read_text(encoding="utf-8")
    )["documents"]["records"][0]["document_ref"]
    second_ref = json.loads(
        (folder / "03_SAIDAS" / "validation-result.json").read_text(encoding="utf-8")
    )["documents"]["records"][1]["document_ref"]
    items.extend(
        [
            {**items[0], "document_ref": first_ref, "gross_amount": "100.00"},
            {
                **items[0],
                "document_ref": first_ref,
                "product_code": "2",
                "description": "ITEM B",
                "quantity": "1.0000",
                "gross_amount": "50.00",
            },
            {**items[0], "document_ref": second_ref, "gross_amount": "300.00"},
        ]
    )
    acquisition_dir.joinpath("acquisition-items.local.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in items[1:]), encoding="utf-8"
    )

    result = review_counterparties_folder(folder)
    supplier = result["_private_supplier_products"][0]

    assert supplier["name_cnpj"].endswith(f" + {OTHER}")
    assert supplier["simples_status"] == "OPTANTE_SIMPLES"
    assert supplier["product_line_count"] == 3
    assert supplier["product_distinct_count"] == 2
    assert supplier["product_total"] == "450.00"
    assert supplier["share_of_portfolio_products"] == "100.0000"
    assert result["supplier_summary"]["product_mix"]["product_total"] == "450.00"

    written = write_counterparty_outputs(result, folder, meeting_report=True)
    product_local = folder / "05_REVISAO_AQUISICOES" / SUPPLIER_PRODUCTS_LOCAL_FILE
    product_report = folder / "09_APRESENTACAO_CLIENTE" / SUPPLIER_PRODUCTS_REPORT_FILE
    assert product_local in written
    assert product_report in written
    assert OTHER in product_local.read_text(encoding="utf-8")
    assert "ITEM A" in product_report.read_text(encoding="utf-8")
    public = (folder / "05_REVISAO_AQUISICOES" / SUPPLIER_SUMMARY_FILE).read_text(
        encoding="utf-8"
    )
    assert OTHER not in public
    assert "ITEM A" not in public


def test_counterparties_expose_distinct_supplier_amount_populations(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "amount-bases", document_families=["NFE"])
    first_key = access_key(OTHER, "55", 131)
    second_key = access_key(OTHER, "55", 132)
    (folder / "01_XML" / "first.xml").write_text(
        nfe_xml(first_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    (folder / "01_XML" / "second.xml").write_text(
        nfe_xml(second_key, "55", OTHER, COMPANY, "2026-03-06", "200.00"),
        encoding="utf-8",
    )
    _prepare(folder)
    acquisition_dir = folder / "05_REVISAO_AQUISICOES"
    acquisition_dir.mkdir(exist_ok=True)
    records = json.loads(
        (folder / "03_SAIDAS" / "validation-result.json").read_text(encoding="utf-8")
    )["documents"]["records"]
    items = [
        {
            "document_ref": records[0]["document_ref"],
            "direction": "ENTRADA",
            "purchase_operation_status": "PURCHASE_CONTEXT",
            "gross_amount": "100.00",
            "eligible_for_uc003": True,
        },
        {
            "document_ref": records[1]["document_ref"],
            "direction": "ENTRADA",
            "purchase_operation_status": "NON_PURCHASE_ENTRY",
            "gross_amount": "200.00",
            "eligible_for_uc003": True,
        },
    ]
    acquisition_dir.joinpath("acquisition-items.local.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in items), encoding="utf-8"
    )

    result = review_counterparties_folder(folder)

    assert result["supplier_summary"]["documentary_entries"] == {
        "amount_basis": "ALL_ENTRY_DOCUMENT_TOTAL",
        "document_count": 2,
        "document_total": "300.00",
    }
    assert result["supplier_summary"]["purchase_context_documents"] == {
        "amount_basis": "UNIQUE_DOCUMENT_TOTAL_PURCHASE_CONTEXT",
        "document_count": 1,
        "document_total": "100.00",
    }
    assert result["supplier_summary"]["purchase_context_items"] == {
        "amount_basis": "PURCHASE_CONTEXT_ITEM_SUBTOTAL",
        "item_count": 1,
        "item_total": "100.00",
        "eligible_item_count": 1,
        "eligible_item_total": "100.00",
    }


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
    assert supplier["document_regime_status"] == "OPTANTE_SIMPLES"
    assert supplier["simples_status"] == "OPTANTE_SIMPLES"


def test_counterparties_mark_missing_and_invalid_supplier_crt_as_indeterminate(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "indeterminate-crt", document_families=["NFE"])
    missing_key = access_key(OTHER, "55", 129)
    invalid_supplier = "11222333000144"
    invalid_key = access_key(invalid_supplier, "55", 130)
    (folder / "01_XML" / "missing.xml").write_text(
        nfe_xml(missing_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    (folder / "01_XML" / "invalid.xml").write_text(
        nfe_xml(
            invalid_key,
            "55",
            invalid_supplier,
            COMPANY,
            "2026-03-06",
            "200.00",
        ).replace("</emit>", "<CRT>9</CRT></emit>"),
        encoding="utf-8",
    )
    _prepare(folder)

    result = review_counterparties_folder(folder)
    suppliers = {
        supplier["cnpj"]: supplier for supplier in result["_private_suppliers"]
    }

    assert suppliers[OTHER]["document_regime_status"] == "REGIME_INDETERMINADO"
    assert suppliers[OTHER]["simples_status"] == "REGIME_INDETERMINADO"
    assert suppliers[OTHER]["crt_values"] == []
    assert (
        suppliers[invalid_supplier]["document_regime_status"] == "REGIME_INDETERMINADO"
    )
    assert suppliers[invalid_supplier]["simples_status"] == "REGIME_INDETERMINADO"
    assert suppliers[invalid_supplier]["crt_values"] == ["9"]
