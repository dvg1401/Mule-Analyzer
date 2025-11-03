"""Parsing utilities for Mule application XML files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List
import xml.etree.ElementTree as ET


@dataclass(slots=True)
class MuleProcessor:
    """Representation of a processor inside a Mule flow."""

    tag: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MuleFlow:
    """Representation of a Mule flow."""

    name: str
    processors: List[MuleProcessor] = field(default_factory=list)


@dataclass(slots=True)
class MuleAnalysis:
    """Top-level container for a Mule configuration file."""

    path: Path
    flows: List[MuleFlow] = field(default_factory=list)


def parse_mule_file(path: str | Path) -> MuleAnalysis:
    """Parse a Mule application XML file.

    Parameters
    ----------
    path:
        Path to the Mule XML file.

    Returns
    -------
    MuleAnalysis
        Parsed representation of the Mule configuration.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    xml.etree.ElementTree.ParseError
        If the XML cannot be parsed.
    ValueError
        If the XML is parsed but does not contain any Mule flows.
    """

    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    tree = ET.parse(input_path)
    root = tree.getroot()

    flows = [_parse_flow(element) for element in root.findall(".//{*}flow")]
    if not flows:
        raise ValueError("The Mule file does not contain any flows.")

    return MuleAnalysis(path=input_path, flows=flows)


def _parse_flow(element: ET.Element) -> MuleFlow:
    name = element.get("name")
    if not name:
        raise ValueError("Encountered a Mule flow without a name attribute.")

    processors = [
        MuleProcessor(tag=_strip_namespace(child.tag), attributes=dict(child.attrib))
        for child in element
    ]
    return MuleFlow(name=name, processors=processors)


def _strip_namespace(tag: str) -> str:
    """Remove the XML namespace from an element tag."""

    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
