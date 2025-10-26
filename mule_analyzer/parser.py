"""Utilities to parse MuleSoft XML and emit graph JSON."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from io import StringIO
from typing import Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

SchemaDict = Dict[str, object]


@dataclass(frozen=True)
class NodeLookup:
    """Helper to resolve flow and subflow identifiers."""

    flows: Dict[str, str]
    subflows: Dict[str, str]
    assumptions: List[str]

    def resolve(self, name: str) -> Optional[str]:
        if name in self.flows:
            return self.flows[name]
        if name in self.subflows:
            return self.subflows[name]
        self.assumptions.append(f"Reference to unknown flow or subflow '{name}'")
        # assume flow by default for stability
        return f"flow://{name}"


@dataclass
class ProcessorParseResult:
    processor: SchemaDict
    edges: List[SchemaDict]


def parse_mule_file(path: str, project: Optional[str] = None, *, schema_version: str = "1.0.0") -> SchemaDict:
    """Parse a Mule XML file located at *path* into the schema dictionary."""
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    project_name = project or infer_project_name(path)
    return parse_mule_xml(content, project_name, schema_version=schema_version)


def parse_mule_xml(xml_content: str, project: str, *, schema_version: str = "1.0.0") -> SchemaDict:
    """Parse Mule XML *xml_content* and return a dictionary matching the schema."""
    namespace_map = collect_namespaces(xml_content)
    tree = ET.ElementTree(ET.fromstring(xml_content))
    root = tree.getroot()

    assumptions: List[str] = []
    flow_elements = [elem for elem in root if local_name(elem.tag) == "flow"]
    subflow_elements = [
        elem
        for elem in root
        if local_name(elem.tag) in {"sub-flow", "subflow"}
    ]

    lookup = NodeLookup(
        flows={elem.attrib.get("name", ""): f"flow://{elem.attrib.get('name')}" for elem in flow_elements if elem.attrib.get("name")},
        subflows={elem.attrib.get("name", ""): f"subflow://{elem.attrib.get('name')}" for elem in subflow_elements if elem.attrib.get("name")},
        assumptions=assumptions,
    )

    flows = [
        parse_flow(elem, lookup, namespace_map)
        for elem in flow_elements
    ]
    subflows = [
        parse_subflow(elem, lookup, namespace_map)
        for elem in subflow_elements
    ]

    document: SchemaDict = {
        "schemaVersion": schema_version,
        "project": project,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "flows": flows,
        "subflows": subflows,
        "links": [],
    }
    if assumptions:
        document["assumptions"] = assumptions
    return document


def infer_project_name(path: str) -> str:
    """Return a fallback project name based on the file path."""
    parts = path.replace("\\", "/").rstrip("/").split("/")
    if parts:
        return parts[-1].rsplit(".", 1)[0]
    return "unknown"


def collect_namespaces(xml_content: str) -> Dict[str, str]:
    """Collect namespace URI to prefix mapping from the XML content."""
    namespace_map: Dict[str, str] = {}
    for event, data in ET.iterparse(StringIO(xml_content), events=("start-ns",)):
        prefix, uri = data
        # prefer first prefix that appears for a URI
        namespace_map.setdefault(uri, prefix)
    return namespace_map


def parse_flow(elem: ET.Element, lookup: NodeLookup, namespace_map: Dict[str, str]) -> SchemaDict:
    name = elem.attrib.get("name", "")
    flow_id = lookup.flows.get(name, f"flow://{name}")
    processors: List[SchemaDict] = []
    edges: List[SchemaDict] = []
    error_handler: Optional[SchemaDict] = None

    for idx, child in enumerate(child for child in elem if local_name(child.tag) != "error-handler"):
        result = parse_processor(idx, child, lookup, namespace_map)
        processors.append(result.processor)
        edges.extend(result.edges)

    for child in elem:
        if local_name(child.tag) == "error-handler":
            error_handler = parse_error_handler(child, lookup, namespace_map)
            break

    flow_dict: SchemaDict = {
        "id": flow_id,
        "name": name,
        "processors": processors,
        "edges": edges,
        "location": infer_location(elem),
    }
    source = parse_source(elem, namespace_map)
    if source:
        flow_dict["source"] = source
    if error_handler:
        flow_dict["errorHandler"] = error_handler
    flags = derive_flags(processors)
    if flags:
        flow_dict["flags"] = flags
    return flow_dict


def parse_subflow(elem: ET.Element, lookup: NodeLookup, namespace_map: Dict[str, str]) -> SchemaDict:
    name = elem.attrib.get("name", "")
    subflow_id = lookup.subflows.get(name, f"subflow://{name}")
    processors: List[SchemaDict] = []
    error_handler: Optional[SchemaDict] = None

    for idx, child in enumerate(child for child in elem if local_name(child.tag) != "error-handler"):
        result = parse_processor(idx, child, lookup, namespace_map)
        processors.append(result.processor)

    for child in elem:
        if local_name(child.tag) == "error-handler":
            error_handler = parse_error_handler(child, lookup, namespace_map)
            break

    subflow_dict: SchemaDict = {
        "id": subflow_id,
        "name": name,
        "processors": processors,
        "location": infer_location(elem),
    }
    if error_handler:
        subflow_dict["errorHandler"] = error_handler
    return subflow_dict


def parse_processor(idx: int, elem: ET.Element, lookup: NodeLookup, namespace_map: Dict[str, str]) -> ProcessorParseResult:
    processor: SchemaDict = {
        "idx": idx,
        "type": qualified_name(elem.tag, namespace_map),
    }
    config_ref = elem.attrib.get("config-ref")
    if config_ref:
        processor["configRef"] = config_ref

    attributes = build_attributes(elem.attrib, namespace_map, exclude_keys={"config-ref"})
    if attributes:
        processor["attributes"] = attributes

    dw_info = extract_dataweave(elem, namespace_map)
    if dw_info:
        processor["dw"] = dw_info

    branches, edges = extract_branches(elem, lookup, namespace_map)
    if branches:
        processor["branches"] = branches

    if local_name(elem.tag) == "flow-ref":
        name = elem.attrib.get("name")
        if name:
            target = lookup.resolve(name)
            edges.append({"to": target, "via": "flow-ref"})
    return ProcessorParseResult(processor=processor, edges=edges)


def build_attributes(
    attributes: Dict[str, str], namespace_map: Dict[str, str], *, exclude_keys: Iterable[str]
) -> Dict[str, str]:
    result: Dict[str, str] = {}
    excluded = set(exclude_keys)
    for key, value in attributes.items():
        if key in excluded:
            continue
        result[qualified_name(key, namespace_map)] = value
    return result


def extract_branches(
    elem: ET.Element, lookup: NodeLookup, namespace_map: Dict[str, str]
) -> Tuple[List[SchemaDict], List[SchemaDict]]:
    local = local_name(elem.tag)
    branches: List[SchemaDict] = []
    edges: List[SchemaDict] = []
    if local != "choice":
        return branches, edges

    for child in elem:
        child_local = local_name(child.tag)
        if child_local == "when":
            condition = child.attrib.get("expression") or child.attrib.get("condition")
            targets = collect_branch_targets(child, lookup)
            branch: SchemaDict = {"when": condition, "targets": targets}
            branches.append(branch)
            for target in targets:
                edges.append({"to": target, "via": "choice.when"})
        elif child_local == "otherwise":
            targets = collect_branch_targets(child, lookup)
            branch = {"otherwise": True, "targets": targets}
            branches.append(branch)
            for target in targets:
                edges.append({"to": target, "via": "choice.otherwise"})
    return branches, edges


def collect_branch_targets(elem: ET.Element, lookup: NodeLookup) -> List[str]:
    targets: List[str] = []
    for candidate in elem.iter():
        if local_name(candidate.tag) == "flow-ref":
            name = candidate.attrib.get("name")
            if name:
                targets.append(lookup.resolve(name))
    return targets


def extract_dataweave(elem: ET.Element, namespace_map: Dict[str, str]) -> Optional[SchemaDict]:
    qname = qualified_name(elem.tag, namespace_map)
    if not qname.startswith("ee:") and local_name(elem.tag) not in {"transform", "transform-message"}:
        return None

    scripts: List[str] = []
    mime_type: Optional[str] = None
    for node in elem.iter():
        node_local = local_name(node.tag)
        if node_local in {"set-payload", "set-variable", "set-property", "script"}:
            payload_text = (node.text or "").strip()
            if payload_text:
                scripts.append(payload_text)
            if "mimeType" in node.attrib:
                mime_type = node.attrib["mimeType"]
    if not scripts:
        return None

    body = "\n\n".join(scripts).strip()
    header = body.splitlines()[0].strip() if body else None
    version = None
    if header and header.startswith("%dw"):
        parts = header.split()
        if len(parts) >= 2:
            version = parts[1]

    dataweave: SchemaDict = {
        "bodyHash": sha1(body.encode("utf-8")).hexdigest(),
    }
    if version:
        dataweave["version"] = version
    if mime_type:
        dataweave["outputMime"] = mime_type
    if header:
        dataweave["header"] = header
    return dataweave


def parse_error_handler(elem: ET.Element, lookup: NodeLookup, namespace_map: Dict[str, str]) -> Optional[SchemaDict]:
    on_error_entries: List[SchemaDict] = []
    for child in elem:
        local = local_name(child.tag)
        if local not in {"on-error-continue", "on-error-propagate"}:
            continue
        entry: SchemaDict = {
            "type": local,
        }
        when_attr = child.attrib.get("when") or child.attrib.get("type")
        if when_attr:
            entry["when"] = when_attr
        status = child.attrib.get("statusCode")
        if status:
            try:
                entry["setsStatus"] = int(status)
            except ValueError:
                pass
        for candidate in child.iter():
            if local_name(candidate.tag) == "flow-ref":
                name = candidate.attrib.get("name")
                if name:
                    entry["target"] = lookup.resolve(name)
                    break
        on_error_entries.append(entry)

    if not on_error_entries:
        return None
    return {
        "onError": on_error_entries,
        "default": "none",
    }


def parse_source(elem: ET.Element, namespace_map: Dict[str, str]) -> Optional[SchemaDict]:
    if not list(elem):
        return None
    first = elem[0]
    source: SchemaDict = {
        "type": qualified_name(first.tag, namespace_map),
    }
    config_ref = first.attrib.get("config-ref")
    if config_ref:
        source["configRef"] = config_ref
    optional_keys = ["path", "queue", "cron", "responseTimeout"]
    for key in optional_keys:
        value = first.attrib.get(key)
        if value:
            normalized = "responseTimeoutMs" if key == "responseTimeout" else key
            source[normalized] = int(value) if normalized.endswith("Ms") else value
    transaction = extract_transaction(first.attrib)
    if transaction:
        source["transaction"] = transaction
    methods = first.attrib.get("methods")
    if methods:
        source["methods"] = [method.strip() for method in methods.split(",") if method.strip()]
    path_attr = first.attrib.get("path") or first.attrib.get("destination")
    if path_attr and "path" not in source:
        source["path"] = path_attr
    return source


def extract_transaction(attributes: Dict[str, str]) -> Optional[SchemaDict]:
    trans_type = attributes.get("transactionType") or attributes.get("transaction")
    action = attributes.get("transactionAction")
    if not trans_type and not action:
        return None
    transaction: SchemaDict = {}
    if trans_type:
        normalized = trans_type.upper()
        if normalized in {"NONE", "LOCAL", "XA"}:
            transaction["type"] = normalized
    if action:
        normalized_action = action.upper()
        mapping = {
            "ALWAYS_BEGIN": "ALWAYS_BEGIN",
            "BEGIN_OR_JOIN": "BEGIN_OR_JOIN",
            "NONE": "NONE",
        }
        if normalized_action in mapping:
            transaction["action"] = mapping[normalized_action]
    return transaction or None


def derive_flags(processors: List[SchemaDict]) -> Optional[SchemaDict]:
    flags: SchemaDict = {}
    for processor in processors:
        attributes = processor.get("attributes", {})
        if "maxConcurrency" in attributes:
            try:
                value = int(attributes["maxConcurrency"])
                if value > 0:
                    flags["parallelism"] = value
            except ValueError:
                continue
        if processor.get("dw"):
            flags["hasBlockingDW"] = True
    return flags or None


def infer_location(elem: ET.Element) -> str:
    sourceline = getattr(elem, "sourceline", None)
    if sourceline:
        return f"line:{sourceline}"
    name = elem.attrib.get("name")
    if name:
        return f"flow:{name}"
    return "unknown"


def qualified_name(tag: str, namespace_map: Dict[str, str]) -> str:
    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        prefix = namespace_map.get(uri)
        if prefix:
            return f"{prefix}:{local}"
        return local
    return tag


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag
