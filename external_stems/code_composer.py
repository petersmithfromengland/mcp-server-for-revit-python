# -*- coding: utf-8 -*-
"""
Code composer — reads library source files and composes executable
IronPython scripts that inline the needed functions.

Since pyRevit's IronPython environment can't pip-install duHast,
this module reads the source of referenced functions and inlines
them into the generated script.
"""

import ast
import os
from typing import List, Set, Optional, Dict

from .indexer import FunctionInfo, LibraryIndex


def read_function_source(func: FunctionInfo) -> Optional[str]:
    """Read the raw source code of a function from its file."""
    try:
        with open(func.file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        tree = ast.parse(source)
        lines = source.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func.name:
                if hasattr(node, "end_lineno") and node.end_lineno:
                    start = node.lineno - 1
                    end = node.end_lineno
                    return "\n".join(lines[start:end])
        return None
    except Exception:
        return None


def read_class_source(file_path: str, class_name: str) -> Optional[str]:
    """Read the raw source code of a class from its file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        tree = ast.parse(source)
        lines = source.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                if hasattr(node, "end_lineno") and node.end_lineno:
                    start = node.lineno - 1
                    end = node.end_lineno
                    return "\n".join(lines[start:end])
        return None
    except Exception:
        return None


def extract_revit_imports(file_path: str) -> List[str]:
    """Extract Revit API import lines from a source file."""
    imports = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module.startswith("Autodesk.Revit")
                    or node.module.startswith("System")
                    or node.module.startswith("clr")
                ):
                    names = ", ".join(a.name for a in node.names)
                    line_text = f"from {node.module} import {names}"
                    imports.append(line_text)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("clr", "System"):
                        imports.append(f"import {alias.name}")
    except Exception:
        pass
    return imports


def compose_script(
    functions: List[FunctionInfo],
    call_code: str,
    index: LibraryIndex,
    include_transaction: bool = False,
    transaction_name: str = "MCP Operation",
) -> str:
    """Compose a complete IronPython script.

    The script:
    1. Gathers all Revit API imports from referenced source files
    2. Inlines the source of each referenced function
    3. Appends the call_code that uses those functions

    Args:
        functions: List of FunctionInfo objects to inline
        call_code: The code that calls the inlined functions (uses doc, etc.)
        index: The library index (for resolving dependencies)
        include_transaction: Whether to wrap call_code in a Transaction
        transaction_name: Name for the transaction if used
    """
    all_imports: Set[str] = set()
    inlined_sources: List[str] = []
    seen_functions: Set[str] = set()

    for func in functions:
        func_key = f"{func.module_path}.{func.name}"
        if func_key in seen_functions:
            continue
        seen_functions.add(func_key)

        # Gather imports from the source file
        file_imports = extract_revit_imports(func.file_path)
        all_imports.update(file_imports)

        # Read function source
        source = read_function_source(func)
        if source:
            inlined_sources.append(
                f"# --- From {func.module_path} (line {func.line_number}) ---\n"
                f"{source}"
            )

    # Build the script
    parts: List[str] = []

    # Provenance header
    func_paths = [f"{f.module_path}.{f.name}" for f in functions]
    modifies = "YES (transaction)" if include_transaction else "No (read-only)"
    parts.append("# ── Provenance ──────────────────────────────────────")
    parts.append("# Source     : external")
    parts.append(
        "# Library    : {}".format(
            functions[0].module_path.split(".")[0] if functions else "unknown"
        )
    )
    parts.append("# Functions  : {}".format(", ".join(f.name for f in functions)))
    for fp in func_paths:
        parts.append("#   - {}".format(fp))
    parts.append("# Modifies   : {}".format(modifies))
    parts.append("# Inlined for pyRevit IronPython 2.7 compatibility")
    parts.append("# ────────────────────────────────────────────────────")
    parts.append("")

    # Consolidated imports
    if all_imports:
        for imp in sorted(all_imports):
            parts.append(imp)
        parts.append("")

    # Inlined function definitions
    for src in inlined_sources:
        parts.append(src)
        parts.append("")

    # Call code
    if include_transaction:
        parts.append("# --- Execution (within transaction) ---")
        parts.append("from Autodesk.Revit.DB import Transaction")
        parts.append(f't = Transaction(doc, "{transaction_name}")')
        parts.append("t.Start()")
        parts.append("try:")
        for line in call_code.splitlines():
            parts.append(f"    {line}")
        parts.append("    t.Commit()")
        parts.append("except Exception as e:")
        parts.append("    t.RollBack()")
        parts.append('    print("Error: {}".format(str(e)))')
    else:
        parts.append("# --- Execution ---")
        parts.append(call_code)

    return "\n".join(parts)


def compose_explanation(
    functions: List[FunctionInfo],
    call_code: str,
    include_transaction: bool = False,
) -> str:
    """Generate a human-readable explanation of what the composed script does."""
    lines: List[str] = []
    lines.append("## Composed Script Explanation\n")

    lines.append("### Functions Used")
    for func in functions:
        lines.append(f"- **{func.name}** from `{func.module_path}`")
        if func.docstring:
            first_line = func.docstring.strip().split("\n")[0][:80]
            lines.append(f"  - {first_line}")
        if func.requires_doc:
            lines.append("  - Takes `doc` (Revit document)")
        if func.requires_transaction:
            lines.append("  - Requires transaction (modifies model)")
        params_str = ", ".join(p.get("name", "?") for p in func.parameters)
        lines.append(f"  - Parameters: `({params_str})`")

    lines.append("")
    lines.append("### Execution Plan")
    if include_transaction:
        lines.append("- Script will run inside a Revit **Transaction**")
    else:
        lines.append("- Script is **read-only** (no transaction)")

    lines.append("")
    lines.append("### Call Code")
    lines.append("```python")
    lines.append(call_code)
    lines.append("```")

    return "\n".join(lines)
