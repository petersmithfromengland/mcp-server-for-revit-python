# -*- coding: utf-8 -*-
"""
Workflow orchestration for the Revit MCP Server.

The LLM must call ``plan_revit_action`` before generating or executing
any code.

Pipeline stages:
    1. _extract_keywords     -- clean, stop-word-filtered keyword list
    2. _classify_intent      -- "query" | "modify" | "view" | "compound"
    3. _search_duhast_rag    -- vector search against indexed duHast docs
    4. build_action_plan     -- assemble structured plan
    5. render_action_plan    -- format plan as human-readable string
"""

from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


# -- Constants ---------------------------------------------------------

_STOP_WORDS = {
    "get",
    "set",
    "all",
    "the",
    "for",
    "and",
    "with",
    "from",
    "into",
    "has",
    "use",
    "can",
    "are",
    "was",
    "its",
    "not",
    "but",
    "that",
    "this",
    "via",
    "per",
    "how",
    "who",
    "why",
    "any",
}

_MODIFY_SIGNALS = {
    "delete",
    "create",
    "set",
    "move",
    "rename",
    "modify",
    "change",
    "update",
    "add",
    "remove",
    "place",
    "insert",
    "edit",
    "replace",
    "copy",
    "mirror",
    "rotate",
    "resize",
    "split",
    "join",
    "merge",
}

_VIEW_SIGNALS = {
    "view",
    "image",
    "screenshot",
    "render",
    "export",
    "visualize",
    "display",
    "activate",
    "navigate",
    "camera",
    "open",
}

_QUERY_SIGNALS = {
    "list",
    "query",
    "find",
    "count",
    "check",
    "what",
    "which",
    "search",
    "report",
    "summarise",
    "summarize",
    "describe",
    "detail",
}


# -- ActionPlan dataclass ---------------------------------------------


@dataclass
class RAGMatch:
    """A single duHast RAG result, simplified for the plan."""

    name: str
    module: str
    source_type: str
    text: str
    distance: float


@dataclass
class ActionPlan:
    """Structured result of the planning pipeline."""

    request: str
    intent: str  # "query" | "modify" | "view" | "compound"
    keywords: List[str]
    rag_matches: List[RAGMatch] = field(default_factory=list)
    rag_error: Optional[str] = None
    recommendation: str = "custom"
    confidence: str = "low"


# -- Pipeline stages ---------------------------------------------------


def _extract_keywords(user_request: str) -> List[str]:
    """Return a cleaned, stop-word-filtered keyword list."""
    import re

    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9]*", user_request.lower())
    keywords = [t for t in tokens if len(t) > 2 and t not in _STOP_WORDS]
    if not keywords:
        keywords = [t for t in tokens if len(t) > 1 and t not in _STOP_WORDS]
    logger.debug("Extracted keywords: %s", keywords)
    return keywords


def _classify_intent(keywords: List[str]) -> str:
    """Classify request intent from its keyword set."""
    kw_set = set(keywords)
    has_modify = bool(kw_set & _MODIFY_SIGNALS)
    has_view = bool(kw_set & _VIEW_SIGNALS)
    has_query = bool(kw_set & _QUERY_SIGNALS)

    if has_modify and (has_query or has_view):
        intent = "compound"
    elif has_modify:
        intent = "modify"
    elif has_view:
        intent = "view"
    else:
        intent = "query"
    logger.debug("Classified intent: %s", intent)
    return intent


def _search_duhast_rag(
    user_request: str,
) -> tuple[List[RAGMatch], Optional[str]]:
    """Search the duHast AST+BM25 index.

    Replaces the ChromaDB+SentenceTransformer vector search.
    Re-ranking (functions before module docs) is performed inside
    rag.ast_index.search(), so results arrive pre-sorted.

    Returns (matches, error_string_or_None).
    """
    matches: list[RAGMatch] = []
    error: Optional[str] = None
    try:
        from rag.config import load_config
        from rag.ast_index import get_state, search as ast_search

        cfg = load_config()
        store_dir = cfg.rag.vector_store_dir
        desired = cfg.rag.max_results

        logger.debug("AST index store_dir=%s, desired=%d", store_dir, desired)

        # Resolve the library path for auto-build fallback
        library_path = ""
        enabled = [lib for lib in cfg.libraries if lib.enabled]
        if enabled:
            library_path = enabled[0].path

        state = get_state(store_dir, library_path)
        if state is None:
            error = "AST index not built. Run: python -m rag.ast_index"
            logger.warning(error)
            return [], error

        raw = ast_search(user_request, state, max_results=desired)

        matches = [
            RAGMatch(
                name=r.name,
                module=r.module,
                source_type=r.source_type,
                text=r.text,
                distance=r.distance,
            )
            for r in raw
        ]

        funcs = [m for m in matches if m.source_type in ("function", "class_doc")]
        docs  = [m for m in matches if m.source_type not in ("function", "class_doc")]
        logger.info(
            "AST search returned %d matches (%d funcs, %d docs)",
            len(matches), len(funcs), len(docs),
        )

    except Exception as exc:
        error = "AST search failed: {}".format(exc)
        logger.error("AST search exception: %s", exc, exc_info=True)

    return matches, error


def _select_recommendation(
    rag_matches: List[RAGMatch],
) -> tuple[str, str]:
    """Derive recommendation and confidence from RAG results.

    Returns (recommendation, confidence).
    """
    if not rag_matches:
        return "custom", "low"

    # Use the best *function* match for confidence, not module docs
    func_matches = [
        m for m in rag_matches if m.source_type in ("function", "class_doc")
    ]
    best = func_matches[0] if func_matches else rag_matches[0]
    best_distance = best.distance

    # Cosine distance: 0 = identical, ~0.5 = decent match, >1.0 = poor
    if best_distance < 0.5:
        return "duhast_function", "high"
    elif best_distance < 0.7:
        return "duhast_function", "medium"
    elif best_distance < 1.0:
        return "duhast_reference", "low"
    else:
        return "custom", "low"


# -- Public API --------------------------------------------------------


def build_action_plan(user_request: str) -> ActionPlan:
    """Build a structured ActionPlan for a user request."""
    logger.info("Building action plan for: %s", user_request[:200])
    keywords = _extract_keywords(user_request)
    intent = _classify_intent(keywords)

    if not keywords:
        logger.warning("No keywords extracted — returning empty plan")
        return ActionPlan(
            request=user_request,
            intent=intent,
            keywords=[],
        )

    rag_matches, rag_error = _search_duhast_rag(user_request)
    recommendation, confidence = _select_recommendation(rag_matches)

    logger.info(
        "Action plan built: intent=%s, matches=%d, recommendation=%s, confidence=%s",
        intent,
        len(rag_matches),
        recommendation,
        confidence,
    )

    return ActionPlan(
        request=user_request,
        intent=intent,
        keywords=keywords,
        rag_matches=rag_matches,
        rag_error=rag_error,
        recommendation=recommendation,
        confidence=confidence,
    )


def _first_description_line(text: str, skip_prefix: str = "") -> str:
    """Return the first non-empty, non-header line from a chunk's text.

    Skips lines starting with ``skip_prefix`` (e.g. ``"Module:"`` or
    ``"Function:"``).  Falls back to the full text truncated to 120 chars.
    """
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if skip_prefix and stripped.startswith(skip_prefix):
            continue
        return stripped[:120]
    return text.strip()[:120]


def _import_line(module: str, full_name: str) -> str:
    """Build a ``from duHast.X import Y`` statement from RAG metadata.

    ``module`` is the dotted module path (e.g. ``Revit.Rooms.rooms``).
    ``full_name`` is the full qualified name which ends with the symbol
    (e.g. ``Revit.Rooms.rooms.get_all_rooms``).
    """
    # The symbol name is the last segment of full_name
    symbol = full_name.split(".")[-1]
    return "from duHast.{} import {}".format(module, symbol)


def render_action_plan(plan: ActionPlan) -> str:
    """Render an ActionPlan as a structured string for the LLM.

    Output is designed for LLM consumption: blunt, structured, and
    impossible to misinterpret.
    """
    lines: list[str] = []

    if not plan.keywords:
        lines.append("ERROR: Could not extract keywords. Ask the user to rephrase.")
        return "\n".join(lines)

    # ---- Header — gives Claude context before reading results ----
    lines.append("=== duHast RAG Search Results ===")
    lines.append("Request : {}".format(plan.request))
    lines.append(
        "Intent  : {}  |  Keywords: {}".format(
            plan.intent, ", ".join(plan.keywords[:10])
        )
    )
    lines.append("")

    # ---- RAG error ----
    if plan.rag_error:
        lines.append("WARNING: {}".format(plan.rag_error))
        lines.append("")

    # Split matches into functions/classes vs module docs
    func_matches = [
        m for m in plan.rag_matches if m.source_type in ("function", "class_doc")
    ]
    doc_matches = [
        m for m in plan.rag_matches if m.source_type not in ("function", "class_doc")
    ]

    if not plan.rag_matches:
        lines.append("No matching duHast code found for this query.")
        lines.append("Suggest writing custom IronPython code using the Revit API.")
        return "\n".join(lines)

    # ---- Functions section (most important) ----
    if func_matches:
        lines.append(
            "FOUND {} duHast FUNCTION(S) — present these to the user:".format(
                len(func_matches)
            )
        )
        lines.append("")
        for i, m in enumerate(func_matches, 1):
            relevance = max(0, (1 - m.distance) * 100)
            import_stmt = _import_line(m.module, m.name)
            lines.append("{}. {} ({:.0f}% relevance)".format(i, m.name, relevance))
            lines.append("   Import : {}".format(import_stmt))
            lines.append("   ```python")
            lines.append("   {}".format(m.text.strip().replace("\n", "\n   ")))
            lines.append("   ```")
            lines.append("")
    else:
        lines.append("No specific duHast functions matched this query.")
        lines.append("")

    # ---- Related modules (context) ----
    if doc_matches:
        lines.append("Related duHast modules (for additional context):")
        for m in doc_matches:
            desc = _first_description_line(m.text, skip_prefix="Module:")
            lines.append("- {} : {}".format(m.module, desc))
        lines.append("")

    # ---- Closing instruction ----
    total = len(func_matches) + len(doc_matches)
    lines.append(
        "IMPORTANT: The {} result(s) above are REAL duHast functions/modules. "
        "Show the user the function names and their import paths. "
        "Do NOT claim that no functions exist or that you cannot find them.".format(
            total
        )
    )

    return "\n".join(lines)
