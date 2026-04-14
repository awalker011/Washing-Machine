from __future__ import annotations

import argparse
import json
import sys

from .pipeline import process_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standardize CSV/XLSX files into validated output CSVs using external schema and mapping configs."
    )
    parser.add_argument("--input", required=True, help="Path to the input folder or a single CSV/XLSX file.")
    parser.add_argument("--schema", required=True, help="Path to a schema file or schema directory.")
    parser.add_argument("--mapping", required=True, help="Path to a mapping file or mapping directory.")
    parser.add_argument("--output", default="./output", help="Output directory for accepted rows and error files.")
    parser.add_argument("--logs", default="./logs", help="Directory for CSV log files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = process_all(
            input_path=args.input,
            schema_path=args.schema,
            mapping_path=args.mapping,
            output_dir=args.output,
            logs_dir=args.logs,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
