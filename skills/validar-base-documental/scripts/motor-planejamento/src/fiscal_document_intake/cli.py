from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = validate_folder(args.folder)
        output_dir = args.output_dir or args.folder / "03_SAIDAS"
        written = write_outputs(result, output_dir)
    except ValidationError as error:
        print(
            json.dumps({"status": "OPERATIONAL_ERROR", "error": str(error)}),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "status": result["status"],
                "validation_id": result["validation_id"],
                "planning_authorized": result["gates"]["planning_authorized"],
                "outputs": [path.name for path in written],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["gates"]["planning_authorized"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
