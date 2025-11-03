"""Tests for the Mule Analyzer CLI."""

from __future__ import annotations

import subprocess
import sys


def test_cli_handles_invalid_xml_without_traceback(tmp_path):
    """The CLI should exit gracefully when the XML cannot be parsed."""

    mule_file = tmp_path / "invalid.xml"
    mule_file.write_text(
        """
        <mule:root>
            <mule:flow name="broken-flow" />
        </mule:root>
        """.strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "mule_analyzer.cli", str(mule_file)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "Could not parse Mule configuration" in result.stderr
