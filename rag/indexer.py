# -*- coding: utf-8 -*-
"""
duHast source code AST extractor.

Walks a duHast library directory and extracts function-level and
module-level chunks from Python source files using Python's built-in
``ast`` module.  The chunks are consumed by ``rag.ast_index`` to build
the BM25 in-memory search index.

Usage (CLI — builds the BM25 JSON index):
    python -m rag.ast_index           # uses config.xml defaults
    python -m rag.ast_index --force   # rebuild even if file exists
"""

import ast
import hashlib
import os
import re
import time
from typing import List


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _module_header(filepath: str, root: str) -> str:
    """Build a human-readable module path from a file path."""
    rel = os.path.relpath(filepath, root).replace(os.sep, ".")
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.endswith(".__init__"):
        rel = rel[:-9]
    return rel


def _strip_license_block(source: str) -> str:
    """Remove the boilerplate BSD license comment block."""
    lines = source.split("\n")
    out: list[str] = []
    in_license = False
    for line in lines:
        stripped = line.strip()
        if stripped == "# License:" or stripped == "#License:":
            in_license = True
            continue
        if in_license:
            if stripped.startswith("#") or stripped == "":
                continue
            in_license = False
        out.append(line)
    return "\n".join(out)


def _extract_chunks_from_file(
    filepath: str,
    root: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[dict]:
    """Extract semantic chunks from a single Python file.

    Strategy:
      1. Parse the AST to find every top-level function and class.
      2. For each function/method, create a chunk containing:
         - The module path
         - The function signature
         - The docstring
         - The first N characters of the body (for context)
      3. If the file has a module-level docstring, include it as a
         separate chunk.
      4. Fall back to sliding-window text chunking for files that
         fail to parse.
    """
    module_path = _module_header(filepath, root)

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError):
        return []

    source = _strip_license_block(source)

    chunks: list[dict] = []

    # Try AST-based extraction first
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fall back to text chunking for unparseable files
        return _text_chunks(source, module_path, filepath, chunk_size, chunk_overlap)

    # Module-level docstring
    mod_doc = ast.get_docstring(tree)
    if mod_doc and len(mod_doc.strip()) > 20:
        # Strip the decorative tilde lines
        clean_doc = re.sub(r"~+", "", mod_doc).strip()
        if clean_doc:
            chunks.append(
                {
                    "id": _chunk_id(filepath, "module"),
                    "text": "Module: {}\n\n{}".format(module_path, clean_doc),
                    "metadata": {
                        "source_file": filepath,
                        "module": module_path,
                        "type": "module_doc",
                        "name": module_path,
                    },
                }
            )

    # Walk top-level definitions
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            chunk = _function_chunk(node, source, module_path, filepath)
            if chunk:
                chunks.append(chunk)

        elif isinstance(node, ast.ClassDef):
            # Class-level docstring
            class_doc = ast.get_docstring(node)
            class_name = "{}.{}".format(module_path, node.name)
            if class_doc:
                chunks.append(
                    {
                        "id": _chunk_id(filepath, "class:" + node.name),
                        "text": "Class: {}\n\n{}".format(class_name, class_doc.strip()),
                        "metadata": {
                            "source_file": filepath,
                            "module": module_path,
                            "type": "class_doc",
                            "name": class_name,
                        },
                    }
                )
            # Methods within the class
            for item in ast.iter_child_nodes(node):
                if isinstance(item, ast.FunctionDef):
                    chunk = _function_chunk(item, source, class_name, filepath)
                    if chunk:
                        chunks.append(chunk)

    # If AST extraction found nothing useful, fall back to text chunks
    if not chunks:
        chunks = _text_chunks(source, module_path, filepath, chunk_size, chunk_overlap)

    return chunks


def _function_chunk(
    node: ast.FunctionDef,
    source: str,
    parent_path: str,
    filepath: str,
) -> dict | None:
    """Build a chunk dict for a single function/method AST node."""
    func_name = node.name
    docstring = ast.get_docstring(node) or ""
    full_name = "{}.{}".format(parent_path, func_name)

    # Extract the function signature from source lines
    source_lines = source.split("\n")
    start = node.lineno - 1
    # Find the end of the def line (may span multiple lines)
    sig_lines = []
    for i in range(start, min(start + 10, len(source_lines))):
        sig_lines.append(source_lines[i])
        if "):" in source_lines[i] or "):" in source_lines[i].rstrip():
            break

    signature = "\n".join(sig_lines).strip()

    # Build the chunk text
    parts = ["Function: {}".format(full_name), ""]
    if signature:
        parts.append(signature)
        parts.append("")
    if docstring:
        parts.append(docstring.strip())

    text = "\n".join(parts).strip()

    if len(text) < 20:
        return None

    return {
        "id": _chunk_id(filepath, "func:" + full_name),
        "text": text,
        "metadata": {
            "source_file": filepath,
            "module": parent_path,
            "type": "function",
            "name": full_name,
        },
    }


def _text_chunks(
    source: str,
    module_path: str,
    filepath: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[dict]:
    """Sliding-window text chunks as a fallback."""
    source = _strip_license_block(source)
    lines = [l for l in source.split("\n") if l.strip()]
    text = "\n".join(lines)

    if len(text) < 30:
        return []

    chunks = []
    words = text.split()
    step = max(chunk_size - chunk_overlap, 1)

    for i in range(0, len(words), step):
        window = " ".join(words[i : i + chunk_size])
        if len(window) < 30:
            continue
        chunk_idx = i // step
        chunks.append(
            {
                "id": _chunk_id(filepath, "text:{}".format(chunk_idx)),
                "text": "Module: {}\n\n{}".format(module_path, window),
                "metadata": {
                    "source_file": filepath,
                    "module": module_path,
                    "type": "text_chunk",
                    "name": module_path,
                },
            }
        )

    return chunks


def _chunk_id(filepath: str, label: str) -> str:
    """Deterministic chunk ID."""
    raw = "{}::{}".format(filepath, label)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Directory walking
# ---------------------------------------------------------------------------


def collect_chunks(
    library_path: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[dict]:
    """Walk a library directory and collect all chunks."""
    all_chunks: list[dict] = []
    library_path = os.path.normpath(library_path)

    for dirpath, dirnames, filenames in os.walk(library_path):
        # Skip __pycache__ and hidden dirs
        dirnames[:] = [
            d for d in dirnames if not d.startswith("__") and not d.startswith(".")
        ]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            chunks = _extract_chunks_from_file(
                fpath, library_path, chunk_size, chunk_overlap
            )
            all_chunks.extend(chunks)

    return all_chunks
