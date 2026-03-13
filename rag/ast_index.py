# -*- coding: utf-8 -*-
"""
AST-based BM25 index for the duHast library.

Replaces ChromaDB + SentenceTransformer with:
  1. Python ast extraction (via rag.indexer.collect_chunks) — pure stdlib, fast
  2. rank_bm25 in-memory scoring — < 1 second for 2,900 chunks

Startup path (server):
  - load_index() reads a pre-built JSON cache (milliseconds)
  - Builds a BM25Okapi object from the cached chunks (< 0.5 s)
  - No network calls, no ML models, no vector database

Offline build (run once, or after duHast updates):
  python -m rag.ast_index           # build rag/duhast_ast.json
  python -m rag.ast_index --force   # rebuild even if file exists
"""

import json
import logging
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ASTResult:
    """A single BM25 search result from the AST index."""

    text: str
    module: str
    name: str
    source_type: str  # "function" | "class_doc" | "module_doc" | "text_chunk"
    source_file: str
    distance: float   # 0 = best match, 1 = no match (compatible with RAGResult)


@dataclass
class IndexState:
    """In-memory BM25 index built from AST-extracted chunks."""

    chunks: List[dict]                    # raw chunk dicts from collect_chunks()
    bm25: object                          # BM25Okapi instance
    modules: Dict[str, dict]             # module_path → {docstring, functions, classes}
    chunk_count: int
    library_path: str
    generated: str


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


def _tokenise(text: str) -> List[str]:
    """Lowercase alphabetic tokeniser (matches the benchmark's approach)."""
    return re.findall(r"[a-z][a-z0-9]*", text.lower())


# ---------------------------------------------------------------------------
# Index path convention
# ---------------------------------------------------------------------------


def ast_index_path(vector_store_dir: str) -> str:
    """Derive the AST index JSON path from the vector store directory.

    If vector_store_dir is ``rag/duhast``, the AST index is stored at
    ``rag/duhast_ast.json`` — next to the ChromaDB folder, not inside it.
    """
    parent = os.path.dirname(os.path.normpath(vector_store_dir))
    name = os.path.basename(os.path.normpath(vector_store_dir))
    return os.path.join(parent, name + "_ast.json")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_index(
    library_path: str,
    output_path: str,
    force: bool = False,
) -> dict:
    """Walk *library_path*, extract AST chunks, and save to *output_path* as JSON.

    Args:
        library_path: Root directory of the Python library to index.
        output_path:  Destination JSON file path.
        force:        If True, rebuild even if *output_path* already exists.

    Returns:
        The raw dict that was written to disk (keys: generated, library_path,
        chunk_count, chunks).
    """
    if os.path.exists(output_path) and not force:
        logger.info("AST index already exists at %s (use --force to rebuild)", output_path)
        with open(output_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    from rag.indexer import collect_chunks

    t0 = time.time()
    logger.info("Building AST index from %s", library_path)
    chunks = collect_chunks(library_path)
    elapsed = time.time() - t0
    logger.info("Extracted %d chunks in %.1f s", len(chunks), elapsed)

    data = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "library_path": library_path,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)

    logger.info("AST index saved → %s (%d chunks)", output_path, len(chunks))
    return data


# ---------------------------------------------------------------------------
# Load (fast path)
# ---------------------------------------------------------------------------


def load_index(output_path: str) -> IndexState:
    """Load the JSON cache and build a BM25 in-memory index.

    Typical time: < 0.5 s for a 2,900-chunk corpus.
    """
    from rank_bm25 import BM25Okapi

    t0 = time.time()
    logger.info("Loading AST index from %s", output_path)

    with open(output_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    chunks = data["chunks"]

    # Build BM25 corpus
    tokenised = [_tokenise(c["text"]) for c in chunks]
    bm25 = BM25Okapi(tokenised)

    # Build per-module summary (used by get_overview)
    modules: Dict[str, dict] = {}
    for chunk in chunks:
        meta = chunk["metadata"]
        module = meta["module"]
        chunk_type = meta["type"]
        if module not in modules:
            modules[module] = {"docstring": "", "functions": [], "classes": []}
        if chunk_type == "module_doc":
            parts = chunk["text"].split("\n\n", 1)
            modules[module]["docstring"] = parts[1].strip() if len(parts) > 1 else ""
        elif chunk_type == "function":
            modules[module]["functions"].append(meta["name"].split(".")[-1])
        elif chunk_type == "class_doc":
            modules[module]["classes"].append(meta["name"].split(".")[-1])

    elapsed = time.time() - t0
    logger.info(
        "AST index ready: %d chunks, %d modules in %.2f s",
        len(chunks), len(modules), elapsed,
    )

    return IndexState(
        chunks=chunks,
        bm25=bm25,
        modules=modules,
        chunk_count=len(chunks),
        library_path=data.get("library_path", ""),
        generated=data.get("generated", ""),
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

# BM25 score → distance mapping constants.
# BM25 scores for this corpus typically fall in 0–20.
# We use log1p to compress the range and map to [0, 1]:
#   score ≥ 15  → distance ≈ 0.0  (high confidence)
#   score ≈  8  → distance ≈ 0.3  (medium-high)
#   score ≈  4  → distance ≈ 0.5  (medium)
#   score ≈  2  → distance ≈ 0.65 (low)
#   score =  0  → distance = 1.0  (no match)
_LOG_SCALE = math.log1p(15.0)

# ---------------------------------------------------------------------------
# Revit-domain disambiguation boost
#
# Some common English and programming words are also Revit element types
# (e.g. "windows" → WPF windows vs Revit window families; "columns" →
# DataFrame/Matrix columns vs Revit structural columns).  When any of these
# words appears in the query we apply a score multiplier to chunks whose
# module path contains "revit", pushing Revit-API results above generic
# utility/UI code without affecting unambiguous queries.
# ---------------------------------------------------------------------------

_REVIT_DOMAIN_KEYWORDS: frozenset = frozenset({
    # Element types that share names with UI / Python / general concepts
    "window", "windows",
    "column", "columns",
    "view", "views",
    "level", "levels",
    "link", "links",
    "filter", "filters",
    "type", "types",
    "area", "areas",
    "group", "groups",
    "text",
    "phase", "phases",
    "floor", "floors",     # also math.floor
    "grid", "grids",       # also CSS/UI grids
    "sheet", "sheets",     # also Excel sheets
    # Lower-collision Revit terms — still worth boosting for consistency
    "room", "rooms",
    "wall", "walls",
    "ceiling", "ceilings",
    "door", "doors",
    "stair", "stairs",
    "railing", "railings",
    "workset", "worksets",
    "material", "materials",
    "parameter", "parameters",
    "schedule", "schedules",
    "family", "families",
    "element", "elements",
    "tag", "tags",
    "revision", "revisions",
    "scope",
    "boundary",
})

# Score multiplier applied to chunks in a "duHast.Revit.*" module when the
# query contains one or more _REVIT_DOMAIN_KEYWORDS.
_REVIT_MODULE_BOOST: float = 3.0

# Marker that must appear in a chunk's module path (case-insensitive) for
# the boost to apply.  duHast modules covering Revit elements all live under
# a path segment named "Revit" (e.g. "Revit.Rooms.rooms").
_REVIT_MODULE_MARKER: str = "revit"


def _score_to_distance(score: float) -> float:
    """Map a raw BM25 score to a cosine-distance-like value in [0, 1]."""
    if score <= 0:
        return 1.0
    return max(0.0, 1.0 - math.log1p(score) / _LOG_SCALE)


def search(
    query: str,
    state: IndexState,
    max_results: int = 8,
) -> List[ASTResult]:
    """BM25 keyword search over AST chunks.

    Over-fetches candidates then re-ranks so that concrete function/class
    chunks are preferred over module-level docstring chunks — mirroring the
    re-ranking logic in the original vector RAG workflow.

    When the query contains Revit element-type keywords that are also common
    in non-Revit code (e.g. "windows", "columns"), a score boost is applied
    to chunks from duHast.Revit.* modules so they are not displaced by WPF,
    Matrix, or other generic utility results.

    Args:
        query:       Natural-language query string.
        state:       Loaded IndexState (from load_index).
        max_results: Maximum results to return.

    Returns:
        List of ASTResult sorted by relevance (lowest distance first),
        functions before module docs.
    """
    tokens = _tokenise(query)
    if not tokens:
        return []

    raw_scores = state.bm25.get_scores(tokens)

    # Apply Revit-domain boost when the query mentions Revit element types
    # that could otherwise match generic utility/UI code.
    if set(tokens) & _REVIT_DOMAIN_KEYWORDS:
        scores = [
            float(raw_scores[i]) * _REVIT_MODULE_BOOST
            if _REVIT_MODULE_MARKER in state.chunks[i]["metadata"]["module"].lower()
            else float(raw_scores[i])
            for i in range(len(raw_scores))
        ]
    else:
        scores = [float(s) for s in raw_scores]

    # Over-fetch 4× so re-ranking still fills max_results with functions
    import heapq
    n_candidates = min(max_results * 4, len(scores))
    top_indices = heapq.nlargest(n_candidates, range(len(scores)), key=lambda i: scores[i])

    results: List[ASTResult] = []
    for idx in top_indices:
        chunk = state.chunks[idx]
        meta = chunk["metadata"]
        results.append(ASTResult(
            text=chunk["text"],
            module=meta["module"],
            name=meta["name"],
            source_type=meta["type"],
            source_file=meta.get("source_file", ""),
            distance=_score_to_distance(scores[idx]),
        ))

    # Re-rank: concrete function/class chunks first, then module docs
    funcs = [r for r in results if r.source_type in ("function", "class_doc")]
    docs  = [r for r in results if r.source_type not in ("function", "class_doc")]
    return (funcs + docs)[:max_results]


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def get_overview(state: IndexState, max_modules: int = 100) -> str:
    """Return a compact module-level summary suitable for LLM consumption.

    Args:
        state:       Loaded IndexState.
        max_modules: Cap on number of modules shown (sorted alphabetically).

    Returns:
        Multi-line string listing modules, their function counts, and first
        line of their docstring.
    """
    lines = [
        "=== duHast Library Overview ===",
        "  {} indexed chunks across {} modules".format(
            state.chunk_count, len(state.modules)
        ),
        "  Index built: {}".format(state.generated),
        "",
    ]

    sorted_modules = sorted(state.modules.items())[:max_modules]
    for module, info in sorted_modules:
        doc = info["docstring"]
        first_line = doc.split("\n")[0].strip() if doc else "(no docstring)"
        if len(first_line) > 100:
            first_line = first_line[:97] + "..."

        fn_count = len(info["functions"])
        cls_count = len(info["classes"])
        tag_parts = []
        if fn_count:
            tag_parts.append("{} fn".format(fn_count))
        if cls_count:
            tag_parts.append("{} cls".format(cls_count))
        tag = ", ".join(tag_parts) if tag_parts else "no symbols"

        lines.append("  {} [{}]".format(module, tag))
        if first_line and first_line != "(no docstring)":
            lines.append("    {}".format(first_line))

    if len(state.modules) > max_modules:
        lines.append("  ... and {} more modules".format(
            len(state.modules) - max_modules
        ))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# In-process singleton (used by the MCP server)
# ---------------------------------------------------------------------------

_singleton: Optional[IndexState] = None
_singleton_lock = threading.Lock()


def get_state(vector_store_dir: str, library_path: str = "") -> Optional[IndexState]:
    """Return the singleton IndexState, loading (or auto-building) if needed.

    Thread-safe.  The first call pays the JSON load + BM25 build cost
    (< 0.5 s).  Subsequent calls return the cached object instantly.

    If the JSON index does not exist and *library_path* is provided,
    the index is built automatically (takes a few seconds).

    Returns None if the index cannot be loaded or built.
    """
    global _singleton

    if _singleton is not None:
        return _singleton

    with _singleton_lock:
        if _singleton is not None:
            return _singleton

        index_path = ast_index_path(vector_store_dir)

        if not os.path.exists(index_path):
            if not library_path:
                logger.warning(
                    "AST index not found at %s. "
                    "Run: python -m rag.ast_index",
                    index_path,
                )
                return None
            # Auto-build on first use
            logger.info(
                "AST index not found — auto-building from %s. "
                "This runs once and takes a few seconds.",
                library_path,
            )
            try:
                build_index(library_path, index_path)
            except Exception as exc:
                logger.error("Auto-build of AST index failed: %s", exc)
                return None

        try:
            _singleton = load_index(index_path)
        except Exception as exc:
            logger.error("Failed to load AST index: %s", exc)
            return None

    return _singleton


def is_ready(vector_store_dir: str) -> bool:
    """Return True if the singleton index is loaded and ready."""
    if _singleton is not None:
        return True
    return os.path.exists(ast_index_path(vector_store_dir))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: ``python -m rag.ast_index [--force]``."""
    try:
        from rag.config import load_config
    except ImportError:
        # Allow running from repo root without the package installed
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from rag.config import load_config

    force = "--force" in sys.argv
    cfg = load_config()

    enabled = [lib for lib in cfg.libraries if lib.enabled]
    if not enabled:
        print("No enabled libraries in config.xml.")
        sys.exit(1)

    for lib in enabled:
        index_path = ast_index_path(cfg.rag.vector_store_dir)
        print("\n=== Building AST index: {} ===".format(lib.name))
        print("  Library path : {}".format(lib.path))
        print("  Index output : {}".format(index_path))
        t0 = time.time()
        data = build_index(lib.path, index_path, force=force)
        elapsed = time.time() - t0
        print("  Chunks       : {}".format(data["chunk_count"]))
        print("  Elapsed      : {:.1f} s".format(elapsed))

        # Quick load + BM25 build sanity check
        print("  Loading index + building BM25...", end=" ", flush=True)
        t1 = time.time()
        state = load_index(index_path)
        print("done in {:.2f} s  ({} modules)".format(time.time() - t1, len(state.modules)))

    print("\nDone. Start the MCP server — no warmup required.")


if __name__ == "__main__":
    main()
