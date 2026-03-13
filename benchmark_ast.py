# -*- coding: utf-8 -*-
"""
Benchmark: AST+BM25 index for duHast search.

Tests 100 queries and reports:
  - Init time
  - Per-query latency
  - Top-5 result names per query
  - Hit rate for "direct" queries (expected token in top-5 function name)

Run with:
    .venv/Scripts/python benchmark_ast.py
"""

import os
import sys
import re
import time
import heapq

TOP_N = 5

# -----------------------------------------------------------------------
# Same 100 queries as benchmark_rag.py, plus expected token hints
# for "direct" queries (used to compute hit rate).
# Format: (kind, query, expected_token_or_None)
# expected_token: a substring that should appear in at least one of the
# top-5 function/class *names* for the query to count as a "hit".
# -----------------------------------------------------------------------
QUERIES = [
    # --- original 10 ---
    ("direct",   "get all rooms",                           "room"),
    ("direct",   "list walls by type",                      "wall"),
    ("direct",   "set parameter value",                     "parameter"),
    ("direct",   "place family instance",                   "famil"),
    ("indirect", "change wall layer thickness",             None),
    ("indirect", "find doors that belong to a room",        None),
    ("indirect", "export schedule data to excel",           None),
    ("abstract", "tag elements in a view",                  None),
    ("abstract", "colour override by category",             None),
    ("abstract", "check if element is on a workset",        None),
    # --- 20 from round 2 ---
    ("direct",   "get all levels",                          "level"),
    ("direct",   "get room boundary",                       "room"),
    ("direct",   "get element bounding box",                "bounding"),
    ("direct",   "get family category",                     "famil"),
    ("direct",   "get all linked models",                   "link"),
    ("indirect", "rename a sheet",                          None),
    ("indirect", "delete unused materials",                 None),
    ("indirect", "get door width parameter",                None),
    ("indirect", "get ceiling height",                      None),
    ("indirect", "copy elements to another level",          None),
    ("indirect", "get phase of element",                    None),
    ("indirect", "apply view filter to view",               None),
    ("indirect", "create a floor plan view",                None),
    ("indirect", "hide element in view",                    None),
    ("indirect", "number rooms sequentially",               None),
    ("abstract", "move element to new location",            None),
    ("abstract", "make a group from selection",             None),
    ("abstract", "find unused view templates",              None),
    ("abstract", "get all elements visible in active view", None),
    ("abstract", "synchronise with central model",          None),
    # --- 70 new ---
    ("direct",   "get all sheets",                          "sheet"),
    ("direct",   "get all views",                           "view"),
    ("direct",   "get wall type name",                      "wall"),
    ("direct",   "get room name",                           "room"),
    ("direct",   "get level elevation",                     "level"),
    ("direct",   "get all floors",                          "floor"),
    ("direct",   "get all ceilings",                        "ceiling"),
    ("direct",   "get all doors",                           "door"),
    ("direct",   "get all windows",                         "window"),
    ("direct",   "get all grids",                           "grid"),
    ("direct",   "get worksets list",                       "workset"),
    ("direct",   "get element id",                          None),
    ("direct",   "get sheet number",                        "sheet"),
    ("direct",   "get view scale",                          "view"),
    ("direct",   "get material name",                       "material"),
    ("direct",   "get all curtain walls",                   "curtain"),
    ("direct",   "get all railings",                        "railing"),
    ("direct",   "get all stairs",                          "stair"),
    ("direct",   "get all columns",                         "column"),
    ("direct",   "get schedule fields",                     "schedule"),
    ("indirect", "sort elements by level",                  None),
    ("indirect", "get walls on a specific level",           None),
    ("indirect", "filter elements by parameter value",      None),
    ("indirect", "load family from file",                   None),
    ("indirect", "change room name",                        None),
    ("indirect", "get annotation tags",                     None),
    ("indirect", "change grid head visibility",             None),
    ("indirect", "purge unused families",                   None),
    ("indirect", "get view crop region",                    None),
    ("indirect", "rotate element",                          None),
    ("indirect", "mirror elements about axis",              None),
    ("indirect", "create section view",                     None),
    ("indirect", "print drawings to pdf",                   None),
    ("indirect", "get all text notes",                      None),
    ("indirect", "get structural walls",                    None),
    ("indirect", "get elements by type",                    None),
    ("indirect", "change material appearance",              None),
    ("indirect", "get room occupancy parameter",            None),
    ("indirect", "get wall base constraint",                None),
    ("indirect", "get floor type name",                     None),
    ("indirect", "join geometry of two elements",           None),
    ("indirect", "get assembly instances",                  None),
    ("indirect", "calculate room perimeter",                None),
    ("indirect", "get scope box assigned to view",          None),
    ("indirect", "check if view is a view template",        None),
    ("indirect", "get door schedule data",                  None),
    ("indirect", "get ceiling type name",                   None),
    ("indirect", "get linked revit file elements",          None),
    ("indirect", "update sheet title block",                None),
    ("indirect", "change view template assigned to view",   None),
    ("abstract", "find all warnings in model",              None),
    ("abstract", "batch rename loaded families",            None),
    ("abstract", "find elements without a room",            None),
    ("abstract", "generate a quantity take off",            None),
    ("abstract", "swap one family type for another",        None),
    ("abstract", "find duplicate room numbers",             None),
    ("abstract", "get structural framing members",          None),
    ("abstract", "set crop region to custom shape",         None),
    ("abstract", "activate a view on a sheet",              None),
    ("abstract", "check wall fire rating parameter",        None),
    ("abstract", "push parameter value to all instances of a type", None),
    ("abstract", "find elements that reference a demolished phase",  None),
    ("abstract", "detect overlapping rooms",                None),
    ("abstract", "get all detail items in a view",          None),
    ("abstract", "isolate elements by category in view",    None),
    ("abstract", "check if workset is editable",            None),
    ("abstract", "get all revision clouds",                 None),
    ("abstract", "find rooms with no area",                 None),
    ("abstract", "get total wall area by type",             None),
    ("abstract", "reorder sheets by number",                None),
]


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _short(name: str) -> str:
    parts = name.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else name


def _bar(label: str, width: int = 72) -> None:
    print("\n" + "=" * width)
    print("  {}".format(label))
    print("=" * width)


def _tokenise(text: str):
    return re.findall(r"[a-z][a-z0-9]*", text.lower())


def _hit(top_names: list, expected: str) -> bool:
    """Return True if *expected* is a substring of any top name."""
    if expected is None:
        return False
    return any(expected in n.lower() for n in top_names)


# -----------------------------------------------------------------------
# AST + BM25 benchmark
# -----------------------------------------------------------------------

def bench_ast(state):
    _bar("AST + BM25 (rank_bm25)")

    query_times = []
    results_by_query = {}
    direct_hits = 0
    direct_total = 0

    for kind, query, expected in QUERIES:
        from rag.ast_index import search as ast_search, _score_to_distance
        import math

        tokens = _tokenise(query)
        t1 = time.perf_counter()
        results = ast_search(query, state, max_results=TOP_N)
        elapsed = time.perf_counter() - t1
        query_times.append(elapsed)

        hits = [
            (_short(r.name), r.source_type, r.distance)
            for r in results
        ]
        results_by_query[query] = (kind, hits, elapsed, expected)

        if kind == "direct" and expected is not None:
            direct_total += 1
            top_names = [h[0] for h in hits]
            if _hit(top_names, expected):
                direct_hits += 1

    print("Avg query : {:.2f} ms  |  Min: {:.2f} ms  |  Max: {:.2f} ms".format(
        sum(query_times) / len(query_times) * 1000,
        min(query_times) * 1000,
        max(query_times) * 1000,
    ))
    if direct_total:
        print("Direct hit rate : {}/{} = {:.0f}%".format(
            direct_hits, direct_total, 100 * direct_hits / direct_total
        ))
    print()

    for query, (kind, hits, elapsed, expected) in results_by_query.items():
        top_names = [h[0] for h in hits]
        flag = ""
        if kind == "direct" and expected is not None:
            flag = " [HIT]" if _hit(top_names, expected) else " [MISS]"
        print("  [{:8s}] {!r}  ({:.0f} ms){}".format(kind, query, elapsed * 1000, flag))
        for i, (name, typ, dist) in enumerate(hits, 1):
            relevance = max(0, int((1 - dist) * 100))
            print("             {}. {:55s} {:12s} {}%".format(i, name, typ, relevance))

    return query_times, results_by_query, direct_hits, direct_total


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

if __name__ == "__main__":
    # ---- Build / load AST index ----
    _bar("Loading AST index")
    from rag.config import load_config
    from rag.ast_index import get_state, ast_index_path, build_index, load_index

    cfg = load_config()
    enabled = [lib for lib in cfg.libraries if lib.enabled]
    library_path = enabled[0].path if enabled else ""
    index_path = ast_index_path(cfg.rag.vector_store_dir)

    if not os.path.exists(index_path):
        print("Index not found at {} — building now...".format(index_path))
        t_build = time.perf_counter()
        build_index(library_path, index_path)
        print("  Built in {:.1f} s".format(time.perf_counter() - t_build))

    t0 = time.perf_counter()
    print("Loading {} ...".format(index_path), end=" ", flush=True)
    state = load_index(index_path)
    init_s = time.perf_counter() - t0
    print("done in {:.2f} s  ({} chunks, {} modules)".format(
        init_s, state.chunk_count, len(state.modules)
    ))

    # ---- Run AST benchmark ----
    ast_times, ast_results, direct_hits, direct_total = bench_ast(state)

    _bar("Summary")
    print("  Init time  : {:.2f} s".format(init_s))
    print("  Queries    : {}".format(len(QUERIES)))
    print("  Avg query  : {:.2f} ms".format(sum(ast_times) / len(ast_times) * 1000))
    if direct_total:
        print("  Direct hits: {}/{} = {:.0f}%".format(
            direct_hits, direct_total, 100 * direct_hits / direct_total
        ))
    print()
