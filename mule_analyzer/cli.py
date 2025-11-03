"""Command line interface for the Mule Analyzer utility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

from .parser import MuleAnalysis, parse_mule_file


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""

    parser = argparse.ArgumentParser(
        prog="mule-analyzer",
        description="Analyze Mule application XML descriptors.",
    )
    parser.add_argument(
        "mule_file",
        type=Path,
        help="Path to the Mule XML file that should be analyzed.",
    )
    return parser


def format_analysis(analysis: MuleAnalysis) -> str:
    """Render a textual representation of the analysis result."""

    lines: list[str] = [f"File: {analysis.path}", "Flows:"]
    if not analysis.flows:
        lines.append("  (no flows found)")
    for flow in analysis.flows:
        lines.append(f"  - {flow.name}")
        if flow.processors:
            for processor in flow.processors:
                lines.append(f"      * {processor.tag}")
        else:
            lines.append("      (no processors)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the command line tool."""

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        analysis = parse_mule_file(args.mule_file)
    except FileNotFoundError:
        sys.stderr.write(
            f"Error: The file '{args.mule_file}' does not exist.\n"
        )
        return 1
    except (ET.ParseError, ValueError) as exc:
        sys.stderr.write(
            "Error: Could not parse Mule configuration "
            f"'{args.mule_file}': {exc}\n"
        )
        return 1

    print(format_analysis(analysis))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
