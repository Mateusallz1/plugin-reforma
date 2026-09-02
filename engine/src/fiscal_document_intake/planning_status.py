from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .acquisition import ACQUISITION_SCHEMA_VERSION
from .content import CONTENT_SCHEMA_VERSION
from .core import (
    DOCUMENT_SCHEMA_VERSION,
    ValidationError,
    _format_decimal,
    _parse_decimal,
)
from .revenue import REVENUE_SCHEMA_VERSION
from .simple_reconciliation import SIMPLE_RECONCILIATION_SCHEMA_VERSION

PLANNING_STATUS_SCHEMA = "br.com.planejamento-reforma-tributaria/planning-status"
PLANNING_STATUS_SCHEMA_VERSION = "1.3.0"
DOCUMENTARY_SUMMARY_SCHEMA = (
    "br.com.planejamento-reforma-tributaria/documentary-summary"
)
DOCUMENTARY_SUMMARY_SCHEMA_VERSION = "1.0.0"


def _load_optional(path: Path, label: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{label} deve ser JSON UTF-8 válido") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} deve conter um objeto JSON")
    return value


def _action(action: str, label: str, *, automatic: bool, scope: str) -> dict[str, Any]:
    return {
        "action": action,
        "label": label,
        "automatic": automatic,
        "blocking_scope": scope,
    }


def _required_input(
    input_id: str,
    label: str,
    reason: str,
    *,
    scope: str,
    accepted_sources: list[str],
) -> dict[str, Any]:
    return {
        "input_id": input_id,
        "label": label,
        "reason": reason,
        "blocking_scope": scope,
        "accepted_sources": accepted_sources,
    }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decimal(value: Any) -> Decimal:
    return _parse_decimal(value) or Decimal(0)


def _ratio(purchases: Any, revenue: Any) -> str | None:
    if purchases is None or revenue is None:
        return None
    denominator = _decimal(revenue)
    if denominator <= 0:
        return None
    return f"{(_decimal(purchases) / denominator).quantize(Decimal('0.0001')):.4f}"


def _documentary_summary(
    validation: dict[str, Any] | None,
    content: dict[str, Any] | None,
    acquisition: dict[str, Any] | None,
    revenue: dict[str, Any] | None,
    reconciliation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build an aggregate audit view without copying commercial details.

    Values in this view are observations from completed local stages. Missing
    values remain ``None`` instead of being converted to zero, because an
    unavailable source is not evidence of no movement.
    """

    documents = _mapping(validation.get("documents")) if validation else {}
    pdf_evidence = _mapping(validation.get("pdf_evidence")) if validation else {}
    validation_gates = _mapping(validation.get("gates")) if validation else {}
    direction_counts = _mapping(documents.get("direction_counts"))
    direction_amounts = _mapping(documents.get("direction_gross_amounts"))

    flows = {
        direction: {
            "document_count": direction_counts.get(direction),
            "gross_amount": direction_amounts.get(direction),
        }
        for direction in ("ENTRADA", "SAIDA")
    }

    operational_groups: list[dict[str, Any]] = []
    for code, group_value in _mapping(documents.get("analysis_groups")).items():
        group = _mapping(group_value)
        detected_count = group.get("detected_count")
        included_count = group.get("count")
        if not detected_count and not included_count:
            continue
        operational_groups.append(
            {
                "group": code,
                "label": group.get("label"),
                "direction": group.get("direction"),
                "document_status": group.get("document_status"),
                "detected_count": detected_count,
                "included_count": included_count,
                "gross_amount": group.get("gross_amount"),
            }
        )

    content_data = _mapping(content)
    acquisition_data = _mapping(acquisition)
    revenue_data = _mapping(revenue)
    reconciliation_data = _mapping(reconciliation)
    revenue_totals = _mapping(revenue_data.get("totals"))
    reconciliation_totals = _mapping(reconciliation_data.get("totals"))
    reconciliation_gates = _mapping(reconciliation_data.get("gates"))

    if validation is None:
        status = "NOT_APURADO"
    elif (
        not validation_gates.get("planning_authorized")
        or validation.get("status") == "DOCUMENT_BASE_READY_WITH_SCOPE_LIMITATIONS"
    ):
        status = "PARCIAL"
    else:
        status = "APURADO"

    acquisition_gates = _mapping(acquisition_data.get("gates"))
    revenue_gates = _mapping(revenue_data.get("gates"))
    if acquisition is None:
        acquisition_nature_status = "NAO_INICIADO"
    elif acquisition_gates.get("analyst_review_required"):
        acquisition_nature_status = "PENDENTE_ANALISTA"
    else:
        acquisition_nature_status = "CONCLUIDO_OPERACIONAL"

    if revenue is None:
        revenue_classification_status = "NAO_INICIADO"
    elif not revenue_gates.get("cfop_classification_complete", True):
        revenue_classification_status = "PENDENTE_ANALISTA"
    else:
        revenue_classification_status = "CONCLUIDO_OPERACIONAL"

    if reconciliation is None:
        pgdas_status = "NAO_INICIADO"
    elif reconciliation_gates.get(
        "group_coverage_complete"
    ) and reconciliation_gates.get("documentary_scope_reconciled"):
        pgdas_status = "CONCILIADO"
    else:
        pgdas_status = "PARCIAL_O_PENDENTE"

    acquisition_totals = _mapping(acquisition_data.get("documentary_totals"))
    gross_purchases = acquisition_totals.get("gross_documentary_purchases")
    pending_purchases = acquisition_totals.get("pending_purchase_treatment")
    purchase_returns = revenue_totals.get("purchase_returns_outbound")
    if revenue is not None and purchase_returns is None:
        purchase_returns = "0.00"
    gross_revenue = revenue_totals.get("gross_operational_revenue")
    sales_returns = revenue_totals.get("sales_returns_inbound")
    net_purchases = None
    net_revenue = None
    if gross_purchases is not None and purchase_returns is not None:
        net_purchases = _format_decimal(
            _decimal(gross_purchases) - _decimal(purchase_returns)
        )
    if gross_revenue is not None and sales_returns is not None:
        net_revenue = _format_decimal(_decimal(gross_revenue) - _decimal(sales_returns))
    if acquisition is None and revenue is None:
        comparison_status = "NOT_APURADO"
    elif (
        acquisition is None
        or revenue is None
        or gross_purchases is None
        or pending_purchases is None
        or gross_revenue is None
        or _decimal(pending_purchases) != 0
        or not revenue_gates.get("revenue_population_ready")
    ):
        comparison_status = "PARTIAL"
    else:
        comparison_status = "AVAILABLE"
    purchase_sales_comparison = {
        "status": comparison_status,
        "gross_documentary_purchases": gross_purchases,
        "purchase_returns_outbound": purchase_returns,
        "net_documentary_purchases_candidate": net_purchases,
        "pending_purchase_treatment": pending_purchases,
        "gross_operational_revenue": gross_revenue,
        "sales_returns_inbound": sales_returns,
        "net_documentary_revenue_candidate": net_revenue,
        "purchase_to_revenue_ratio": _ratio(net_purchases, net_revenue),
        "cross_document_linkage": "NOT_PERFORMED",
        "interpretation": "AUDIT_ONLY",
    }

    return {
        "schema": DOCUMENTARY_SUMMARY_SCHEMA,
        "schema_version": DOCUMENTARY_SUMMARY_SCHEMA_VERSION,
        "status": status,
        "coverage": {
            "xml_files_found": documents.get("xml_files_found"),
            "fiscal_documents_found": documents.get("fiscal_documents_found"),
            "included_documents": documents.get("included"),
            "excluded_documents": documents.get("excluded"),
            "reported_documents": documents.get("reported"),
            "pdf_files_found": pdf_evidence.get("pdf_files_found"),
        },
        "document_types": documents.get("document_type_counts", {}),
        "flows": flows,
        "operational_groups": sorted(
            operational_groups, key=lambda item: str(item.get("group") or "")
        ),
        "content": {
            "records_total": content_data.get("records_total"),
            "record_kind_counts": content_data.get("record_kind_counts", {}),
            "component_count": content_data.get("component_count"),
            "eligible_records": _mapping(content_data.get("uc003_eligibility")).get(
                "eligible_records"
            ),
            "restricted_records": _mapping(content_data.get("uc003_eligibility")).get(
                "restricted_records"
            ),
        },
        "acquisitions": {
            "records": acquisition_data.get("acquisition_records"),
            "category_counts": acquisition_data.get("category_counts", {}),
            "category_amounts": acquisition_data.get("category_amounts", {}),
            "documentary_totals": acquisition_data.get("documentary_totals", {}),
            "nature_status": acquisition_nature_status,
        },
        "revenue": {
            "reviewed_documents": revenue_data.get("reviewed_documents"),
            "totals": {
                key: revenue_totals.get(key)
                for key in (
                    "gross_revenue_goods",
                    "gross_revenue_services",
                    "gross_revenue_transport",
                    "other_revenue",
                    "gross_operational_revenue",
                    "sales_returns_inbound",
                    "purchase_returns_outbound",
                    "excluded_non_revenue_operations",
                    "pending_revenue_treatment",
                    "unallocated_document_components",
                )
            },
            "classification_status": revenue_classification_status,
        },
        "pgdas_reconciliation": {
            "status": pgdas_status,
            "totals": {
                key: reconciliation_totals.get(key)
                for key in (
                    "pgdas_group_declared",
                    "pgdas_matched_establishment",
                    "documentary_matched_establishment",
                    "matched_difference",
                    "uncovered_pgdas_revenue",
                )
            },
            "missing_establishments": len(
                _mapping(reconciliation_data.get("coverage")).get(
                    "missing_establishment_refs", []
                )
                or []
            ),
        },
        "classification_status": {
            "acquisition_nature": acquisition_nature_status,
            "revenue_cfop": revenue_classification_status,
            "pgdas": pgdas_status,
        },
        "purchase_sales_comparison": purchase_sales_comparison,
        "limitations": [
            "Resumo preliminar de evidência local; não é conclusão de receita tributável, crédito ou débito.",
            "Valores ausentes significam fonte ainda não disponível, não ausência de movimento.",
            "Descrições comerciais e identificadores fiscais permanecem fora deste agregado.",
        ],
    }


def _base_result() -> dict[str, Any]:
    return {
        "schema": PLANNING_STATUS_SCHEMA,
        "schema_version": PLANNING_STATUS_SCHEMA_VERSION,
        "use_case": "PLANNING_COORDINATION",
        "phase": "PLANNING_STATUS",
        "status": "READY_TO_CONTINUE",
        "current_stage": "DOCUMENT_VALIDATION",
        "completed_stages": [],
        "available_actions": [],
        "required_inputs": [],
        "can_continue_partially": False,
        "technical_gates": {},
        "summary": {
            "situation": "A pasta foi recebida e ainda precisa passar pela validação documental.",
            "completed": [],
            "found": [],
            "needed": [],
            "can_continue": "O plugin pode iniciar a validação automaticamente.",
            "next_step": "Validar os documentos fiscais fornecidos.",
        },
        "documentary_summary": _documentary_summary(None, None, None, None, None),
    }


def _finalize(result: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    result["required_inputs"] = sorted(
        result["required_inputs"], key=lambda item: item["input_id"]
    )
    result["available_actions"] = sorted(
        result["available_actions"], key=lambda item: item["action"]
    )
    result["summary"]["needed"] = [item["label"] for item in result["required_inputs"]]
    if result["required_inputs"] and not result["available_actions"]:
        result["summary"]["next_step"] = "Fornecer os seguintes itens: " + "; ".join(
            item["label"] for item in result["required_inputs"]
        )
    result["state_id"] = (
        "PLN-"
        + hashlib.sha256(
            json.dumps(
                {
                    "material": material,
                    "status": result["status"],
                    "stage": result["current_stage"],
                    "actions": result["available_actions"],
                    "inputs": result["required_inputs"],
                    "schema_version": PLANNING_STATUS_SCHEMA_VERSION,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        .hexdigest()[:16]
        .upper()
    )
    return result


def evaluate_planning_status(
    folder: Path | str, pgdas_folder: Path | str | None = None
) -> dict[str, Any]:
    base = Path(folder).expanduser().resolve()
    if not base.is_dir():
        raise ValidationError("A pasta empresarial informada não existe")

    validation = _load_optional(
        base / "03_SAIDAS" / "validation-result.json",
        "03_SAIDAS/validation-result.json",
    )
    content = _load_optional(
        base / "04_CONTEUDO" / "content-summary.json",
        "04_CONTEUDO/content-summary.json",
    )
    acquisition = _load_optional(
        base / "05_REVISAO_AQUISICOES" / "acquisition-summary.json",
        "05_REVISAO_AQUISICOES/acquisition-summary.json",
    )
    revenue = _load_optional(
        base / "06_REVISAO_RECEITAS" / "revenue-summary.json",
        "06_REVISAO_RECEITAS/revenue-summary.json",
    )
    reconciliation = _load_optional(
        base / "07_CONCILIACAO_SIMPLES" / "simple-reconciliation-summary.json",
        "07_CONCILIACAO_SIMPLES/simple-reconciliation-summary.json",
    )
    if (
        validation is not None
        and validation.get("schema_version") != DOCUMENT_SCHEMA_VERSION
    ):
        validation = None
    if content is not None and content.get("schema_version") != CONTENT_SCHEMA_VERSION:
        content = None
    if (
        acquisition is not None
        and acquisition.get("schema_version") != ACQUISITION_SCHEMA_VERSION
    ):
        acquisition = None
    if revenue is not None and revenue.get("schema_version") != REVENUE_SCHEMA_VERSION:
        revenue = None
    if (
        reconciliation is not None
        and reconciliation.get("schema_version") != SIMPLE_RECONCILIATION_SCHEMA_VERSION
    ):
        reconciliation = None
    pgdas_available = bool(
        pgdas_folder and Path(pgdas_folder).expanduser().resolve().is_dir()
    )
    material = {
        "validation_id": validation.get("validation_id") if validation else None,
        "content_analysis_id": content.get("content_analysis_id") if content else None,
        "acquisition_review_id": acquisition.get("review_id") if acquisition else None,
        "revenue_review_id": revenue.get("review_id") if revenue else None,
        "reconciliation_id": (
            reconciliation.get("reconciliation_id") if reconciliation else None
        ),
        "pgdas_available": pgdas_available,
    }
    result = _base_result()
    result["documentary_summary"] = _documentary_summary(
        validation, content, acquisition, revenue, reconciliation
    )

    if validation is None:
        result["available_actions"].append(
            _action(
                "RUN_DOCUMENT_VALIDATION",
                "Validar os documentos fiscais fornecidos",
                automatic=True,
                scope="DOCUMENT_BASE",
            )
        )
        return _finalize(result, material)
    if validation.get("use_case") != "UC-001":
        raise ValidationError("A saída documental não pertence ao UC-001")

    planning_authorized = bool(validation.get("gates", {}).get("planning_authorized"))
    result["technical_gates"]["documents_ready"] = planning_authorized
    if not planning_authorized:
        blockers = len(validation.get("blockers", []))
        result.update(
            {
                "status": "BLOCKED",
                "current_stage": "DOCUMENT_VALIDATION",
                "can_continue_partially": False,
            }
        )
        result["required_inputs"].append(
            _required_input(
                "RESOLVE_DOCUMENTARY_BLOCKERS",
                "Documentos fiscais corrigidos ou complementares",
                f"A validação encontrou {blockers} pendência(s) que impedem qualquer população documental de prosseguir.",
                scope="DOCUMENT_BASE",
                accepted_sources=[
                    "XML fiscal válido",
                    "correção da competência ou do escopo",
                ],
            )
        )
        result["summary"].update(
            {
                "situation": "A validação documental encontrou pendências que impedem a análise.",
                "found": [f"Foram encontrados {blockers} bloqueador(es) documentais."],
                "can_continue": "Nenhuma análise documental pode continuar enquanto os bloqueadores permanecerem.",
                "next_step": "Corrigir ou complementar os documentos indicados no relatório de prontidão.",
            }
        )
        return _finalize(result, material)

    result["completed_stages"].append("DOCUMENT_VALIDATION")
    result["summary"]["completed"].append(
        "Documentos fiscais validados nos escopos autorizados."
    )
    authorized_scopes = validation.get("gates", {}).get("authorized_scopes", [])
    scope_count = len(authorized_scopes)
    result["summary"]["found"].append(
        "Um conjunto de documentos está autorizado para análise."
        if scope_count == 1
        else f"{scope_count} conjuntos de documentos estão autorizados para análise."
    )

    if content is None:
        result["current_stage"] = "CONTENT_EXTRACTION"
        result["available_actions"].append(
            _action(
                "RUN_CONTENT_EXTRACTION",
                "Extrair produtos, serviços e transportes",
                automatic=True,
                scope="AUTHORIZED_DOCUMENTS",
            )
        )
        result["summary"].update(
            {
                "situation": "Os documentos estão prontos para a extração do conteúdo fiscal.",
                "can_continue": "O plugin pode extrair o conteúdo automaticamente.",
                "next_step": "Extrair produtos, serviços e transportes dos documentos autorizados.",
            }
        )
        return _finalize(result, material)
    if content.get("use_case") != "UC-002":
        raise ValidationError("A saída de conteúdo não pertence ao UC-002")

    content_ready = bool(content.get("gates", {}).get("uc003_analysis_authorized"))
    result["technical_gates"]["content_ready"] = content_ready
    if not content_ready:
        result.update(
            {
                "status": "BLOCKED",
                "current_stage": "CONTENT_EXTRACTION",
                "can_continue_partially": False,
            }
        )
        result["required_inputs"].append(
            _required_input(
                "RESOLVE_CONTENT_RESTRICTIONS",
                "Correção dos itens fiscais restritos",
                "Nenhum item elegível foi liberado para as revisões seguintes.",
                scope="FISCAL_CONTENT",
                accepted_sources=["XML corrigido", "catálogo Produto x NCM aprovado"],
            )
        )
        result["summary"].update(
            {
                "situation": "O conteúdo foi extraído, mas não há população autorizada para revisão.",
                "can_continue": "As revisões permanecem bloqueadas.",
                "next_step": "Corrigir os itens restritos indicados no relatório de qualidade.",
            }
        )
        return _finalize(result, material)

    result["completed_stages"].append("CONTENT_EXTRACTION")
    result["summary"]["completed"].append(
        "Conteúdo fiscal extraído e preparado para revisão."
    )

    automatic_reviews = False
    if acquisition is None:
        automatic_reviews = True
        result["available_actions"].append(
            _action(
                "RUN_ACQUISITION_REVIEW",
                "Revisar as aquisições",
                automatic=True,
                scope="ACQUISITIONS",
            )
        )
    else:
        if acquisition.get("phase") != "ACQUISITION_REVIEW":
            raise ValidationError("A saída de aquisições não pertence ao UC-003")
        result["completed_stages"].append("ACQUISITION_REVIEW")
        result["technical_gates"]["acquisition_review_ready"] = bool(
            acquisition.get("gates", {}).get("uc003_execution_ready")
        )
        if acquisition.get("gates", {}).get("analyst_review_required"):
            result["summary"]["completed"].append(
                "Aquisições revisadas e encaminhadas para classificação do analista."
            )
            result["required_inputs"].append(
                _required_input(
                    "APPROVE_ACQUISITION_CLASSIFICATIONS",
                    "Classificação e aprovação das aquisições",
                    "As naturezas das compras dependem da finalidade econômica confirmada pelo analista.",
                    scope="ACQUISITION_PLANNING",
                    accepted_sources=[
                        "aprovação na fila central da carteira ou classificação local aprovada pelo analista"
                    ],
                )
            )
        else:
            result["summary"]["completed"].append("Aquisições revisadas.")

    if revenue is None:
        automatic_reviews = True
        result["available_actions"].append(
            _action(
                "RUN_REVENUE_REVIEW",
                "Revisar as receitas",
                automatic=True,
                scope="REVENUE",
            )
        )
    else:
        if revenue.get("phase") != "REVENUE_REVIEW":
            raise ValidationError("A saída de receitas não pertence ao UC-003B")
        result["completed_stages"].append("REVENUE_REVIEW")
        revenue_ready = bool(revenue.get("gates", {}).get("revenue_population_ready"))
        result["technical_gates"]["revenue_ready"] = revenue_ready
        if not revenue_ready:
            result["required_inputs"].append(
                _required_input(
                    "REVIEW_REVENUE_DIFFERENCES",
                    "Revisão das diferenças de receita",
                    "Existem CFOPs, documentos mistos ou diferenças de valores que impedem a conciliação do faturamento.",
                    scope="REVENUE_RECONCILIATION",
                    accepted_sources=[
                        "classificações de receita aprovadas pelo analista",
                        "documentos complementares",
                    ],
                )
            )
        elif revenue.get("status") == "REVENUE_REVIEW_NO_DOCUMENT":
            result["summary"]["completed"].append(
                "Nenhuma receita documental foi encontrada nesta competência; a conciliação com a declaração dirá se houve movimento."
            )
        else:
            result["summary"]["completed"].append(
                "Receitas documentais revisadas e classificadas."
            )

    if automatic_reviews:
        result["current_stage"] = "OPERATION_REVIEWS"
        result["can_continue_partially"] = bool(result["required_inputs"])
        result["summary"].update(
            {
                "situation": "O conteúdo está pronto para as revisões de compras e receitas.",
                "can_continue": "As revisões disponíveis podem ser executadas automaticamente e de forma independente.",
                "next_step": "Executar as revisões de aquisições e receitas que ainda não foram concluídas.",
            }
        )
        return _finalize(result, material)

    revenue_ready = bool(
        revenue and revenue.get("gates", {}).get("revenue_population_ready")
    )
    if not revenue_ready:
        result.update(
            {
                "status": "NEEDS_USER_INPUT",
                "current_stage": "REVENUE_REVIEW",
                "can_continue_partially": bool(acquisition),
            }
        )
        result["summary"].update(
            {
                "situation": "As receitas foram revisadas, mas ainda existem diferenças que impedem a conciliação.",
                "can_continue": "A frente de aquisições pode continuar; a conciliação da receita deve aguardar.",
                "next_step": "Revisar as diferenças de receita indicadas na fila local.",
            }
        )
        return _finalize(result, material)

    if reconciliation is None:
        result["current_stage"] = "SIMPLE_REVENUE_RECONCILIATION"
        if pgdas_available:
            result["available_actions"].append(
                _action(
                    "RUN_SIMPLE_RECONCILIATION",
                    "Conciliar a receita documental com o PGDAS-D",
                    automatic=True,
                    scope="SIMPLE_REVENUE",
                )
            )
            result["summary"].update(
                {
                    "situation": "As receitas estão prontas e a pasta do PGDAS-D foi localizada.",
                    "can_continue": "O plugin pode executar a conciliação automaticamente.",
                    "next_step": "Conciliar a receita por estabelecimento e atividade.",
                }
            )
        else:
            result["status"] = "NEEDS_USER_INPUT"
            result["required_inputs"].append(
                _required_input(
                    "PROVIDE_PGDAS_FOLDER",
                    "Pasta do PGDAS-D da competência",
                    "A receita documental está pronta, mas falta a declaração usada para confrontar o faturamento informado no Simples.",
                    scope="SIMPLE_REVENUE",
                    accepted_sources=[
                        "declaração PGDAS-D",
                        "recibo e extrato opcionais",
                    ],
                )
            )
            result["summary"].update(
                {
                    "situation": "As receitas estão prontas para conciliação com o Simples Nacional.",
                    "can_continue": "Aquisições podem continuar, mas a conciliação depende da declaração.",
                    "next_step": "Indicar a pasta que contém a declaração PGDAS-D da mesma competência.",
                }
            )
        return _finalize(result, material)

    if reconciliation.get("use_case") != "UC-003C":
        raise ValidationError("A saída de conciliação não pertence ao UC-003C")
    if reconciliation.get("revenue_review_id") != revenue.get("review_id"):
        result["current_stage"] = "SIMPLE_REVENUE_RECONCILIATION"
        if pgdas_available:
            result["available_actions"].append(
                _action(
                    "RUN_SIMPLE_RECONCILIATION",
                    "Atualizar a conciliação após a nova revisão de receitas",
                    automatic=True,
                    scope="SIMPLE_REVENUE",
                )
            )
            result["summary"]["next_step"] = "Atualizar a conciliação automaticamente."
        else:
            result["status"] = "NEEDS_USER_INPUT"
            result["required_inputs"].append(
                _required_input(
                    "PROVIDE_PGDAS_FOLDER",
                    "Pasta do PGDAS-D para atualizar a conciliação",
                    "A revisão de receitas mudou depois da última conciliação.",
                    scope="SIMPLE_REVENUE",
                    accepted_sources=["declaração PGDAS-D da competência"],
                )
            )
        return _finalize(result, material)

    result["completed_stages"].append("SIMPLE_REVENUE_RECONCILIATION")
    documentary_reconciled = bool(
        reconciliation.get("gates", {}).get("documentary_scope_reconciled")
    )
    group_complete = bool(
        reconciliation.get("gates", {}).get("group_coverage_complete")
    )
    result["technical_gates"].update(
        {
            "documentary_scope_reconciled": documentary_reconciled,
            "group_coverage_complete": group_complete,
            "uc004_planning_authorized": False,
        }
    )
    result["current_stage"] = "SIMPLE_REVENUE_RECONCILIATION"
    if not documentary_reconciled:
        result["required_inputs"].append(
            _required_input(
                "REVIEW_SIMPLE_REVENUE_DIFFERENCES",
                "Explicação das diferenças entre documentos e PGDAS-D",
                "O estabelecimento coberto possui valores documentais diferentes dos declarados.",
                scope="SIMPLE_REVENUE",
                accepted_sources=[
                    "documentos complementares",
                    "deduções",
                    "decisão aprovada do analista",
                ],
            )
        )
    if not group_complete:
        missing_count = len(
            reconciliation.get("coverage", {}).get("missing_establishment_refs", [])
        )
        missing_reason = (
            "O PGDAS-D contém um estabelecimento sem base documental fornecida."
            if missing_count == 1
            else f"O PGDAS-D contém {missing_count} estabelecimentos sem base documental fornecida."
        )
        missing_label = (
            "Pasta fiscal do estabelecimento ainda não coberto"
            if missing_count == 1
            else "Pastas fiscais dos estabelecimentos ainda não cobertos"
        )
        result["required_inputs"].append(
            _required_input(
                "PROVIDE_MISSING_ESTABLISHMENT_DOCUMENTS",
                missing_label,
                missing_reason,
                scope="CONSOLIDATED_GROUP",
                accepted_sources=[
                    "pasta fiscal do estabelecimento e da mesma competência"
                ],
            )
        )

    if result["required_inputs"]:
        result["status"] = "NEEDS_USER_INPUT"
        result["can_continue_partially"] = documentary_reconciled and not group_complete
        result["summary"].update(
            {
                "situation": (
                    "O estabelecimento analisado conciliou, mas o fechamento do grupo ainda está incompleto."
                    if documentary_reconciled and not group_complete
                    else "A conciliação encontrou pontos que exigem documentos ou revisão do analista."
                ),
                "completed": result["summary"]["completed"]
                + ["Receitas confrontadas com a declaração do Simples Nacional."],
                "can_continue": (
                    "A análise do estabelecimento conciliado pode continuar; o consolidado do grupo permanece pendente."
                    if result["can_continue_partially"]
                    else "O planejamento conclusivo deve aguardar a resolução das pendências."
                ),
                "next_step": "Fornecer os itens listados em 'Preciso de você' para completar o fechamento.",
            }
        )
        return _finalize(result, material)

    result.update(
        {
            "status": "CURRENT_IMPLEMENTATION_COMPLETE",
            "current_stage": "READY_FOR_MATERIAL_RULES",
            "can_continue_partially": False,
        }
    )
    result["summary"].update(
        {
            "situation": "Todas as etapas atualmente implementadas foram concluídas.",
            "completed": result["summary"]["completed"]
            + ["Receita documental conciliada integralmente com o PGDAS-D."],
            "can_continue": "O próximo avanço depende da implementação e aprovação das regras materiais do UC-004.",
            "next_step": "Aplicar as regras materiais versionadas quando o UC-004 estiver disponível.",
        }
    )
    return _finalize(result, material)


def _summary_value(value: Any) -> str:
    return "não apurado" if value is None else str(value)


def _summary_status_label(value: Any) -> str:
    return {
        "NOT_APURADO": "Ainda não apurado",
        "PARCIAL": "Apuração parcial",
        "APURADO": "Apurado com os documentos disponíveis",
        "NAO_INICIADO": "Ainda não iniciado",
        "PENDENTE_ANALISTA": "Pendente de aprovação do analista",
        "CONCLUIDO_OPERACIONAL": "Concluído no nível operacional",
        "CONCILIADO": "Conciliado para o escopo coberto",
        "PARCIAL_O_PENDENTE": "Parcial ou pendente de revisão",
    }.get(str(value), _summary_value(value))


def _append_documentary_summary(lines: list[str], result: dict[str, Any]) -> None:
    """Append a user-facing aggregate without exposing commercial details."""

    documentary = _mapping(result.get("documentary_summary"))
    coverage = _mapping(documentary.get("coverage"))
    flows = _mapping(documentary.get("flows"))
    content = _mapping(documentary.get("content"))
    acquisitions = _mapping(documentary.get("acquisitions"))
    acquisition_totals = _mapping(acquisitions.get("documentary_totals"))
    revenue = _mapping(documentary.get("revenue"))
    revenue_totals = _mapping(revenue.get("totals"))
    comparison = _mapping(documentary.get("purchase_sales_comparison"))
    pgdas = _mapping(documentary.get("pgdas_reconciliation"))
    pgdas_totals = _mapping(pgdas.get("totals"))

    lines.extend(
        [
            "## Resumo documental preliminar",
            "",
            "Esta é uma fotografia dos dados observados até agora. Ela serve para conferência e auditoria, mas não conclui receita tributável, crédito ou débito.",
            "",
            f"- Estado do resumo: {_summary_status_label(documentary.get('status'))}",
            f"- XMLs encontrados: {_summary_value(coverage.get('xml_files_found'))}",
            f"- Documentos fiscais identificados: {_summary_value(coverage.get('fiscal_documents_found'))}",
            f"- Documentos incluídos: {_summary_value(coverage.get('included_documents'))}",
            f"- Documentos excluídos: {_summary_value(coverage.get('excluded_documents'))}",
            f"- PDFs encontrados: {_summary_value(coverage.get('pdf_files_found'))}",
            "",
            "### Entradas e saídas",
            "",
            "| Fluxo | Documentos | Valor bruto |",
            "|---|---:|---:|",
        ]
    )
    for direction, label in (("ENTRADA", "Entradas"), ("SAIDA", "Saídas")):
        flow = _mapping(flows.get(direction))
        lines.append(
            f"| {label} | {_summary_value(flow.get('document_count'))} | "
            f"{_summary_value(flow.get('gross_amount'))} |"
        )

    lines.extend(
        [
            "",
            "### Documentos por tipo",
            "",
            "| Tipo | Documentos |",
            "|---|---:|",
        ]
    )
    type_labels = {"NFE": "NF-e", "NFCE": "NFC-e", "NFSE": "NFS-e", "CTE": "CT-e"}
    document_types = _mapping(documentary.get("document_types"))
    if document_types:
        for document_type, count in sorted(document_types.items()):
            lines.append(
                f"| {type_labels.get(document_type, document_type)} | {count} |"
            )
    else:
        lines.append("| Nenhum tipo apurado | não apurado |")

    lines.extend(
        [
            "",
            "### Populações identificadas",
            "",
            "| População | Registros | Situação |",
            "|---|---:|---|",
        ]
    )
    kind_labels = {
        "PRODUCT": "Produtos",
        "SERVICE": "Serviços",
        "TRANSPORT": "Transportes",
    }
    kind_counts = _mapping(content.get("record_kind_counts"))
    if kind_counts:
        for kind, count in sorted(kind_counts.items()):
            lines.append(f"| {kind_labels.get(kind, kind)} | {count} | Observado |")
    elif content.get("records_total") is not None:
        lines.append(
            f"| Conteúdo normalizado | {content['records_total']} | Observado |"
        )
    else:
        lines.append("| Conteúdo fiscal | não apurado | Ainda não iniciado |")
    component_status = (
        "Observado"
        if content.get("component_count") is not None
        else "Ainda não iniciado"
    )
    lines.append(
        f"| Componentes extraídos | {_summary_value(content.get('component_count'))} | {component_status} |"
    )

    lines.extend(
        [
            "",
            "### Aquisições",
            "",
            "| Categoria | Itens | Valor dos itens |",
            "|---|---:|---:|",
        ]
    )
    category_counts = _mapping(acquisitions.get("category_counts"))
    category_amounts = _mapping(acquisitions.get("category_amounts"))
    category_labels = {
        "MERCADORIA": "Mercadorias",
        "SERVICO": "Serviços",
        "TRANSPORTE": "Transportes",
    }
    if category_counts:
        for category, count in sorted(category_counts.items()):
            lines.append(
                f"| {category_labels.get(category, category)} | {count} | "
                f"{_summary_value(category_amounts.get(category))} |"
            )
    else:
        lines.append("| Aquisições | não apurado | não apurado |")
    lines.append(
        f"- Natureza econômica: {_summary_status_label(acquisitions.get('nature_status'))}."
    )
    if acquisition_totals:
        lines.extend(
            [
                f"- Total bruto documental de compras: {_summary_value(acquisition_totals.get('gross_documentary_purchases'))}.",
                f"- Documentos pendentes de tratamento: {_summary_value(acquisition_totals.get('pending_document_count'))}.",
                f"- Operações de entrada fora de compras: {_summary_value(acquisition_totals.get('non_purchase_entry_operations'))}.",
            ]
        )

    lines.extend(
        [
            "",
            "### Receitas documentais",
            "",
            "| Componente | Valor |",
            "|---|---:|",
        ]
    )
    revenue_labels = {
        "gross_revenue_goods": "Mercadorias",
        "gross_revenue_services": "Serviços",
        "gross_revenue_transport": "Transportes",
        "other_revenue": "Outras receitas",
        "gross_operational_revenue": "Receita operacional documental",
        "sales_returns_inbound": "Devoluções",
        "purchase_returns_outbound": "Devoluções de compra emitidas",
        "excluded_non_revenue_operations": "Remessas e operações fora da receita",
        "pending_revenue_treatment": "Tratamento pendente",
        "unallocated_document_components": "Componentes não alocados",
    }
    if revenue_totals and any(value is not None for value in revenue_totals.values()):
        for key, label in revenue_labels.items():
            if key in revenue_totals:
                lines.append(f"| {label} | {_summary_value(revenue_totals.get(key))} |")
    else:
        lines.append("| Receita documental | não apurada |")
    lines.append(
        f"- Classificação por CFOP: {_summary_status_label(revenue.get('classification_status'))}."
    )

    if comparison.get("status") not in {None, "NOT_APURADO"}:
        lines.extend(
            [
                "",
                "### Compras documentais × vendas documentais",
                "",
                "| Indicador | Valor |",
                "|---|---:|",
                f"| Compras documentais brutas | {_summary_value(comparison.get('gross_documentary_purchases'))} |",
                f"| Devoluções de compra | {_summary_value(comparison.get('purchase_returns_outbound'))} |",
                f"| Compras documentais líquidas candidatas | {_summary_value(comparison.get('net_documentary_purchases_candidate'))} |",
                f"| Receita operacional documental bruta | {_summary_value(comparison.get('gross_operational_revenue'))} |",
                f"| Devoluções de venda | {_summary_value(comparison.get('sales_returns_inbound'))} |",
                f"| Receita documental líquida candidata | {_summary_value(comparison.get('net_documentary_revenue_candidate'))} |",
                f"| Relação compras/receita | {_summary_value(comparison.get('purchase_to_revenue_ratio'))} |",
                f"- Situação: {_summary_status_label(comparison.get('status'))}. Indicador exclusivamente documental e de auditoria; não conclui margem, estoque ou irregularidade.",
            ]
        )

    if any(value is not None for value in pgdas_totals.values()) or pgdas.get(
        "status"
    ) not in {None, "NAO_INICIADO"}:
        lines.extend(
            [
                "",
                "### Conciliação com o PGDAS-D",
                "",
                "| Indicador | Valor |",
                "|---|---:|",
            ]
        )
        pgdas_labels = {
            "pgdas_group_declared": "PGDAS-D declarado no grupo",
            "pgdas_matched_establishment": "PGDAS-D do estabelecimento coberto",
            "documentary_matched_establishment": "Receita documental do estabelecimento coberto",
            "matched_difference": "Diferença no estabelecimento coberto",
            "uncovered_pgdas_revenue": "Receita PGDAS-D declarada por estabelecimento fora do escopo desta análise",
        }
        for key, label in pgdas_labels.items():
            if key == "uncovered_pgdas_revenue" and not pgdas.get(
                "missing_establishments"
            ):
                continue
            if key in pgdas_totals:
                lines.append(f"| {label} | {_summary_value(pgdas_totals.get(key))} |")
        lines.append(f"- Situação: {_summary_status_label(pgdas.get('status'))}.")
        if pgdas.get("missing_establishments"):
            lines.append(
                "- Esse valor pertence a estabelecimento(s) declarado(s) no PGDAS-D que não estão na pasta documental atual; não indica falta de lastro no estabelecimento analisado."
            )

    lines.extend(
        [
            "",
            "Os valores acima são apresentados para conferência. A aprovação da natureza das aquisições e as conclusões tributárias continuam nas etapas próprias.",
            "",
        ]
    )


def _report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    scope_labels = {
        "DOCUMENT_BASE": "toda a base documental",
        "FISCAL_CONTENT": "a extração do conteúdo fiscal",
        "ACQUISITION_PLANNING": "a análise das aquisições",
        "REVENUE_RECONCILIATION": "a conciliação das receitas",
        "SIMPLE_REVENUE": "a conciliação com o Simples Nacional",
        "CONSOLIDATED_GROUP": "o fechamento consolidado do grupo",
    }
    lines = [
        "# Situação do Planejamento",
        "",
        "## Situação atual",
        "",
        summary["situation"],
        "",
    ]
    documentary_lines: list[str] = []
    _append_documentary_summary(documentary_lines, result)
    lines.extend(documentary_lines)
    lines.extend(["## O que foi concluído", ""])
    lines.extend(f"- {item}" for item in summary["completed"])
    if not summary["completed"]:
        lines.append("- Nenhuma etapa concluída ainda.")
    lines.extend(["", "## O que foi encontrado", ""])
    lines.extend(f"- {item}" for item in summary["found"])
    if not summary["found"]:
        lines.append("- Nenhuma ocorrência adicional identificada.")
    lines.extend(["", "## Preciso de você", ""])
    if result["required_inputs"]:
        for item in result["required_inputs"]:
            lines.extend(
                [
                    f"- **{item['label']}**",
                    f"  - Como enviar: {', '.join(item['accepted_sources'])}",
                ]
            )
    else:
        lines.append("- Nenhuma informação adicional necessária neste momento.")
    lines.extend(["", "## Por que é necessário", ""])
    if result["required_inputs"]:
        for item in result["required_inputs"]:
            impact = scope_labels.get(item["blocking_scope"], "a etapa atual")
            lines.append(
                f"- **{item['label']}**: {item['reason']} Sem isso, permanece pendente {impact}."
            )
    else:
        lines.append("- Nenhuma pendência depende do usuário neste momento.")
    lines.extend(
        [
            "",
            "## O que pode continuar",
            "",
            summary["can_continue"],
            "",
            "## Próximo passo",
            "",
            summary["next_step"],
            "",
        ]
    )
    return "\n".join(lines)


def write_planning_status_outputs(
    result: dict[str, Any], output_dir: Path | str
) -> tuple[Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "planning-status.json"
    report_path = target / "relatorio-status-planejamento.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_report(result), encoding="utf-8")
    return json_path, report_path
