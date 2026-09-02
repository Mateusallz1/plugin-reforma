from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .acquisition import ACQUISITION_SCHEMA_VERSION
from .content import CONTENT_SCHEMA_VERSION
from .core import DOCUMENT_SCHEMA_VERSION, ValidationError
from .revenue import REVENUE_SCHEMA_VERSION
from .simple_reconciliation import SIMPLE_RECONCILIATION_SCHEMA_VERSION

CREDIT_PLANNING_SCHEMA = (
    "br.com.planejamento-reforma-tributaria/credit-planning-simulation"
)
CREDIT_PLANNING_SCHEMA_VERSION = "1.1.0"
DEFAULT_SCENARIO = {
    "scenario_id": "ANALYST_RATES_9_1_V1",
    "mode": "SIMULATION_ONLY",
    "rates": {
        "NAO_OPTANTE_SIMPLES": "0.0900",
        "OPTANTE_SIMPLES": "0.0100",
        "MEI": "0.0000",
        "NANOEMPREENDEDOR": "0.0000",
        "PESSOA_FISICA": "0.0000",
        "REGIME_INDETERMINADO": "0.0000",
        "DIVERGENTE_NO_PERIODO": "0.0000",
        "UNKNOWN": "0.0000",
    },
}
NON_DEMANDING_CUSTOMER_STATUSES = {
    "OPTANTE_SIMPLES",
    "MEI",
    "NANOEMPREENDEDOR",
    "PESSOA_FISICA",
    "REGIME_INDETERMINADO",
    "DIVERGENTE_NO_PERIODO",
    "UNKNOWN",
}
NON_DEMANDING_CUSTOMER_CATEGORIES = {
    "CONDOMINIO",
    "CONDOMINIUM",
    "ORGAO_PUBLICO",
    "PUBLIC_ENTITY",
    "GOVERNO",
    "GOVERNMENT",
}


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"Planejamento de crédito exige {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} deve ser JSON UTF-8 válido") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} deve conter um objeto JSON")
    return value


def _load_jsonl(path: Path, *, optional: bool = False) -> list[dict[str, Any]]:
    if not path.is_file():
        if optional:
            return []
        raise ValidationError(f"Planejamento de crédito exige {path.name}")
    records: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), start=1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValidationError(
                    f"{path.name} possui linha inválida: {line_number}"
                )
            records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{path.name} deve ser JSONL UTF-8 válido") from error
    return records


def _decimal(value: Any) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal(0)
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as error:
        raise ValidationError(f"Valor decimal inválido: {value}") from error


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _quantity(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def _percent(value: Decimal, total: Decimal) -> str:
    if total == 0:
        return "0.0000"
    return format((value * Decimal(100) / total).quantize(Decimal("0.0001")), "f")


def _read_scenario(path: Path | str | None) -> dict[str, Any]:
    if path is None:
        return DEFAULT_SCENARIO
    scenario = _load_json(Path(path).expanduser().resolve(), "scenario de crédito")
    rates = scenario.get("rates")
    if (
        scenario.get("mode") != "SIMULATION_ONLY"
        or not isinstance(scenario.get("scenario_id"), str)
        or not isinstance(rates, dict)
    ):
        raise ValidationError(
            "O cenário de crédito deve ser SIMULATION_ONLY, possuir scenario_id e rates"
        )
    normalized_rates: dict[str, str] = {}
    for status, rate in rates.items():
        normalized_rates[str(status)] = _money(_decimal(rate))
    return {**scenario, "rates": normalized_rates}


def _period_folders(root: Path) -> list[Path]:
    if (root / "03_SAIDAS" / "validation-result.json").is_file():
        return [root]
    folders = {
        path.parent.parent
        for path in root.rglob("03_SAIDAS/validation-result.json")
        if path.is_file()
    }
    return sorted(folders, key=lambda item: str(item).casefold())


def _load_period_inputs(folder: Path) -> dict[str, Any]:
    validation = _load_json(
        folder / "03_SAIDAS" / "validation-result.json",
        "03_SAIDAS/validation-result.json",
    )
    content = _load_json(
        folder / "04_CONTEUDO" / "content-summary.json",
        "04_CONTEUDO/content-summary.json",
    )
    acquisition = _load_json(
        folder / "05_REVISAO_AQUISICOES" / "acquisition-summary.json",
        "05_REVISAO_AQUISICOES/acquisition-summary.json",
    )
    revenue = _load_json(
        folder / "06_REVISAO_RECEITAS" / "revenue-summary.json",
        "06_REVISAO_RECEITAS/revenue-summary.json",
    )
    supplier_rows = _load_jsonl(
        folder / "05_REVISAO_AQUISICOES" / "fornecedores-regime.local.jsonl"
    )
    customer_rows = _load_jsonl(
        folder / "06_REVISAO_RECEITAS" / "clientes-cnpj-regime.local.jsonl"
    )
    acquisition_items = _load_jsonl(
        folder / "05_REVISAO_AQUISICOES" / "acquisition-items.local.jsonl"
    )
    versions = {
        "validation": (validation, DOCUMENT_SCHEMA_VERSION),
        "content": (content, CONTENT_SCHEMA_VERSION),
        "acquisition": (acquisition, ACQUISITION_SCHEMA_VERSION),
        "revenue": (revenue, REVENUE_SCHEMA_VERSION),
    }
    for label, (value, expected) in versions.items():
        if value.get("schema_version") != expected:
            raise ValidationError(f"Saída {label} não pertence à versão vigente")
    if validation.get("use_case") != "UC-001" or not validation.get("gates", {}).get(
        "planning_authorized"
    ):
        raise ValidationError("UC-001 não autorizou o planejamento de crédito")
    if content.get("gates", {}).get("uc003_analysis_authorized") is not True:
        raise ValidationError("UC-002 não autorizou a revisão de aquisições")
    if acquisition.get("use_case") != "UC-003" or revenue.get("use_case") != "UC-003":
        raise ValidationError("Saídas de aquisições e receitas não pertencem ao UC-003")
    period = str(validation.get("scope", {}).get("period") or "")
    if not period:
        raise ValidationError("A competência não foi informada no escopo")
    return {
        "folder": folder,
        "period": period,
        "validation": validation,
        "content": content,
        "acquisition": acquisition,
        "revenue": revenue,
        "supplier_rows": supplier_rows,
        "customer_rows": customer_rows,
        "acquisition_items": acquisition_items,
    }


def _reconciliation_for_period(
    folder: Path, portfolio_root: Path | None, period: str
) -> tuple[dict[str, Any] | None, str]:
    is_multi_establishment_portfolio = bool(
        portfolio_root is not None and len(_period_folders(portfolio_root)) > 1
    )
    candidates: list[tuple[Path, str]] = []
    if portfolio_root is not None:
        candidates.append(
            (
                portfolio_root
                / ".reforma-tributaria"
                / "conciliacoes-simples-grupo"
                / period
                / "simple-reconciliation-summary.json",
                "GROUP",
            )
        )
    if not is_multi_establishment_portfolio:
        candidates.append(
            (
                folder
                / "07_CONCILIACAO_SIMPLES"
                / "simple-reconciliation-summary.json",
                "ESTABLISHMENT",
            )
        )
    for path, mode in candidates:
        if path.is_file():
            summary = _load_json(path, path.name)
            if summary.get("schema_version") != SIMPLE_RECONCILIATION_SCHEMA_VERSION:
                raise ValidationError(
                    "A conciliação do PGDAS-D não pertence à versão vigente"
                )
            return summary, mode
    return None, "GROUP_MISSING" if is_multi_establishment_portfolio else "MISSING"


def _customer_profile(row: dict[str, Any]) -> str:
    category = str(row.get("entity_category") or "").strip().upper()
    if category in NON_DEMANDING_CUSTOMER_CATEGORIES:
        return category
    status = str(row.get("simples_status") or "UNKNOWN").strip().upper()
    if status in NON_DEMANDING_CUSTOMER_STATUSES:
        return status
    if status == "NAO_OPTANTE_SIMPLES":
        return "REGIME_NORMAL"
    return "REGIME_INDETERMINADO"


def _supplier_credit_rows(
    inputs: dict[str, Any], scenario: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    supplier_by_document: dict[str, dict[str, Any]] = {}
    for supplier in inputs["supplier_rows"]:
        for document_ref in supplier.get("document_refs", []):
            supplier_by_document[str(document_ref)] = supplier
    grouped: dict[str, dict[str, Any]] = {}
    for item in inputs["acquisition_items"]:
        if item.get("direction") != "ENTRADA":
            continue
        supplier = supplier_by_document.get(str(item.get("document_ref")))
        if supplier is None:
            continue
        cnpj = str(supplier.get("cnpj") or "")
        entry = grouped.setdefault(
            cnpj,
            {
                "supplier": supplier,
                "purchase_base": Decimal(0),
                "creditable_base": Decimal(0),
                "pending_base": Decimal(0),
                "excluded_base": Decimal(0),
                "item_count": 0,
            },
        )
        amount = _decimal(item.get("gross_amount"))
        if item.get("purchase_operation_status") != "PURCHASE_CONTEXT":
            entry["excluded_base"] += amount
            continue
        entry["purchase_base"] += amount
        entry["item_count"] += 1
        if item.get("eligible_for_uc003") is not True:
            entry["excluded_base"] += amount
        elif (
            item.get("nature_status") != "ANALYST_APPROVED"
            or item.get("legal_evidence_status") != "CONFIRMED_DECLARED"
        ):
            entry["pending_base"] += amount
        else:
            entry["creditable_base"] += amount

    rows: list[dict[str, Any]] = []
    by_status: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "supplier_count": 0,
            "supplier_count_with_creditable_base": 0,
            "purchase_base": Decimal(0),
            "creditable_base": Decimal(0),
            "pending_base": Decimal(0),
            "estimated_credit": Decimal(0),
        }
    )
    for entry in sorted(
        grouped.values(), key=lambda value: str(value["supplier"].get("cnpj"))
    ):
        supplier = entry["supplier"]
        status = str(supplier.get("simples_status") or "REGIME_INDETERMINADO")
        rate = _decimal(scenario["rates"].get(status, "0.00"))
        creditable = entry["creditable_base"]
        estimated = creditable * rate
        if status in {"REGIME_INDETERMINADO", "UNKNOWN", "DIVERGENTE_NO_PERIODO"}:
            credit_status = "NO_ESTIMATE_REGIME_UNCONFIRMED"
        elif entry["pending_base"] > 0:
            credit_status = "PENDING_OPERATIONAL_EVIDENCE"
        elif rate == 0:
            credit_status = "NO_ESTIMATE_SCENARIO_RATE_ZERO"
        else:
            credit_status = "ESTIMATED_WITH_ANALYST_SCENARIO"
        row = {
            "schema": CREDIT_PLANNING_SCHEMA,
            "schema_version": CREDIT_PLANNING_SCHEMA_VERSION,
            "role": "SUPPLIER_CREDIT_SIMULATION",
            "party_type": "CNPJ",
            "cnpj": supplier.get("cnpj"),
            "name": supplier.get("name"),
            "name_cnpj": supplier.get("name_cnpj"),
            "competence": inputs["period"],
            "simples_status": status,
            "document_count": supplier.get("document_count", 0),
            "purchase_base": _money(entry["purchase_base"]),
            "creditable_base": _money(creditable),
            "pending_base": _money(entry["pending_base"]),
            "excluded_base": _money(entry["excluded_base"]),
            "scenario_rate": _money(rate),
            "scenario_rate_percent": _money(rate * Decimal(100)),
            "estimated_credit": _money(estimated),
            "credit_status": credit_status,
            "item_count": entry["item_count"],
        }
        rows.append(row)
        summary = by_status[status]
        summary["supplier_count"] += 1
        summary["supplier_count_with_creditable_base"] += int(creditable > 0)
        summary["purchase_base"] += entry["purchase_base"]
        summary["creditable_base"] += creditable
        summary["pending_base"] += entry["pending_base"]
        summary["estimated_credit"] += estimated
    public_summary = {
        "by_supplier_regime": {
            status: {
                **values,
                "purchase_base": _money(values["purchase_base"]),
                "creditable_base": _money(values["creditable_base"]),
                "pending_base": _money(values["pending_base"]),
                "estimated_credit": _money(values["estimated_credit"]),
            }
            for status, values in sorted(by_status.items())
        },
        "supplier_count": len(rows),
        "purchase_base": _money(
            sum((_decimal(row["purchase_base"]) for row in rows), Decimal(0))
        ),
        "creditable_base": _money(
            sum((_decimal(row["creditable_base"]) for row in rows), Decimal(0))
        ),
        "pending_base": _money(
            sum((_decimal(row["pending_base"]) for row in rows), Decimal(0))
        ),
        "estimated_credit": _money(
            sum((_decimal(row["estimated_credit"]) for row in rows), Decimal(0))
        ),
    }
    return rows, public_summary


def _customer_exposure(
    inputs: dict[str, Any],
    reconciliation: dict[str, Any] | None,
    reconciliation_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normal_revenue = Decimal(0)
    category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    rows: list[dict[str, Any]] = []
    for customer in inputs["customer_rows"]:
        category = _customer_profile(customer)
        amount = _decimal(customer.get("document_total"))
        category_totals[category] += amount
        if category == "REGIME_NORMAL":
            normal_revenue += amount
        rows.append(
            {
                "schema": CREDIT_PLANNING_SCHEMA,
                "schema_version": CREDIT_PLANNING_SCHEMA_VERSION,
                "role": "CUSTOMER_CREDIT_EXPOSURE",
                "party_type": "CNPJ",
                "cnpj": customer.get("cnpj"),
                "name": customer.get("name"),
                "name_cnpj": customer.get("name_cnpj"),
                "competence": inputs["period"],
                "simples_status": customer.get("simples_status"),
                "customer_profile": category,
                "document_count": customer.get("document_count", 0),
                "document_total": customer.get("document_total", "0.00"),
                "credit_demand": category == "REGIME_NORMAL",
            }
        )
    cpf_total = Decimal(0)
    customer_registry_status = str(
        inputs.get("customer_summary", {}).get("registry_status") or "ABSENT"
    )
    unresolved_customer_regime_revenue = Decimal(0)
    if inputs.get("customer_summary"):
        cpf_total = _decimal(
            inputs["customer_summary"]
            .get("sales_to_individuals", {})
            .get("document_total")
        )
    if customer_registry_status != "LOADED":
        unresolved_customer_regime_revenue = sum(
            (
                _decimal(customer.get("document_total"))
                for customer in inputs["customer_rows"]
                if _customer_profile(customer)
                in {"UNKNOWN", "REGIME_INDETERMINADO", "DIVERGENTE_NO_PERIODO"}
            ),
            Decimal(0),
        )
    if reconciliation is None:
        pgdas_revenue = Decimal(0)
        documentary_revenue = _decimal(
            inputs["revenue"].get("totals", {}).get("net_documentary_revenue_candidate")
        )
        uncovered = Decimal(0)
        xml_excess = Decimal(0)
        reconciliation_status = reconciliation_mode
        group_complete = False
    else:
        pgdas_revenue = _decimal(
            reconciliation.get("totals", {}).get("pgdas_group_declared")
        )
        documentary_revenue = _decimal(
            inputs["revenue"].get("totals", {}).get("net_documentary_revenue_candidate")
        )
        uncovered = max(pgdas_revenue - documentary_revenue, Decimal(0))
        xml_excess = max(documentary_revenue - pgdas_revenue, Decimal(0))
        reconciliation_status = reconciliation.get("status", "UNKNOWN")
        group_complete = bool(
            reconciliation.get("gates", {}).get("group_coverage_complete")
        )
    category_totals["PESSOA_FISICA_DOCUMENTADA"] += cpf_total
    category_totals["RECEITA_SEM_NOTA_FISCAL"] += uncovered
    threshold = pgdas_revenue * Decimal("0.20")
    if reconciliation is None:
        recommendation = (
            "PENDING_GROUP_CONSOLIDATION"
            if reconciliation_mode == "GROUP_MISSING"
            else "PENDING_PGDAS_RECONCILIATION"
        )
    elif xml_excess > 0:
        recommendation = "PENDING_REVENUE_DIVERGENCE"
    elif reconciliation_mode == "GROUP" and not group_complete:
        recommendation = "PENDING_GROUP_CONSOLIDATION"
    elif unresolved_customer_regime_revenue > 0:
        recommendation = "PENDING_CUSTOMER_REGIME_LOOKUP"
    elif normal_revenue > threshold:
        recommendation = "RECOMMEND_HYBRID_REVIEW"
    else:
        recommendation = "NO_HYBRID_RECOMMENDATION"
    public_summary = {
        "basis": "PGDAS_RECONCILED_REVENUE",
        "reconciliation_mode": reconciliation_mode,
        "reconciliation_status": reconciliation_status,
        "pgdas_revenue": _money(pgdas_revenue),
        "documentary_revenue": _money(documentary_revenue),
        "revenue_without_invoice": _money(uncovered),
        "revenue_without_invoice_customer_assumption": "PESSOA_FISICA"
        if uncovered > 0
        else "NONE",
        "revenue_without_invoice_tax_treatment": "TRIBUTED_IN_PGDAS_SAME_WAY"
        if uncovered > 0
        else "NOT_APPLICABLE",
        "revenue_without_invoice_fiscal_benefit": "NONE"
        if uncovered > 0
        else "NOT_APPLICABLE",
        "xml_above_pgdas": _money(xml_excess),
        "normal_customer_revenue": _money(normal_revenue),
        "normal_customer_share": _percent(normal_revenue, pgdas_revenue),
        "threshold_percent": "20.0000",
        "threshold_amount": _money(threshold),
        "cpf_documented_revenue": _money(cpf_total),
        "customer_registry_status": customer_registry_status,
        "unresolved_customer_regime_revenue": _money(
            unresolved_customer_regime_revenue
        ),
        "category_totals": {
            category: _money(value)
            for category, value in sorted(category_totals.items())
        },
        "recommendation": recommendation,
        "simulation_only": True,
    }
    return rows, public_summary


def plan_credit_folder(
    folder: Path | str,
    *,
    scenario_path: Path | str | None = None,
    portfolio_root: Path | str | None = None,
) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta empresarial informada não existe")
    inputs = _load_period_inputs(base)
    reconciliation, reconciliation_mode = _reconciliation_for_period(
        base,
        Path(portfolio_root).expanduser().resolve() if portfolio_root else None,
        inputs["period"],
    )
    inputs["customer_summary"] = _load_json(
        base / "06_REVISAO_RECEITAS" / "clientes-cnpj-regime-summary.json",
        "06_REVISAO_RECEITAS/clientes-cnpj-regime-summary.json",
    )
    scenario = _read_scenario(scenario_path)
    supplier_rows, supplier_summary = _supplier_credit_rows(inputs, scenario)
    customer_rows, customer_summary = _customer_exposure(
        inputs, reconciliation, reconciliation_mode
    )
    return {
        "schema": CREDIT_PLANNING_SCHEMA,
        "schema_version": CREDIT_PLANNING_SCHEMA_VERSION,
        "use_case": "UC-004",
        "mode": "PERIOD",
        "scope": inputs["validation"]["scope"],
        "scenario": {
            "scenario_id": scenario["scenario_id"],
            "mode": scenario["mode"],
            "rates": scenario["rates"],
        },
        "customer_exposure": customer_summary,
        "supplier_credit": supplier_summary,
        "gates": {
            "pgdas_reconciled": reconciliation is not None,
            "group_consolidated": reconciliation_mode == "ESTABLISHMENT"
            or (
                reconciliation_mode == "GROUP"
                and bool(
                    reconciliation
                    and reconciliation.get("gates", {}).get("group_coverage_complete")
                )
            ),
            "simulation_only": True,
            "credit_legal_conclusion": False,
        },
        "limitations": [
            "As taxas do cenário são premissas de previsão e não crédito legal confirmado.",
            "A diferença positiva do PGDAS-D sobre o XML é tratada como venda para PF apenas na simulação.",
            "A classificação de natureza econômica e a evidência legal do UC-003 continuam exigindo aprovação.",
        ],
        "_private_suppliers": supplier_rows,
        "_private_customers": customer_rows,
    }


def plan_credit_portfolio(
    portfolio_root: Path | str, *, scenario_path: Path | str | None = None
) -> dict[str, Any]:
    root = Path(portfolio_root).expanduser().resolve()
    folders = _period_folders(root)
    if not folders:
        raise ValidationError(
            "Nenhuma competência processada foi encontrada na carteira"
        )
    period_results = [
        plan_credit_folder(folder, scenario_path=scenario_path, portfolio_root=root)
        for folder in folders
    ]
    supplier_rows = [
        row for result in period_results for row in result["_private_suppliers"]
    ]
    customer_rows = [
        row for result in period_results for row in result["_private_customers"]
    ]

    by_period: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in period_results:
        by_period[result["scope"]["period"]].append(result)

    pgdas = Decimal(0)
    documentary = Decimal(0)
    without_invoice = Decimal(0)
    normal = Decimal(0)
    for period_results_for_period in by_period.values():
        declared = _decimal(
            period_results_for_period[0]["customer_exposure"].get("pgdas_revenue")
        )
        documented = sum(
            (
                _decimal(result["customer_exposure"].get("documentary_revenue"))
                for result in period_results_for_period
            ),
            Decimal(0),
        )
        pgdas += declared
        documentary += documented
        without_invoice += max(declared - documented, Decimal(0))
        normal += sum(
            (
                _decimal(result["customer_exposure"].get("normal_customer_revenue"))
                for result in period_results_for_period
            ),
            Decimal(0),
        )
    threshold = pgdas * Decimal("0.20")
    recommendations = {
        result["customer_exposure"]["recommendation"] for result in period_results
    }
    unresolved_customer_regime_revenue = sum(
        (
            _decimal(
                result["customer_exposure"].get("unresolved_customer_regime_revenue")
            )
            for result in period_results
        ),
        Decimal(0),
    )
    all_group_complete = all(
        result["gates"]["group_consolidated"] for result in period_results
    )
    if not all_group_complete:
        recommendation = "PENDING_GROUP_CONSOLIDATION"
    elif "PENDING_REVENUE_DIVERGENCE" in recommendations:
        recommendation = "PENDING_REVENUE_DIVERGENCE"
    elif unresolved_customer_regime_revenue > 0:
        recommendation = "PENDING_CUSTOMER_REGIME_LOOKUP"
    elif normal > threshold:
        recommendation = "RECOMMEND_HYBRID_REVIEW"
    else:
        recommendation = "NO_HYBRID_RECOMMENDATION"
    supplier_credit_total = sum(
        (
            _decimal(result["supplier_credit"].get("estimated_credit"))
            for result in period_results
        ),
        Decimal(0),
    )
    supplier_creditable = sum(
        (
            _decimal(result["supplier_credit"].get("creditable_base"))
            for result in period_results
        ),
        Decimal(0),
    )
    supplier_pending = sum(
        (
            _decimal(result["supplier_credit"].get("pending_base"))
            for result in period_results
        ),
        Decimal(0),
    )
    return {
        "schema": CREDIT_PLANNING_SCHEMA,
        "schema_version": CREDIT_PLANNING_SCHEMA_VERSION,
        "use_case": "UC-004",
        "mode": "PORTFOLIO",
        "scope": {
            "periods": [result["scope"]["period"] for result in period_results],
            "establishments": sorted(
                {result["scope"].get("establishment_ref") for result in period_results}
            ),
        },
        "scenario": period_results[0]["scenario"],
        "periods": [
            {
                "period": result["scope"]["period"],
                "establishment_ref": result["scope"].get("establishment_ref"),
                "customer_exposure": result["customer_exposure"],
                "supplier_credit": result["supplier_credit"],
                "gates": result["gates"],
            }
            for result in period_results
        ],
        "customer_exposure": {
            "basis": "PGDAS_RECONCILED_REVENUE",
            "pgdas_revenue": _money(pgdas),
            "documentary_revenue": _money(documentary),
            "revenue_without_invoice": _money(without_invoice),
            "revenue_without_invoice_customer_assumption": "PESSOA_FISICA"
            if without_invoice > 0
            else "NONE",
            "revenue_without_invoice_tax_treatment": "TRIBUTED_IN_PGDAS_SAME_WAY"
            if without_invoice > 0
            else "NOT_APPLICABLE",
            "revenue_without_invoice_fiscal_benefit": "NONE"
            if without_invoice > 0
            else "NOT_APPLICABLE",
            "normal_customer_revenue": _money(normal),
            "normal_customer_share": _percent(normal, pgdas),
            "threshold_percent": "20.0000",
            "threshold_amount": _money(threshold),
            "recommendation": recommendation,
            "customer_registry_status": "LOADED"
            if all(
                result["customer_exposure"].get("customer_registry_status") == "LOADED"
                for result in period_results
            )
            else "ABSENT",
            "unresolved_customer_regime_revenue": _money(
                unresolved_customer_regime_revenue
            ),
            "simulation_only": True,
        },
        "supplier_credit": {
            "creditable_base": _money(supplier_creditable),
            "pending_base": _money(supplier_pending),
            "estimated_credit": _money(supplier_credit_total),
            "simulation_only": True,
        },
        "gates": {
            "period_count": len(period_results),
            "group_consolidated": all_group_complete,
            "simulation_only": True,
            "credit_legal_conclusion": False,
        },
        "limitations": [
            "A recomendação consolidada depende da cobertura PGDAS-D de todas as competências.",
            "As taxas são premissas de previsão; o resultado não constitui crédito apropriável.",
        ],
        "_private_suppliers": supplier_rows,
        "_private_customers": customer_rows,
    }


def _local_report(result: dict[str, Any]) -> str:
    lines = [
        "# Planejamento de crédito IBS/CBS",
        "",
        "- Documento confidencial de trabalho; simulação, não conclusão legal.",
        f"- Cenário: `{result['scenario']['scenario_id']}`",
        "",
        "## Exposição comercial dos clientes",
        "",
        f"- Receita PGDAS-D: {result['customer_exposure'].get('pgdas_revenue', 'não apurado')}",
        f"- Clientes de regime normal: {result['customer_exposure'].get('normal_customer_revenue', 'não apurado')}",
        f"- Participação: {result['customer_exposure'].get('normal_customer_share', 'não apurado')}%",
        f"- Linha de corte (20%): {result['customer_exposure'].get('threshold_amount', 'não apurado')}",
        f"- Receita sem nota fiscal: {result['customer_exposure'].get('revenue_without_invoice', 'não apurado')}",
        f"- Tratamento da receita sem nota: {result['customer_exposure'].get('revenue_without_invoice_tax_treatment', 'não apurado')}",
        f"- Recomendação: `{result['customer_exposure'].get('recommendation')}`",
        "",
        "## Fornecedores e crédito estimado",
        "",
        "| Empresa + CNPJ | Regime | Base creditável | Taxa | Crédito estimado | Situação |",
        "|---|---|---:|---:|---:|---|",
    ]
    for supplier in result["_private_suppliers"]:
        lines.append(
            f"| {supplier['name_cnpj']} | {supplier['simples_status']} | {supplier['creditable_base']} | {supplier['scenario_rate_percent']}% | {supplier['estimated_credit']} | {supplier['credit_status']} |"
        )
    return "\n".join(lines) + "\n"


def write_credit_outputs(
    result: dict[str, Any], output_dir: Path | str, *, meeting_report: bool = False
) -> list[Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    public_name = (
        "portfolio-credit-planning-summary.json"
        if result.get("mode") == "PORTFOLIO"
        else "credit-planning-summary.json"
    )
    public_path = target / public_name
    local_path = target / "credit-planning.local.jsonl"
    public_payload = {
        key: value for key, value in result.items() if not key.startswith("_private_")
    }
    public_path.write_text(
        json.dumps(public_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    local_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in [*result["_private_suppliers"], *result["_private_customers"]]
        ),
        encoding="utf-8",
    )
    written = [public_path, local_path]
    if meeting_report:
        report_path = target / "credit-planning.local.md"
        report_path.write_text(_local_report(result), encoding="utf-8")
        written.append(report_path)
    return written
