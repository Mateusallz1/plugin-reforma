from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .core import ValidationError

PLANNING_STATUS_SCHEMA = "br.com.planejamento-reforma-tributaria/planning-status"
PLANNING_STATUS_SCHEMA_VERSION = "1.0.0"


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
                        "planilha de classificação das aquisições preenchida e aprovada pelo analista"
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
        "## O que foi concluído",
        "",
    ]
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
