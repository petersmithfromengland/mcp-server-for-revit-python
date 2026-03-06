# -*- coding: utf-8 -*-
"""
Revit API XML documentation parser and index.

Parses the .NET XML documentation file (RevitAPI.xml) shipped with the
Revit SDK and builds a searchable, in-memory index of every type,
method, property, field, and event in the Revit API.

The index supports:
- Full-text search across class/member names and summaries
- Lookup by fully-qualified name
- Browsing members of a specific class
- Filtering by member kind (type, method, property, field, event)
- Namespace browsing
"""

import os
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Set


# ── Data classes ───────────────────────────────────────────────────


@dataclass
class ApiParam:
    """A parameter on a method."""

    name: str
    description: str = ""


@dataclass
class ApiException:
    """An exception a method can throw."""

    type_name: str  # e.g. "Autodesk.Revit.Exceptions.ArgumentException"
    description: str = ""


@dataclass
class ApiMember:
    """A single member from the Revit API XML docs."""

    raw_name: str  # full XML name attr, e.g. "M:Autodesk.Revit.DB.Wall.Create(...)"
    kind: str  # "type", "method", "property", "field", "event"
    full_name: str  # qualified name without prefix/params
    short_name: str  # just the member name (e.g. "Create")
    parent_type: str  # owning class/enum (e.g. "Autodesk.Revit.DB.Wall")
    namespace: str  # e.g. "Autodesk.Revit.DB"
    summary: str = ""
    remarks: str = ""
    returns: str = ""
    since: str = ""
    parameters: List[ApiParam] = field(default_factory=list)
    exceptions: List[ApiException] = field(default_factory=list)
    signature: str = ""  # method signature from the raw name


KIND_MAP = {
    "T": "type",
    "M": "method",
    "P": "property",
    "F": "field",
    "E": "event",
}


# ── XML text extraction ───────────────────────────────────────────


def _get_text(element) -> str:
    """Extract all text content from an XML element, including tails
    of child elements (for inline tags like <see>, <list>, etc.)."""
    if element is None:
        return ""
    parts = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        # Include text of <see cref="..."/> as the cref value
        if child.tag == "see" and child.get("cref"):
            cref = child.get("cref", "")
            # Strip the T:/M:/P: prefix
            if ":" in cref:
                cref = cref.split(":", 1)[1]
            parts.append(cref)
        elif child.tag == "paramref" and child.get("name"):
            parts.append(child.get("name", ""))
        elif child.text:
            parts.append(child.text.strip())
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(parts)


# ── Parsing ────────────────────────────────────────────────────────


def _parse_member_name(raw_name: str):
    """Parse the XML member name attribute into components.

    Examples:
        "T:Autodesk.Revit.DB.Wall"
        "M:Autodesk.Revit.DB.Wall.Create(Autodesk.Revit.DB.Document,...)"
        "P:Autodesk.Revit.DB.Wall.Width"
        "F:Autodesk.Revit.DB.WallKind.Basic"
    """
    if ":" not in raw_name:
        return None, raw_name, raw_name, "", "", ""

    kind_char, full = raw_name.split(":", 1)
    kind = KIND_MAP.get(kind_char, kind_char)

    # Strip method signature for dotted-name parsing
    signature = ""
    paren_idx = full.find("(")
    if paren_idx != -1:
        signature = full[paren_idx:]
        dotted = full[:paren_idx]
    else:
        dotted = full

    # Split into parent + short name
    parts = dotted.rsplit(".", 1)
    if len(parts) == 2:
        parent_type = parts[0]
        short_name = parts[1]
    else:
        parent_type = ""
        short_name = dotted

    # For types, the full_name IS the type itself
    if kind == "type":
        parent_type = dotted
        short_name = dotted.rsplit(".", 1)[-1]

    # Namespace
    ns_parts = parent_type.rsplit(".", 1)
    namespace = ns_parts[0] if len(ns_parts) == 2 else ""

    return kind, dotted, short_name, parent_type, namespace, signature


def parse_revit_api_xml(xml_path: str) -> List[ApiMember]:
    """Parse RevitAPI.xml and return a list of ApiMember objects."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    members = []

    for elem in root.findall(".//member"):
        raw_name = elem.get("name", "")
        if not raw_name:
            continue

        kind, full_name, short_name, parent_type, namespace, signature = (
            _parse_member_name(raw_name)
        )
        if kind is None:
            continue

        member = ApiMember(
            raw_name=raw_name,
            kind=kind,
            full_name=full_name,
            short_name=short_name,
            parent_type=parent_type,
            namespace=namespace,
            summary=_get_text(elem.find("summary")),
            remarks=_get_text(elem.find("remarks")),
            returns=_get_text(elem.find("returns")),
            since=_get_text(elem.find("since")),
            signature=signature,
        )

        # Parameters
        for p in elem.findall("param"):
            member.parameters.append(
                ApiParam(
                    name=p.get("name", ""),
                    description=_get_text(p),
                )
            )

        # Exceptions
        for exc in elem.findall("exception"):
            cref = exc.get("cref", "")
            if ":" in cref:
                cref = cref.split(":", 1)[1]
            member.exceptions.append(
                ApiException(type_name=cref, description=_get_text(exc))
            )

        members.append(member)

    return members


# ── Index ──────────────────────────────────────────────────────────


class RevitApiIndex:
    """Searchable index of the Revit API documentation."""

    def __init__(self, members: List[ApiMember]):
        self.members = members

        # Lookup by full name (e.g. "Autodesk.Revit.DB.Wall")
        self._by_full_name: Dict[str, ApiMember] = {}
        # Lookup by raw XML name
        self._by_raw_name: Dict[str, ApiMember] = {}
        # Members grouped by parent type
        self._by_parent: Dict[str, List[ApiMember]] = {}
        # Types (T: entries) only
        self._types: Dict[str, ApiMember] = {}
        # By kind
        self._by_kind: Dict[str, List[ApiMember]] = {}
        # By namespace
        self._by_namespace: Dict[str, List[ApiMember]] = {}

        self._build()

    def _build(self):
        for m in self.members:
            self._by_full_name[m.full_name] = m
            self._by_raw_name[m.raw_name] = m

            if m.parent_type:
                self._by_parent.setdefault(m.parent_type, []).append(m)

            if m.kind == "type":
                self._types[m.full_name] = m

            self._by_kind.setdefault(m.kind, []).append(m)

            if m.namespace:
                self._by_namespace.setdefault(m.namespace, []).append(m)

    @property
    def total_members(self) -> int:
        return len(self.members)

    @property
    def total_types(self) -> int:
        return len(self._types)

    def get_type(self, type_name: str) -> Optional[ApiMember]:
        """Get a type definition by its full name."""
        return self._types.get(type_name)

    def get_class_members(self, type_name: str, kind: str = "") -> List[ApiMember]:
        """Get all members of a class/type.

        Args:
            type_name: Full class name, e.g. 'Autodesk.Revit.DB.Wall'
            kind: Filter by kind ('method', 'property', 'field', 'event')
        """
        members = self._by_parent.get(type_name, [])
        if kind:
            members = [m for m in members if m.kind == kind]
        return members

    def get_namespaces(self) -> Dict[str, int]:
        """Get all namespaces with member counts."""
        return {ns: len(ms) for ns, ms in self._by_namespace.items()}

    def search(
        self,
        query: str,
        kind: str = "",
        namespace: str = "",
        max_results: int = 25,
    ) -> List[ApiMember]:
        """Search the API index.

        Args:
            query: Search term (matched against name and summary)
            kind: Filter by kind ('type', 'method', 'property', 'field', 'event')
            namespace: Filter by namespace prefix
            max_results: Maximum results to return
        """
        query_lower = query.lower()
        query_parts = query_lower.split()
        results = []

        scope = self.members
        if kind:
            scope = self._by_kind.get(kind, [])

        for m in scope:
            if namespace and not m.namespace.lower().startswith(namespace.lower()):
                continue

            score = 0

            # Exact short name match
            if m.short_name.lower() == query_lower:
                score += 50
            # Short name contains query
            elif query_lower in m.short_name.lower():
                score += 20
            # Full name contains query
            elif query_lower in m.full_name.lower():
                score += 10
            # Summary contains query
            elif m.summary and query_lower in m.summary.lower():
                score += 5

            # Multi-word: check all parts present
            if score == 0 and len(query_parts) > 1:
                text = f"{m.full_name} {m.summary}".lower()
                if all(part in text for part in query_parts):
                    score += 8

            if score > 0:
                # Boost types
                if m.kind == "type":
                    score += 5
                results.append((score, m))

        results.sort(key=lambda x: (-x[0], x[1].full_name))
        return [m for _, m in results[:max_results]]

    def get_enum_values(self, enum_name: str) -> List[ApiMember]:
        """Get all field values of an enum type."""
        return [m for m in self._by_parent.get(enum_name, []) if m.kind == "field"]


# ── Persistence ────────────────────────────────────────────────────


def save_api_index(index: RevitApiIndex, output_path: str) -> None:
    """Save the API index to a compact JSON file."""
    data = {
        "total_members": index.total_members,
        "total_types": index.total_types,
        "members": [asdict(m) for m in index.members],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), default=str)


def load_api_index(index_path: str) -> RevitApiIndex:
    """Load a previously saved API index from JSON."""
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _valid = set(ApiMember.__dataclass_fields__)
    members = []
    for md in data["members"]:
        params = [ApiParam(**p) for p in md.pop("parameters", [])]
        exceptions = [ApiException(**e) for e in md.pop("exceptions", [])]
        cleaned = {k: v for k, v in md.items() if k in _valid}
        m = ApiMember(**cleaned, parameters=params, exceptions=exceptions)
        members.append(m)

    return RevitApiIndex(members)


# ── Convenience builder ────────────────────────────────────────────


def build_revit_api_index(xml_path: str) -> RevitApiIndex:
    """Parse the XML and build the index in one step."""
    members = parse_revit_api_xml(xml_path)
    return RevitApiIndex(members)
