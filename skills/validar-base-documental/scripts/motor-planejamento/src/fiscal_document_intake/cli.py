from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .content import extract_content_folder, write_content_outputs
from .core import ValidationError, validate_folder, write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fiscal-document-intake",
        description="Valida o UC-001 de uma pasta fiscal local.",
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
        else:
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
