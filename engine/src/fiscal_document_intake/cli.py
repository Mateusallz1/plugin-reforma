from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .acquisition import review_acquisitions_folder, write_acquisition_outputs
from .content import extract_content_folder, write_content_outputs
from .core import ValidationError, validate_folder, write_outputs
from .planning_status import evaluate_planning_status, write_planning_status_outputs
from .revenue import review_revenue_folder, write_revenue_outputs
from .simple_reconciliation import (
    reconcile_simple_revenue,
    write_simple_reconciliation_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fiscal-document-intake",
        description="Executa os fluxos UC-001, UC-002 e UC-003 de uma pasta fiscal local.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validar uma pasta UC-001")
    validate.add_argument("folder", type=Path)
    validate.add_argument("--output-dir", type=Path)
    content = subparsers.add_parser(
        "extract-content", help="Extrair conteúdo fiscal autorizado pelo UC-001"
    )
    content.add_argument("folder", type=Path)
    content.add_argument("--output-dir", type=Path)
    acquisition = subparsers.add_parser(
        "review-acquisitions", help="Revisar aquisições autorizadas pelo UC-002"
    )
    acquisition.add_argument("folder", type=Path)
    acquisition.add_argument("--ruleset", type=Path, required=True)
    acquisition.add_argument("--output-dir", type=Path)
    revenue = subparsers.add_parser(
        "review-revenue", help="Revisar receitas, devoluções e remessas do UC-002"
    )
    revenue.add_argument("folder", type=Path)
    revenue.add_argument("--cfop-ruleset", type=Path, required=True)
    revenue.add_argument("--analyst-rules", type=Path, required=True)
    revenue.add_argument("--output-dir", type=Path)
    simple_reconciliation = subparsers.add_parser(
        "reconcile-simple-revenue",
        help="Conciliar a receita do UC-003B com uma declaração PGDAS-D",
    )
    simple_reconciliation.add_argument("folder", type=Path)
    simple_reconciliation.add_argument("--pgdas-folder", type=Path, required=True)
    simple_reconciliation.add_argument("--output-dir", type=Path)
    planning_status = subparsers.add_parser(
        "planning-status",
        help="Identificar o estágio atual e a próxima ação útil do planejamento",
    )
    planning_status.add_argument("folder", type=Path)
    planning_status.add_argument("--pgdas-folder", type=Path)
    planning_status.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_folder(args.folder)
            output_dir = args.output_dir or args.folder / "03_SAIDAS"
            written = write_outputs(result, output_dir)
            ready = result["gates"]["planning_authorized"]
            response = {
                "status": result["status"],
                "validation_id": result["validation_id"],
                "planning_authorized": ready,
                "outputs": [path.name for path in written],
            }
        elif args.command == "extract-content":
            result = extract_content_folder(args.folder)
            output_dir = args.output_dir or args.folder / "04_CONTEUDO"
            written = write_content_outputs(result, output_dir)
            ready = result["gates"]["content_extraction_ready"]
            response = {
                "status": result["status"],
                "content_analysis_id": result["content_analysis_id"],
                "content_extraction_ready": ready,
                "uc003_analysis_authorized": result["gates"][
                    "uc003_analysis_authorized"
                ],
                "lcp214_classification_ready": result["gates"][
                    "lcp214_classification_ready"
                ],
                "outputs": [path.name for path in written],
            }
        elif args.command == "review-acquisitions":
            result = review_acquisitions_folder(args.folder, args.ruleset)
            output_dir = args.output_dir or args.folder / "05_REVISAO_AQUISICOES"
            written = write_acquisition_outputs(result, output_dir)
            ready = result["gates"]["uc003_execution_ready"]
            response = {
                "status": result["status"],
                "review_id": result["review_id"],
                "acquisition_records": result["acquisition_records"],
                "analyst_review_required": result["gates"]["analyst_review_required"],
                "uc004_planning_authorized": result["gates"][
                    "uc004_planning_authorized"
                ],
                "outputs": [path.name for path in written],
            }
        elif args.command == "review-revenue":
            result = review_revenue_folder(
                args.folder, args.cfop_ruleset, args.analyst_rules
            )
            output_dir = args.output_dir or args.folder / "06_REVISAO_RECEITAS"
            written = write_revenue_outputs(result, output_dir)
            ready = result["gates"]["uc003_revenue_execution_ready"]
            response = {
                "status": result["status"],
                "review_id": result["review_id"],
                "reviewed_documents": result["reviewed_documents"],
                "revenue_population_ready": result["gates"]["revenue_population_ready"],
                "analyst_review_required": result["gates"]["analyst_review_required"],
                "uc004_planning_authorized": result["gates"][
                    "uc004_planning_authorized"
                ],
                "outputs": [path.name for path in written],
            }
        elif args.command == "reconcile-simple-revenue":
            result = reconcile_simple_revenue(args.folder, args.pgdas_folder)
            output_dir = args.output_dir or args.folder / "07_CONCILIACAO_SIMPLES"
            written = write_simple_reconciliation_outputs(result, output_dir)
            ready = result["gates"]["documentary_scope_reconciled"]
            response = {
                "status": result["status"],
                "reconciliation_id": result["reconciliation_id"],
                "documentary_scope_reconciled": ready,
                "group_coverage_complete": result["gates"]["group_coverage_complete"],
                "analyst_review_required": result["gates"]["analyst_review_required"],
                "uc004_planning_authorized": result["gates"][
                    "uc004_planning_authorized"
                ],
                "outputs": [path.name for path in written],
            }
        else:
            result = evaluate_planning_status(args.folder, args.pgdas_folder)
            output_dir = args.output_dir or args.folder / "08_STATUS_PLANEJAMENTO"
            written = write_planning_status_outputs(result, output_dir)
            ready = True
            response = {
                "status": result["status"],
                "state_id": result["state_id"],
                "current_stage": result["current_stage"],
                "next_actions": [
                    action["action"] for action in result["available_actions"]
                ],
                "required_inputs": [
                    item["input_id"] for item in result["required_inputs"]
                ],
                "can_continue_partially": result["can_continue_partially"],
                "outputs": [path.name for path in written],
            }
    except ValidationError as error:
        print(
            json.dumps({"status": "OPERATIONAL_ERROR", "error": str(error)}),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
