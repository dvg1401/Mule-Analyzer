"""Command-line interface for the Mule Analyzer parser."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .parser import parse_mule_file


def build_parser() -> argparse.ArgumentParser:
    """Create and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Parse a Mule XML file and emit the graph JSON schema representation.",
    )
    parser.add_argument(
        "input",
        help="Path to the Mule XML file to parse.",
    )
    parser.add_argument(
        "--project",
        help="Override the project name stored in the generated JSON.",
    )
    parser.add_argument(
        "--schema-version",
        default="1.0.0",
        help="Schema version to record in the output JSON (default: 1.0.0).",
    )
    parser.add_argument(
        "--out",
        help="Optional path for the generated JSON file. Defaults to replacing the input extension with .json.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON output with indentation.",
    )
    return parser


def determine_output_path(input_path: Path, explicit: Optional[str]) -> Path:
    """Resolve the destination JSON path based on CLI inputs."""
    if explicit:
        return Path(explicit)
    if input_path.suffix:
        return input_path.with_suffix(".json")
    return input_path.with_name(f"{input_path.name}.json")


def dump_json(document: dict, destination: Path, *, pretty: bool) -> None:
    """Write *document* as JSON to *destination*, optionally pretty printed."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        if pretty:
            json.dump(document, handle, indent=2, ensure_ascii=False)
        else:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI entry point with optional argument vector *argv*."""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"Input file '{input_path}' does not exist.")

    try:
        document = parse_mule_file(
            str(input_path),
            project=args.project,
            schema_version=args.schema_version,
        )
    except ValueError as exc:
        parser.error(
            f"Could not parse Mule configuration '{input_path}': {exc}"
        )

    output_path = determine_output_path(input_path, args.out)
    dump_json(document, output_path, pretty=args.pretty)
    print(f"Generated JSON written to {output_path}")
    return 0


__all__: Iterable[str] = ["main"]
