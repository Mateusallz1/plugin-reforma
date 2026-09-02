from __future__ import annotations

import json
from pathlib import Path

from fiscal_document_intake.acquisition import ACQUISITION_SCHEMA_VERSION
from fiscal_document_intake.cli import main
from fiscal_document_intake.content import CONTENT_SCHEMA_VERSION
from fiscal_document_intake.core import DOCUMENT_SCHEMA_VERSION
from fiscal_document_intake.counterparties import COUNTERPARTY_SCHEMA_VERSION
from fiscal_document_intake.credit_planning import (
    CREDIT_PLANNING_SCHEMA_VERSION,
    plan_credit_folder,
    write_credit_outputs,
)
from fiscal_document_intake.revenue import REVENUE_SCHEMA_VERSION
from fiscal_document_intake.simple_reconciliation import (
    SIMPLE_RECONCILIATION_SCHEMA_VERSION,
)

COMPANY = "12345678000195"
NORMAL_SUPPLIER = "98765432000198"
SIMPLE_SUPPLIER = "11222333000144"
NORMAL_CUSTOMER = "22333444000155"
SIMPLE_CUSTOMER = "33444555000166"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_inputs(
    folder: Path, *, pgdas: str = "1000.00", xml: str = "1000.00"
) -> None:
    _write_json(
        folder / "03_SAIDAS" / "validation-result.json",
        {
            "schema_version": DOCUMENT_SCHEMA_VERSION,
            "use_case": "UC-001",
            "validation_id": "VAL-SYNTHETIC",
            "gates": {"planning_authorized": True},
            "scope": {
                "entity_ref": "EMPRESA-SINTETICA",
                "establishment_ref": "ESTAB-SINTETICO",
                "period": "2026-03",
            },
        },
    )
    _write_json(
        folder / "04_CONTEUDO" / "content-summary.json",
        {
            "schema_version": CONTENT_SCHEMA_VERSION,
            "use_case": "UC-002",
            "content_analysis_id": "CNT-SYNTHETIC",
            "gates": {"uc003_analysis_authorized": True},
        },
    )
    _write_json(
        folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json",
        {
            "schema_version": ACQUISITION_SCHEMA_VERSION,
            "use_case": "UC-003",
            "phase": "ACQUISITION_REVIEW",
        },
    )
    _write_json(
        folder / "06_REVISAO_RECEITAS" / "revenue-summary.json",
        {
            "schema_version": REVENUE_SCHEMA_VERSION,
            "use_case": "UC-003",
            "phase": "REVENUE_REVIEW",
            "scope": {"period": "2026-03"},
            "totals": {"net_documentary_revenue_candidate": xml},
        },
    )
    _write_json(
        folder / "07_CONCILIACAO_SIMPLES" / "simple-reconciliation-summary.json",
        {
            "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
            "use_case": "UC-003C",
            "status": "SIMPLE_REVENUE_RECONCILED",
            "totals": {"pgdas_group_declared": pgdas},
            "gates": {"group_coverage_complete": True},
        },
    )
    suppliers = [
        {
            "schema": "counterparty",
            "schema_version": COUNTERPARTY_SCHEMA_VERSION,
            "role": "SUPPLIER",
            "party_type": "CNPJ",
            "cnpj": NORMAL_SUPPLIER,
            "name": "FORNECEDOR NORMAL",
            "name_cnpj": f"FORNECEDOR NORMAL + {NORMAL_SUPPLIER}",
            "competence": "2026-03",
            "simples_status": "NAO_OPTANTE_SIMPLES",
            "document_count": 1,
            "document_total": "100.00",
            "document_refs": ["DOC-NORMAL"],
        },
        {
            "schema": "counterparty",
            "schema_version": COUNTERPARTY_SCHEMA_VERSION,
            "role": "SUPPLIER",
            "party_type": "CNPJ",
            "cnpj": SIMPLE_SUPPLIER,
            "name": "FORNECEDOR SIMPLES",
            "name_cnpj": f"FORNECEDOR SIMPLES + {SIMPLE_SUPPLIER}",
            "competence": "2026-03",
            "simples_status": "OPTANTE_SIMPLES",
            "document_count": 1,
            "document_total": "200.00",
            "document_refs": ["DOC-SIMPLE"],
        },
    ]
    supplier_path = folder / "05_REVISAO_AQUISICOES" / "fornecedores-regime.local.jsonl"
    supplier_path.parent.mkdir(parents=True, exist_ok=True)
    supplier_path.write_text(
        "".join(json.dumps(row) + "\n" for row in suppliers), encoding="utf-8"
    )
    customers = [
        {
            "schema": "counterparty",
            "schema_version": COUNTERPARTY_SCHEMA_VERSION,
            "role": "CUSTOMER",
            "party_type": "CNPJ",
            "cnpj": NORMAL_CUSTOMER,
            "name": "CLIENTE NORMAL",
            "name_cnpj": f"CLIENTE NORMAL + {NORMAL_CUSTOMER}",
            "competence": "2026-03",
            "simples_status": "NAO_OPTANTE_SIMPLES",
            "document_count": 1,
            "document_total": "300.00",
        },
        {
            "schema": "counterparty",
            "schema_version": COUNTERPARTY_SCHEMA_VERSION,
            "role": "CUSTOMER",
            "party_type": "CNPJ",
            "cnpj": SIMPLE_CUSTOMER,
            "name": "CLIENTE SIMPLES",
            "name_cnpj": f"CLIENTE SIMPLES + {SIMPLE_CUSTOMER}",
            "competence": "2026-03",
            "simples_status": "OPTANTE_SIMPLES",
            "document_count": 1,
            "document_total": "200.00",
        },
    ]
    customer_path = folder / "06_REVISAO_RECEITAS" / "clientes-cnpj-regime.local.jsonl"
    customer_path.parent.mkdir(parents=True, exist_ok=True)
    customer_path.write_text(
        "".join(json.dumps(row) + "\n" for row in customers), encoding="utf-8"
    )
    items = [
        {
            "document_ref": "DOC-NORMAL",
            "direction": "ENTRADA",
            "record_kind": "PRODUCT",
            "eligible_for_uc003": True,
            "purchase_operation_status": "PURCHASE_CONTEXT",
            "nature_status": "ANALYST_APPROVED",
            "legal_evidence_status": "CONFIRMED_DECLARED",
            "gross_amount": "100.00",
        },
        {
            "document_ref": "DOC-SIMPLE",
            "direction": "ENTRADA",
            "record_kind": "PRODUCT",
            "eligible_for_uc003": True,
            "purchase_operation_status": "PURCHASE_CONTEXT",
            "nature_status": "ANALYST_APPROVED",
            "legal_evidence_status": "CONFIRMED_DECLARED",
            "gross_amount": "200.00",
        },
    ]
    items_path = folder / "05_REVISAO_AQUISICOES" / "acquisition-items.local.jsonl"
    items_path.write_text(
        "".join(json.dumps(item) + "\n" for item in items), encoding="utf-8"
    )
    _write_json(
        folder / "06_REVISAO_RECEITAS" / "clientes-cnpj-regime-summary.json",
        {
            "schema": "counterparty",
            "schema_version": COUNTERPARTY_SCHEMA_VERSION,
            "role": "CUSTOMER",
            "cnpj_customer_count": 2,
            "cnpj_by_simples_status": {},
            "sales_to_individuals": {"document_count": 0, "document_total": "0.00"},
            "registry_status": "LOADED",
        },
    )


def test_credit_planning_computes_cutoff_and_supplier_estimates(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "credit"
    _write_inputs(folder)

    result = plan_credit_folder(folder)

    assert result["schema_version"] == CREDIT_PLANNING_SCHEMA_VERSION
    assert result["customer_exposure"]["normal_customer_revenue"] == "300.00"
    assert result["customer_exposure"]["normal_customer_share"] == "30.0000"
    assert result["customer_exposure"]["threshold_amount"] == "200.00"
    assert result["customer_exposure"]["recommendation"] == "RECOMMEND_HYBRID_REVIEW"
    assert result["supplier_credit"]["creditable_base"] == "300.00"
    assert result["supplier_credit"]["estimated_credit"] == "11.00"

    written = write_credit_outputs(
        result, folder / "10_PLANEJAMENTO_CREDITOS", meeting_report=True
    )
    public = written[0].read_text(encoding="utf-8")
    local = written[1].read_text(encoding="utf-8")
    report = written[2].read_text(encoding="utf-8")
    assert NORMAL_SUPPLIER not in public
    assert NORMAL_SUPPLIER in local
    assert "FORNECEDOR NORMAL" in report
    assert main(["plan-credit-simulation", str(folder)]) == 0


def test_credit_planning_blocks_xml_above_pgdas(tmp_path: Path) -> None:
    folder = tmp_path / "xml-above-pgdas"
    _write_inputs(folder, pgdas="900.00", xml="1000.00")

    result = plan_credit_folder(folder)

    assert result["customer_exposure"]["xml_above_pgdas"] == "100.00"
    assert result["customer_exposure"]["recommendation"] == "PENDING_REVENUE_DIVERGENCE"


def test_credit_planning_names_and_taxes_pgdas_gap_as_revenue_without_invoice(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "revenue-without-invoice"
    _write_inputs(folder, pgdas="1200.00", xml="1000.00")

    result = plan_credit_folder(folder)

    exposure = result["customer_exposure"]
    assert exposure["revenue_without_invoice"] == "200.00"
    assert exposure["revenue_without_invoice_customer_assumption"] == "PESSOA_FISICA"
    assert exposure["revenue_without_invoice_tax_treatment"] == (
        "TRIBUTED_IN_PGDAS_SAME_WAY"
    )
    assert exposure["revenue_without_invoice_fiscal_benefit"] == "NONE"
    assert exposure["category_totals"]["RECEITA_SEM_NOTA_FISCAL"] == "200.00"


def test_credit_planning_requires_lookup_for_unknown_customer_regimes(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "unknown-customers"
    _write_inputs(folder)
    customer_path = folder / "06_REVISAO_RECEITAS" / "clientes-cnpj-regime.local.jsonl"
    customers = [
        {**json.loads(line), "simples_status": "UNKNOWN"}
        for line in customer_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    customer_path.write_text(
        "".join(json.dumps(row) + "\n" for row in customers), encoding="utf-8"
    )
    summary_path = folder / "06_REVISAO_RECEITAS" / "clientes-cnpj-regime-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["registry_status"] = "ABSENT"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = plan_credit_folder(folder)

    assert result["customer_exposure"]["unresolved_customer_regime_revenue"] == "500.00"
    assert (
        result["customer_exposure"]["recommendation"]
        == "PENDING_CUSTOMER_REGIME_LOOKUP"
    )


def test_credit_planning_does_not_estimate_mei_or_indeterminate_regimes(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "zero-rate-regimes"
    _write_inputs(folder)
    supplier_path = folder / "05_REVISAO_AQUISICOES" / "fornecedores-regime.local.jsonl"
    suppliers = [
        json.loads(line)
        for line in supplier_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    suppliers[0]["simples_status"] = "MEI"
    suppliers[1]["simples_status"] = "REGIME_INDETERMINADO"
    supplier_path.write_text(
        "".join(json.dumps(row) + "\n" for row in suppliers), encoding="utf-8"
    )

    result = plan_credit_folder(folder)

    assert result["supplier_credit"]["estimated_credit"] == "0.00"
    statuses = {
        row["simples_status"]: row["credit_status"]
        for row in result["_private_suppliers"]
    }
    assert statuses["MEI"] == "NO_ESTIMATE_SCENARIO_RATE_ZERO"
    assert statuses["REGIME_INDETERMINADO"] == "NO_ESTIMATE_REGIME_UNCONFIRMED"
