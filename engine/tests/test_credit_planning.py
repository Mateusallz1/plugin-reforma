from __future__ import annotations

import json
from pathlib import Path

import pytest
from fiscal_document_intake.acquisition import ACQUISITION_SCHEMA_VERSION
from fiscal_document_intake.cli import main
from fiscal_document_intake.content import CONTENT_SCHEMA_VERSION
from fiscal_document_intake.core import DOCUMENT_SCHEMA_VERSION, ValidationError
from fiscal_document_intake.counterparties import COUNTERPARTY_SCHEMA_VERSION
from fiscal_document_intake.credit_planning import (
    CREDIT_PLANNING_SCHEMA_VERSION,
    plan_credit_folder,
    plan_credit_portfolio,
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
    folder: Path,
    *,
    pgdas: str = "1000.00",
    xml: str = "1000.00",
    period: str = "2026-03",
    establishment_ref: str = "ESTAB-SINTETICO",
    entity_ref: str = "EMPRESA-SINTETICA",
    reviewed_documents: int | None = None,
) -> None:
    _write_json(
        folder / "03_SAIDAS" / "validation-result.json",
        {
            "schema_version": DOCUMENT_SCHEMA_VERSION,
            "use_case": "UC-001",
            "validation_id": "VAL-SYNTHETIC",
            "gates": {"planning_authorized": True},
            "scope": {
                "entity_ref": entity_ref,
                "establishment_ref": establishment_ref,
                "period": period,
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
            "gates": {"simulation_authorized": True},
        },
    )
    _write_json(
        folder / "06_REVISAO_RECEITAS" / "revenue-summary.json",
        {
            "schema_version": REVENUE_SCHEMA_VERSION,
            "use_case": "UC-003",
            "phase": "REVENUE_REVIEW",
            "scope": {
                "entity_ref": entity_ref,
                "establishment_ref": establishment_ref,
                "period": period,
            },
            "totals": {"net_documentary_revenue_candidate": xml},
            "gates": {
                "revenue_population_ready": True,
                "simulation_authorized": True,
            },
        },
    )
    if reviewed_documents is not None:
        revenue_summary = json.loads(
            (folder / "06_REVISAO_RECEITAS" / "revenue-summary.json").read_text(
                encoding="utf-8"
            )
        )
        revenue_summary["reviewed_documents"] = reviewed_documents
        _write_json(
            folder / "06_REVISAO_RECEITAS" / "revenue-summary.json", revenue_summary
        )
    _write_json(
        folder / "07_CONCILIACAO_SIMPLES" / "simple-reconciliation-summary.json",
        {
            "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
            "use_case": "UC-003C",
            "status": "SIMPLE_REVENUE_RECONCILED",
            "totals": {
                "pgdas_group_declared": pgdas,
                "pgdas_matched_establishment": pgdas,
                "documentary_matched_establishment": xml,
            },
            "gates": {
                "group_coverage_complete": True,
                "documentary_scope_reconciled": True,
                "simulation_authorized": True,
            },
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
    assert result["gates"]["simulation_authorized"] is True
    assert result["gates"]["uc004_planning_authorized"] is False
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
    assert "Base total `PURCHASE_CONTEXT` por itens: 300.00" in report
    assert "Base pendente elegível: 0.00" in report
    assert main(["plan-credit-simulation", str(folder)]) == 0


@pytest.mark.parametrize(
    "relative_path",
    [
        "05_REVISAO_AQUISICOES/acquisition-summary.json",
        "06_REVISAO_RECEITAS/revenue-summary.json",
        "07_CONCILIACAO_SIMPLES/simple-reconciliation-summary.json",
    ],
)
def test_credit_planning_consumes_simulation_authorization_gate(
    tmp_path: Path,
    relative_path: str,
) -> None:
    folder = tmp_path / "simulation-gate"
    _write_inputs(folder)
    summary_path = folder / relative_path
    summary = json.loads(summary_path.read_text())
    summary["gates"]["simulation_authorized"] = False
    _write_json(summary_path, summary)

    with pytest.raises(ValidationError, match="não autorizou a simulação"):
        plan_credit_folder(folder)


def test_credit_planning_labels_purchase_populations_separately(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "amount-bases"
    _write_inputs(folder)
    acquisition_summary_path = (
        folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json"
    )
    acquisition_summary = json.loads(acquisition_summary_path.read_text())
    acquisition_summary["documentary_totals"] = {
        "gross_documentary_purchases": "200.00",
        "non_purchase_entry_operations": "100.00",
    }
    acquisition_summary_path.write_text(json.dumps(acquisition_summary))
    items_path = folder / "05_REVISAO_AQUISICOES" / "acquisition-items.local.jsonl"
    items = [json.loads(line) for line in items_path.read_text().splitlines()]
    items[0]["purchase_operation_status"] = "NON_PURCHASE_ENTRY"
    items[1]["eligible_for_uc003"] = False
    items_path.write_text("".join(json.dumps(item) + "\n" for item in items))

    result = plan_credit_folder(folder)
    supplier_credit = result["supplier_credit"]

    assert supplier_credit["documentary_purchase_total"] == "200.00"
    assert supplier_credit["documentary_purchase_amount_basis"] == (
        "UNIQUE_DOCUMENT_TOTAL"
    )
    assert supplier_credit["purchase_base"] == "200.00"
    assert supplier_credit["purchase_base_amount_basis"] == (
        "PURCHASE_CONTEXT_ITEM_SUBTOTAL"
    )
    assert supplier_credit["pending_base"] == "0.00"
    assert supplier_credit["pending_base_amount_basis"] == (
        "PURCHASE_CONTEXT_ELIGIBLE_PENDING_ITEM_SUBTOTAL"
    )
    assert supplier_credit["non_purchase_entry_total"] == "100.00"
    assert "non_purchase_entry_base" not in supplier_credit
    assert supplier_credit["ineligible_purchase_context_base"] == "200.00"


def test_credit_planning_preserves_fractional_scenario_rates(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "fractional-rates"
    _write_inputs(folder)
    scenario_path = tmp_path / "scenario.json"
    _write_json(
        scenario_path,
        {
            "scenario_id": "ANALYST-FRACTIONAL-RATES",
            "mode": "SIMULATION_ONLY",
            "rates": {
                "NAO_OPTANTE_SIMPLES": "0.0875",
                "OPTANTE_SIMPLES": "0.265",
            },
        },
    )

    result = plan_credit_folder(folder, scenario_path=scenario_path)

    assert result["scenario"]["rates"] == {
        "NAO_OPTANTE_SIMPLES": "0.0875",
        "OPTANTE_SIMPLES": "0.265",
    }
    rows = {row["simples_status"]: row for row in result["_private_suppliers"]}
    assert rows["NAO_OPTANTE_SIMPLES"]["scenario_rate"] == "0.0875"
    assert rows["NAO_OPTANTE_SIMPLES"]["scenario_rate_percent"] == "8.7500"
    assert rows["NAO_OPTANTE_SIMPLES"]["estimated_credit"] == "8.75"
    assert rows["OPTANTE_SIMPLES"]["scenario_rate"] == "0.265"
    assert rows["OPTANTE_SIMPLES"]["scenario_rate_percent"] == "26.500"
    assert rows["OPTANTE_SIMPLES"]["estimated_credit"] == "53.00"
    assert result["supplier_credit"]["estimated_credit"] == "61.75"


def test_credit_planning_rejects_unknown_scenario_rate_status(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "unknown-rate-status"
    _write_inputs(folder)
    scenario_path = tmp_path / "scenario.json"
    _write_json(
        scenario_path,
        {
            "scenario_id": "ANALYST-UNKNOWN-RATE-STATUS",
            "mode": "SIMULATION_ONLY",
            "rates": {"NAO_OPTATE_SIMPLES": "0.09"},
        },
    )

    with pytest.raises(ValidationError, match="status de taxa desconhecido"):
        plan_credit_folder(folder, scenario_path=scenario_path)


def test_credit_planning_rejects_missing_supplier_rate(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "missing-supplier-rate"
    _write_inputs(folder)
    scenario_path = tmp_path / "scenario.json"
    _write_json(
        scenario_path,
        {
            "scenario_id": "ANALYST-MISSING-SUPPLIER-RATE",
            "mode": "SIMULATION_ONLY",
            "rates": {"OPTANTE_SIMPLES": "0.01"},
        },
    )

    with pytest.raises(ValidationError, match="não possui taxa"):
        plan_credit_folder(folder, scenario_path=scenario_path)


def test_credit_planning_blocks_xml_above_pgdas(tmp_path: Path) -> None:
    folder = tmp_path / "xml-above-pgdas"
    _write_inputs(folder, pgdas="900.00", xml="1000.00")

    result = plan_credit_folder(folder)

    assert result["customer_exposure"]["xml_above_pgdas"] == "100.00"
    assert result["customer_exposure"]["recommendation"] == "PENDING_REVENUE_DIVERGENCE"


@pytest.mark.parametrize("declared", ["15778.00", "7241.20"])
def test_credit_planning_marks_missing_document_support_without_customer_inference(
    tmp_path: Path,
    declared: str,
) -> None:
    folder = tmp_path / "missing-document-support"
    _write_inputs(folder, pgdas=declared, xml="0.00", reviewed_documents=0)

    result = plan_credit_folder(folder)

    exposure = result["customer_exposure"]
    assert exposure["pgdas_revenue"] == declared
    assert exposure["documentary_revenue"] == "0.00"
    assert exposure["revenue_without_invoice"] == declared
    assert exposure["revenue_without_invoice_status"] == (
        "ESTABLISHMENT_DOCUMENTS_MISSING"
    )
    assert exposure["revenue_without_invoice_customer_assumption"] == "NONE"
    assert exposure["revenue_without_invoice_tax_treatment"] == "NOT_APPLICABLE"
    assert exposure["revenue_without_invoice_fiscal_benefit"] == "NOT_APPLICABLE"
    assert exposure["category_totals"]["ESTABLISHMENT_DOCUMENTS_MISSING"] == declared
    assert exposure["category_totals"]["PESSOA_FISICA_DOCUMENTADA"] == "0.00"
    assert exposure["recommendation"] == "PENDING_DOCUMENTARY_COVERAGE"


def test_credit_planning_single_establishment_portfolio_uses_period_reconciliation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "portfolio"
    _write_inputs(
        root / "MATRIZ" / "01-2026",
        period="2026-01",
    )
    _write_inputs(
        root / "MATRIZ" / "02-2026",
        period="2026-02",
    )

    result = plan_credit_portfolio(root)

    assert len(result["periods"]) == 2
    assert result["scope"]["periods"] == ["2026-01", "2026-02"]
    assert result["gates"]["period_count"] == 2
    assert result["gates"]["simulation_authorized"] is True
    assert result["gates"]["uc004_planning_authorized"] is False
    assert result["supplier_credit"]["purchase_base"] == "600.00"
    assert result["supplier_credit"]["purchase_base_amount_basis"] == (
        "PURCHASE_CONTEXT_ITEM_SUBTOTAL"
    )
    assert all(period["gates"]["pgdas_reconciled"] for period in result["periods"])
    assert all(period["gates"]["group_consolidated"] for period in result["periods"])
    assert (
        result["customer_exposure"]["recommendation"] != "PENDING_GROUP_CONSOLIDATION"
    )


def test_credit_planning_portfolio_preserves_both_reconciliation_directions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "portfolio"
    _write_inputs(
        root / "MATRIZ" / "01-2026",
        pgdas="900.00",
        xml="1000.00",
        period="2026-01",
    )
    _write_inputs(
        root / "MATRIZ" / "02-2026",
        pgdas="1200.00",
        xml="1100.00",
        period="2026-02",
    )

    result = plan_credit_portfolio(root)

    assert result["customer_exposure"]["revenue_without_invoice"] == "100.00"
    assert result["customer_exposure"]["xml_above_pgdas"] == "100.00"


def test_credit_planning_portfolio_keeps_establishment_pgdas_values_separate(
    tmp_path: Path,
) -> None:
    root = tmp_path / "portfolio"
    _write_inputs(
        root / "MATRIZ" / "01-2026",
        pgdas="200.00",
        xml="200.00",
        period="2026-01",
        establishment_ref="ESTAB-MATRIX",
        reviewed_documents=1,
    )
    _write_inputs(
        root / "FILIAL" / "01-2026",
        pgdas="100.00",
        xml="0.00",
        period="2026-01",
        establishment_ref="ESTAB-BRANCH",
        reviewed_documents=0,
    )
    _write_json(
        root
        / ".reforma-tributaria"
        / "conciliacoes-simples-grupo"
        / "2026-01"
        / "simple-reconciliation-summary.json",
        {
            "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
            "use_case": "UC-003C",
            "status": "SIMPLE_REVENUE_REVIEW_REQUIRED",
            "totals": {"pgdas_group_declared": "300.00"},
            "gates": {
                "group_coverage_complete": True,
                "documentary_scope_reconciled": True,
                "simulation_authorized": True,
            },
        },
    )

    result = plan_credit_portfolio(root)

    periods = {item["establishment_ref"]: item for item in result["periods"]}
    assert periods["ESTAB-MATRIX"]["customer_exposure"]["pgdas_revenue"] == "200.00"
    assert periods["ESTAB-BRANCH"]["customer_exposure"]["pgdas_revenue"] == "100.00"
    assert (
        periods["ESTAB-BRANCH"]["customer_exposure"]["revenue_without_invoice_status"]
        == "ESTABLISHMENT_DOCUMENTS_MISSING"
    )
    assert result["customer_exposure"]["pgdas_revenue"] == "300.00"
    assert result["customer_exposure"]["documentary_revenue"] == "200.00"
    assert result["customer_exposure"]["revenue_without_invoice"] == "100.00"
    assert result["customer_exposure"][
        "revenue_without_invoice_customer_assumption"
    ] == ("NONE")
    assert (
        result["customer_exposure"]["category_totals"][
            "ESTABLISHMENT_DOCUMENTS_MISSING"
        ]
        == "100.00"
    )


def test_credit_planning_skips_group_scope_from_establishment_rollup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "portfolio"
    matrix = root / "MATRIZ" / "01-2026"
    branch = root / "FILIAL" / "01-2026"
    _write_inputs(
        matrix,
        pgdas="200.00",
        xml="200.00",
        period="2026-01",
        establishment_ref="ESTAB-MATRIX",
    )
    _write_inputs(
        branch,
        pgdas="100.00",
        xml="0.00",
        period="2026-01",
        establishment_ref="ESTAB-BRANCH",
    )
    (branch / "07_CONCILIACAO_SIMPLES" / "simple-reconciliation-summary.json").unlink()
    _write_json(
        root
        / ".reforma-tributaria"
        / "conciliacoes-simples-grupo"
        / "2026-01"
        / "simple-reconciliation-summary.json",
        {
            "schema_version": SIMPLE_RECONCILIATION_SCHEMA_VERSION,
            "use_case": "UC-003C",
            "status": "SIMPLE_REVENUE_REVIEW_REQUIRED",
            "totals": {"pgdas_group_declared": "300.00"},
            "gates": {
                "group_coverage_complete": True,
                "documentary_scope_reconciled": True,
                "simulation_authorized": True,
            },
        },
    )

    result = plan_credit_portfolio(root)

    periods = {item["establishment_ref"]: item for item in result["periods"]}
    assert periods["ESTAB-MATRIX"]["customer_exposure"]["reconciliation_mode"] == (
        "ESTABLISHMENT"
    )
    assert periods["ESTAB-BRANCH"]["customer_exposure"]["reconciliation_mode"] == (
        "GROUP"
    )
    assert result["customer_exposure"]["pgdas_revenue"] == "0.00"
    assert result["customer_exposure"]["documentary_revenue"] == "0.00"
    assert result["customer_exposure"]["revenue_without_invoice"] == "0.00"
    assert result["customer_exposure"]["reconciliation_rollup_status"] == "PARTIAL"
    assert result["customer_exposure"]["reconciliation_rollup_skipped_periods"] == [
        "2026-01"
    ]


def test_credit_planning_group_consolidated_requires_documentary_reconciliation(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "group-not-reconciled"
    _write_inputs(folder)
    reconciliation_path = (
        folder / "07_CONCILIACAO_SIMPLES" / "simple-reconciliation-summary.json"
    )
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation["gates"]["documentary_scope_reconciled"] = False
    _write_json(reconciliation_path, reconciliation)

    result = plan_credit_folder(folder)

    assert result["gates"]["pgdas_reconciled"] is True
    assert result["gates"]["group_consolidated"] is False


def test_credit_planning_names_and_taxes_pgdas_gap_as_revenue_without_invoice(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "revenue-without-invoice"
    _write_inputs(folder, pgdas="1200.00", xml="1000.00")

    result = plan_credit_folder(folder)

    exposure = result["customer_exposure"]
    assert exposure["revenue_without_invoice"] == "200.00"
    assert exposure["revenue_without_invoice_customer_assumption"] == "NONE"
    assert exposure["revenue_without_invoice_status"] == (
        "DECLARED_WITHOUT_DOCUMENT_SUPPORT"
    )
    assert exposure["revenue_without_invoice_tax_treatment"] == (
        "TRIBUTED_IN_PGDAS_SAME_WAY"
    )
    assert exposure["revenue_without_invoice_fiscal_benefit"] == "NONE"
    assert exposure["category_totals"]["DECLARED_WITHOUT_DOCUMENT_SUPPORT"] == "200.00"


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
