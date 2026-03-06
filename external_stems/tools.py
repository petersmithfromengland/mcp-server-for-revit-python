# -*- coding: utf-8 -*-
"""
MCP tools for external stems — browsing, searching, and composing
code from indexed external libraries and the Revit API documentation.

Library paths are read from ``config.yaml`` in the repository root.
"""

import os
from typing import Optional

from .config import load_config, get_cache_dir
from .indexer import (
    LibraryIndex,
    FunctionInfo,
    load_index,
    index_library,
    save_index,
)
from .code_composer import (
    compose_script,
    compose_explanation,
    read_function_source as _read_function_source,
)
from .revit_api_index import (
    RevitApiIndex,
    ApiMember,
    build_revit_api_index,
    save_api_index,
    load_api_index,
)
from code_execution.pending import store_pending

# ── Extension root path ───────────────────────────────────────────
_EXTENSION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Singleton indexes ──────────────────────────────────────────────
_lib_indexes: dict = {}  # name -> LibraryIndex
_api_index: Optional[RevitApiIndex] = None


def _cache_path(name: str) -> str:
    """Return the path to a library's cache file."""
    return os.path.join(get_cache_dir(), f"{name.lower()}_index.json")


def _get_index(name: str = None) -> LibraryIndex:
    """Get or build a library index.

    If *name* is None, returns the first enabled library.
    """
    cfg = load_config()

    if name is None:
        # Default to first enabled library
        for lib in cfg.libraries:
            if lib.enabled:
                name = lib.name
                break
        if name is None:
            raise RuntimeError(
                "No external libraries configured.  "
                "Add entries to config.yaml under external_stems.libraries."
            )

    if name in _lib_indexes:
        return _lib_indexes[name]

    # Find library config
    lib_cfg = None
    for lib in cfg.libraries:
        if lib.name == name:
            lib_cfg = lib
            break
    if lib_cfg is None:
        raise RuntimeError(f"Library '{name}' not found in config.yaml")
    if not lib_cfg.enabled:
        raise RuntimeError(f"Library '{name}' is disabled in config.yaml")

    cache = _cache_path(name)
    if os.path.exists(cache):
        idx = load_index(cache)
        _lib_indexes[name] = idx
        return idx

    # First run: build from source
    idx = index_library(lib_cfg.path, name)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    save_index(idx, cache)
    _lib_indexes[name] = idx
    return idx


def _get_api_index() -> RevitApiIndex:
    """Get or build the Revit API documentation index."""
    global _api_index
    if _api_index is not None:
        return _api_index

    cfg = load_config()
    xml_path = cfg.revit_api_xml
    if not xml_path:
        xml_path = os.path.join(_EXTENSION_DIR, "tools", "RevitAPI.xml")

    cache = os.path.join(get_cache_dir(), "revit_api_index.json")

    if os.path.exists(cache):
        _api_index = load_api_index(cache)
        return _api_index

    _api_index = build_revit_api_index(xml_path)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    save_api_index(_api_index, cache)
    return _api_index


def _func_summary(func: FunctionInfo) -> str:
    """One-line summary of a function for listing."""
    params = ", ".join(p.get("name", "?") for p in func.parameters)
    doc = ""
    if func.docstring:
        doc = " — " + func.docstring.strip().split("\n")[0][:80]
    tx = " [modifies model]" if func.requires_transaction else ""
    cls = f" [{func.class_name}]" if func.class_name else ""
    return f"{func.module_path}.{func.name}({params}){cls}{tx}{doc}"


def _format_member_brief(m: ApiMember) -> str:
    """One-line summary for API member listings."""
    kind_tag = f"[{m.kind}]"
    sig = ""
    if m.kind == "method" and m.parameters:
        sig = "(" + ", ".join(p.name for p in m.parameters) + ")"
    elif m.kind == "method":
        sig = "()"
    summary = ""
    if m.summary:
        summary = " — " + m.summary[:100]
    return f"  {kind_tag:10s} {m.full_name}{sig}{summary}"


def _format_member_detail(m: ApiMember) -> str:
    """Full detail view of a single API member."""
    lines = []
    lines.append(f"=== {m.kind.upper()}: {m.full_name} ===")
    if m.since:
        lines.append(f"Since: Revit {m.since}")
    if m.summary:
        lines.append(f"\nSummary: {m.summary}")
    if m.remarks:
        lines.append(f"\nRemarks: {m.remarks}")
    if m.kind == "method" and m.signature:
        lines.append(f"\nSignature: {m.short_name}{m.signature}")
    if m.parameters:
        lines.append("\nParameters:")
        for p in m.parameters:
            lines.append(f"  - {p.name}: {p.description}")
    if m.returns:
        lines.append(f"\nReturns: {m.returns}")
    if m.exceptions:
        lines.append("\nExceptions:")
        for exc in m.exceptions:
            lines.append(f"  - {exc.type_name}: {exc.description}")
    return "\n".join(lines)


# ── MCP tool registration ─────────────────────────────────────────


def register_external_stem_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register all external stem tools with the MCP server."""
    _ = revit_get, revit_post, revit_image  # interface consistency

    # ── Library browsing tools ─────────────────────────────────

    @mcp.tool()
    async def search_external_stems(
        query: str,
        library: str = "",
        category: str = "",
        max_results: int = 20,
    ) -> str:
        """
        Search external stem libraries for functions and classes.

        External stems are indexed from Python libraries configured in
        config.yaml (e.g. duHast).  Use this to find existing utility
        functions before writing code from scratch.

        Args:
            query: Search term (e.g. 'wall', 'delete', 'workset', 'purge')
            library: Library name filter (e.g. 'duHast').  Leave empty
                     to search the default library.
            category: Optional category filter (e.g. 'Walls', 'Views')
            max_results: Maximum results to return (default 20)
        """
        try:
            index = _get_index(library or None)
        except RuntimeError as e:
            return str(e)

        if category:
            results = [
                f
                for f in index.get_by_category(category)
                if query.lower() in f.name.lower()
                or (f.docstring and query.lower() in f.docstring.lower())
                or query.lower() in f.module_path.lower()
            ][:max_results]
        else:
            results = index.search(query, max_results)

        if not results:
            return (
                f"No external functions found for '{query}'."
                " Try broader terms or check categories with"
                " list_external_stem_categories."
            )

        lines = [f"Found {len(results)} result(s) for '{query}':\n"]
        for func in results:
            lines.append(f"  - {_func_summary(func)}")

        lines.append(
            "\nUse read_external_stem with the full function path"
            " to see the source code."
        )
        return "\n".join(lines)

    @mcp.tool()
    async def list_external_stem_categories(
        library: str = "",
    ) -> str:
        """
        List all categories in an external stem library with function counts.

        Args:
            library: Library name (e.g. 'duHast'). Leave empty for default.
        """
        try:
            index = _get_index(library or None)
        except RuntimeError as e:
            return str(e)

        categories: dict = {}
        for func in index._function_lookup.values():
            cat = func.category or "Uncategorized"
            if cat not in categories:
                categories[cat] = {"total": 0, "with_doc": 0, "modifying": 0}
            categories[cat]["total"] += 1
            if func.requires_doc:
                categories[cat]["with_doc"] += 1
            if func.requires_transaction:
                categories[cat]["modifying"] += 1

        lines = [f"{index.name} Library — {index.total_functions} indexed functions\n"]
        for cat in sorted(categories.keys()):
            info = categories[cat]
            lines.append(
                f"  {cat}: {info['total']} functions "
                f"({info['with_doc']} use doc, "
                f"{info['modifying']} modify model)"
            )

        lines.append(
            "\nUse search_external_stems with a category or keyword to drill in."
        )
        return "\n".join(lines)

    @mcp.tool()
    async def read_external_stem(
        function_path: str,
        library: str = "",
    ) -> str:
        """
        Read the full source code of an external stem function.

        Use this after search_external_stems to inspect a function before
        using it in compose_external_stem.

        Args:
            function_path: Full dotted path as shown by search, e.g.
                'duHast.Revit.Walls.walls.get_all_wall_types'
            library: Library name (e.g. 'duHast'). Leave empty for default.
        """
        try:
            index = _get_index(library or None)
        except RuntimeError as e:
            return str(e)

        func = index._function_lookup.get(function_path)
        if not func:
            search_name = function_path.split(".")[-1]
            candidates = [
                k for k in index._function_lookup if search_name.lower() in k.lower()
            ]
            if candidates:
                return (
                    f"Function '{function_path}' not found. Did you mean:\n"
                    + "\n".join(f"  - {c}" for c in candidates[:10])
                )
            return f"Function '{function_path}' not found in library index."

        source = _read_function_source(func)
        if not source:
            return f"Could not read source for {function_path} from {func.file_path}"

        header = [
            f"# Source: {func.file_path}:{func.line_number}",
            f"# Module: {func.module_path}",
        ]
        if func.docstring:
            first_line = func.docstring.strip().split("\n")[0]
            header.append(f"# {first_line}")
        if func.requires_transaction:
            header.append(
                "# WARNING: This function modifies the model (requires transaction)"
            )
        return "\n".join(header) + "\n\n" + source

    @mcp.tool()
    async def compose_external_stem(
        function_paths: str,
        call_code: str,
        library: str = "",
        include_transaction: bool = False,
        transaction_name: str = "MCP Operation",
    ) -> str:
        """
        Compose a self-contained IronPython script by inlining external
        stem functions.

        ⚠ WORKFLOW REQUIREMENT: Call plan_revit_action FIRST.  This tool
        is used in Step 3/4 of the mandatory workflow when internal stems
        alone cannot satisfy the request.

        This does NOT execute the code — it returns the full script with
        provenance for user review.  The generated script is self-contained
        and does not require the external library to be installed in Revit.

        After the user reviews and approves, pass the code_id to
        execute_revit_code to run it.

        ╔══════════════════════════════════════════════════════════╗
        ║  DISPLAY RULES — you MUST follow ALL of these:          ║
        ║                                                          ║
        ║  1. Display the COMPLETE code block from this tool's     ║
        ║     response to the user VERBATIM — never summarise,     ║
        ║     truncate, paraphrase, or rewrite the code.           ║
        ║  2. Include the Code ID so the user can see it.          ║
        ║  3. Ask the user to review and approve before executing. ║
        ║  4. Do NOT call execute_revit_code until the user says   ║
        ║     yes.  Silence is not approval.                       ║
        ╚══════════════════════════════════════════════════════════╝

        PROVENANCE: This tool automatically embeds a provenance
        comment block at the top of every composed script, listing
        the source library, inlined function paths, and whether the
        script modifies the model.  The provenance block is part of
        the code and MUST be included when you display it.

        Args:
            function_paths: Comma-separated full dotted paths, e.g.
                'duHast.Revit.Walls.walls.get_all_wall_types'
            call_code: Python code that calls the inlined functions.
            library: Library name (e.g. 'duHast'). Leave empty for default.
            include_transaction: Wrap in a Transaction (for model-modifying code).
            transaction_name: Name shown in Revit undo history.

        Returns:
            The composed script with provenance for user review.
            You MUST display the full code block to the user and wait
            for explicit approval.
        """
        try:
            index = _get_index(library or None)
        except RuntimeError as e:
            return str(e)

        paths = [p.strip() for p in function_paths.split(",") if p.strip()]
        functions = []
        missing = []
        for path in paths:
            func = index._function_lookup.get(path)
            if func:
                functions.append(func)
            else:
                missing.append(path)
        if missing:
            return (
                "ERROR: Functions not found in index:\n"
                + "\n".join(f"  - {m}" for m in missing)
                + "\n\nUse search_external_stems to find the correct paths."
            )

        needs_tx = any(f.requires_transaction for f in functions)
        warning = ""
        if needs_tx and not include_transaction:
            modifying = [f.name for f in functions if f.requires_transaction]
            warning = (
                "WARNING: These functions modify the model but "
                "include_transaction=False:\n"
                + "\n".join(f"  - {n}" for n in modifying)
                + "\n\nSet include_transaction=True if this code "
                "makes changes.\n\n"
            )

        script = compose_script(
            functions=functions,
            call_code=call_code,
            index=index,
            include_transaction=include_transaction,
            transaction_name=transaction_name,
        )
        explanation = compose_explanation(
            functions=functions,
            call_code=call_code,
            include_transaction=include_transaction,
        )

        func_names = ", ".join(f.name for f in functions)
        desc = f"External stem: {func_names}"
        code_id = store_pending(script, desc, source=f"external:{library or 'default'}")

        return (
            f"{warning}## Prepared Code — awaiting your approval\n\n"
            f"{explanation}\n\n"
            f"**Code ID:** `{code_id}`\n\n"
            f"```python\n{script}\n```\n\n"
            f"---\n\n"
            f"⚠ **DISPLAY INSTRUCTION:** You MUST include the COMPLETE "
            f"code block above in your message to the user — do NOT "
            f"summarise, truncate, or rewrite it.  The user needs to "
            f"see the exact code that will be executed.\n\n"
            f"Ask the user: *Please review the code above.  "
            f"Shall I go ahead and execute it?*"
        )

    @mcp.tool()
    async def list_external_stem_module(
        module_path: str,
        library: str = "",
    ) -> str:
        """
        List all public functions and classes in a specific external module.

        Args:
            module_path: Dotted module path or partial match, e.g.
                'duHast.Revit.Walls.walls' or just 'Walls.walls'
            library: Library name (e.g. 'duHast'). Leave empty for default.
        """
        try:
            index = _get_index(library or None)
        except RuntimeError as e:
            return str(e)

        matches = [m for m in index.modules if module_path in m.module_path]
        if not matches:
            available = sorted(set(m.module_path for m in index.modules))
            return (
                f"Module '{module_path}' not found. Available modules:\n"
                + "\n".join(f"  - {m}" for m in available[:40])
            )

        lines = []
        for mod in matches:
            lines.append(f"\n=== {mod.module_path} ===")
            if mod.docstring:
                first_line = mod.docstring.strip().split("\n")[0]
                lines.append(f"  {first_line}")
            lines.append("")
            if mod.functions:
                lines.append("  Functions:")
                for func in mod.functions:
                    lines.append(f"    - {_func_summary(func)}")
            if mod.classes:
                lines.append("  Classes:")
                for cls in mod.classes:
                    doc = ""
                    if cls.docstring:
                        doc = " — " + cls.docstring.strip().split("\n")[0][:60]
                    lines.append(f"    - {cls.name}{doc}")
                    for method in cls.methods:
                        params = ", ".join(
                            p.get("name", "?") for p in method.parameters
                        )
                        lines.append(f"        .{method.name}({params})")
        return "\n".join(lines)

    @mcp.tool()
    async def rebuild_external_stem_index(
        library: str = "",
    ) -> str:
        """
        Rebuild an external stem library index from source files.

        Use this after the external library has been updated or if the
        index seems stale.

        Args:
            library: Library name (e.g. 'duHast'). Leave empty for default.
        """
        cfg = load_config()
        name = library or None
        if name is None:
            for lib in cfg.libraries:
                if lib.enabled:
                    name = lib.name
                    break
        if name is None:
            return "No external libraries configured in config.yaml."

        # Clear cached index
        if name in _lib_indexes:
            del _lib_indexes[name]
        cache = _cache_path(name)
        if os.path.exists(cache):
            os.remove(cache)

        try:
            index = _get_index(name)
        except RuntimeError as e:
            return str(e)

        return (
            f"Index rebuilt: {len(index.modules)} modules, "
            f"{index.total_functions} functions indexed."
        )

    @mcp.tool()
    async def list_configured_libraries() -> str:
        """
        List all external stem libraries configured in config.yaml.

        Shows the name, path, and enabled status of each library.
        """
        cfg = load_config()
        if not cfg.libraries:
            return (
                "No external libraries configured.\n"
                "Add entries to config.yaml under external_stems.libraries."
            )

        lines = ["Configured external stem libraries:\n"]
        for lib in cfg.libraries:
            status = "✓ enabled" if lib.enabled else "✗ disabled"
            exists = "exists" if os.path.isdir(lib.path) else "PATH NOT FOUND"
            lines.append(f"  {lib.name}: {lib.path}")
            lines.append(f"    Status: {status} | {exists}")

        if cfg.revit_api_xml:
            exists = "exists" if os.path.isfile(cfg.revit_api_xml) else "NOT FOUND"
            lines.append(f"\nRevit API XML: {cfg.revit_api_xml} ({exists})")

        return "\n".join(lines)

    # ── Revit API documentation tools ──────────────────────────

    @mcp.tool()
    async def search_revit_api(
        query: str,
        kind: str = "",
        namespace: str = "",
        max_results: int = 25,
    ) -> str:
        """
        Search the official Revit API documentation for classes, methods,
        properties, enums, and fields.

        Use this BEFORE writing Revit code to find correct class names,
        method signatures, property names, and enum values.

        Args:
            query: Search term (e.g. 'Wall', 'FilteredElementCollector',
                'Transaction', 'BuiltInCategory')
            kind: Filter by member kind: 'type', 'method', 'property',
                'field', 'event', or '' for all
            namespace: Filter by namespace prefix
            max_results: Maximum results to return (default 25)
        """
        index = _get_api_index()
        results = index.search(
            query, kind=kind, namespace=namespace, max_results=max_results
        )
        if not results:
            return (
                f"No Revit API members found for '{query}'."
                " Try broader terms or check a specific namespace."
            )
        lines = [f"Found {len(results)} result(s) for '{query}':\n"]
        for m in results:
            lines.append(_format_member_brief(m))
        lines.append(
            "\nUse get_revit_api_class to see all members of a class,"
            " or get_revit_api_member for full details."
        )
        return "\n".join(lines)

    @mcp.tool()
    async def get_revit_api_class(
        class_name: str,
        kind: str = "",
    ) -> str:
        """
        Get all members of a Revit API class or enum.

        Args:
            class_name: Full or short class name (e.g. 'Wall',
                'Autodesk.Revit.DB.FilteredElementCollector')
            kind: Filter by kind: 'method', 'property', 'field', 'event'
        """
        index = _get_api_index()

        type_info = index.get_type(class_name)
        lookup_name = class_name

        if type_info is None and "." not in class_name:
            for prefix in [
                "Autodesk.Revit.DB",
                "Autodesk.Revit.DB.Architecture",
                "Autodesk.Revit.DB.Structure",
                "Autodesk.Revit.DB.Mechanical",
                "Autodesk.Revit.DB.Electrical",
                "Autodesk.Revit.DB.Plumbing",
                "Autodesk.Revit.UI",
            ]:
                candidate = f"{prefix}.{class_name}"
                type_info = index.get_type(candidate)
                if type_info:
                    lookup_name = candidate
                    break

        if type_info is None:
            results = index.search(class_name, kind="type", max_results=10)
            if results:
                return f"Class '{class_name}' not found. Did you mean:\n" + "\n".join(
                    f"  - {r.full_name}: {r.summary[:80]}" for r in results
                )
            return f"Class '{class_name}' not found in the Revit API."

        lines = [_format_member_detail(type_info)]
        members = index.get_class_members(lookup_name, kind=kind)
        if not members:
            lines.append(f"\nNo {'matching ' if kind else ''}members found.")
            return "\n".join(lines)

        by_kind = {}
        for m in members:
            by_kind.setdefault(m.kind, []).append(m)
        for k in ["property", "method", "field", "event"]:
            ms = by_kind.get(k, [])
            if not ms:
                continue
            lines.append(f"\n--- {k.upper()}S ({len(ms)}) ---")
            for m in sorted(ms, key=lambda x: x.short_name):
                sig = ""
                if k == "method" and m.parameters:
                    sig = "(" + ", ".join(p.name for p in m.parameters) + ")"
                elif k == "method":
                    sig = "()"
                doc = f" — {m.summary[:80]}" if m.summary else ""
                lines.append(f"  {m.short_name}{sig}{doc}")
        return "\n".join(lines)

    @mcp.tool()
    async def get_revit_api_member(
        member_name: str,
    ) -> str:
        """
        Get detailed documentation for a specific Revit API member.

        Args:
            member_name: Full member name, e.g.
                'Autodesk.Revit.DB.Wall.Create'
        """
        index = _get_api_index()
        member = index._by_full_name.get(member_name)
        if member is None and "." not in member_name:
            member = index._by_full_name.get(f"Autodesk.Revit.DB.{member_name}")
        if member is None:
            results = index.search(member_name, max_results=10)
            if results:
                return f"Member '{member_name}' not found. Did you mean:\n" + "\n".join(
                    _format_member_brief(r) for r in results
                )
            return f"Member '{member_name}' not found in the Revit API."

        output = _format_member_detail(member)

        if member.kind == "method":
            overloads = [
                m
                for m in index.members
                if m.full_name == member.full_name
                and m.raw_name != member.raw_name
                and m.kind == "method"
            ]
            if overloads:
                output += f"\n\n--- OVERLOADS ({len(overloads)}) ---"
                for ol in overloads:
                    sig = ol.signature or "()"
                    doc = f" — {ol.summary[:80]}" if ol.summary else ""
                    output += f"\n  {ol.short_name}{sig}{doc}"
                    if ol.parameters:
                        for p in ol.parameters:
                            output += f"\n    - {p.name}: {p.description[:60]}"
        return output

    @mcp.tool()
    async def get_revit_api_enum(
        enum_name: str,
    ) -> str:
        """
        Get all values of a Revit API enum.

        Args:
            enum_name: Full or short enum name (e.g. 'WallKind', 'ViewType',
                'Autodesk.Revit.DB.BuiltInCategory')
        """
        index = _get_api_index()
        type_info = index.get_type(enum_name)
        lookup_name = enum_name

        if type_info is None and "." not in enum_name:
            for prefix in [
                "Autodesk.Revit.DB",
                "Autodesk.Revit.DB.Architecture",
                "Autodesk.Revit.DB.Structure",
            ]:
                candidate = f"{prefix}.{enum_name}"
                type_info = index.get_type(candidate)
                if type_info:
                    lookup_name = candidate
                    break
        if type_info is None:
            results = index.search(enum_name, kind="type", max_results=10)
            if results:
                return f"Enum '{enum_name}' not found. Did you mean:\n" + "\n".join(
                    f"  - {r.full_name}: {r.summary[:80]}" for r in results
                )
            return f"Enum '{enum_name}' not found."

        fields = index.get_enum_values(lookup_name)
        if not fields:
            return (
                f"{lookup_name} exists but has no field values."
                " It may not be an enum — use get_revit_api_class instead."
            )
        lines = [f"=== ENUM: {lookup_name} ==="]
        if type_info.summary:
            lines.append(f"{type_info.summary}")
        lines.append(f"\nValues ({len(fields)}):")
        for f in sorted(fields, key=lambda x: x.short_name):
            doc = f" — {f.summary[:100]}" if f.summary else ""
            lines.append(f"  {f.short_name}{doc}")
        return "\n".join(lines)

    @mcp.tool()
    async def list_revit_api_namespaces() -> str:
        """
        List all namespaces in the Revit API with member counts.
        """
        index = _get_api_index()
        namespaces = index.get_namespaces()
        lines = [
            f"Revit API — {index.total_members} members,"
            f" {index.total_types} types\n"
        ]
        for ns in sorted(namespaces.keys()):
            lines.append(f"  {ns}: {namespaces[ns]} members")
        lines.append("\nUse search_revit_api with namespace filter to explore.")
        return "\n".join(lines)

    @mcp.tool()
    async def rebuild_revit_api_index() -> str:
        """
        Rebuild the Revit API index from the XML documentation file.
        """
        global _api_index
        _api_index = None

        cache = os.path.join(get_cache_dir(), "revit_api_index.json")
        if os.path.exists(cache):
            os.remove(cache)

        index = _get_api_index()
        return (
            f"Revit API index rebuilt: {index.total_members} members,"
            f" {index.total_types} types."
        )
