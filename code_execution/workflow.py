# -*- coding: utf-8 -*-
"""
Workflow orchestration for the Revit MCP Server.

Enforces a strict decision process for ALL code creation requests.
The LLM must call ``plan_revit_action`` before generating or executing
any code.

Pipeline stages (each independently testable):
    1. _extract_keywords     — clean, stop-word-filtered keyword list
    2. _classify_intent      — "query" | "modify" | "view" | "compound"
    3. _score_stems          — weighted, intent-biased stem matching
    4. _evaluate_chain       — qualified chain candidates only (min score gate)
    5. _search_external_libs — external library search with error surfacing
    6. _search_revit_api     — Revit API doc search with error surfacing
    7. _select_recommendation — uses STEM_CONFIDENCE_THRESHOLD constant
    8. render_action_plan    — string rendering separated from logic
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

# ── Constants ─────────────────────────────────────────────────────────

# Minimum weighted score for a stem to be recommended.
# With weighted scoring (ID=3, name=2, desc=1, intent boost=2) this requires
# at least one strong field hit (e.g. ID match) to trigger a recommendation.
STEM_CONFIDENCE_THRESHOLD = 3

_STOP_WORDS = {
    "get", "set", "all", "the", "for", "and", "with", "from", "into",
    "has", "use", "can", "are", "was", "its", "not", "but", "that",
    "this", "via", "per", "how", "who", "why", "any",
}

_MODIFY_SIGNALS = {
    "delete", "create", "set", "move", "rename", "modify", "change",
    "update", "add", "remove", "place", "insert", "edit", "replace",
    "copy", "mirror", "rotate", "resize", "split", "join", "merge",
}

_VIEW_SIGNALS = {
    "view", "image", "screenshot", "render", "export", "visualize",
    "display", "activate", "navigate", "camera", "open",
}

_QUERY_SIGNALS = {
    "list", "query", "find", "count", "check", "what", "which",
    "search", "report", "summarise", "summarize", "describe", "detail",
}


# ── ActionPlan dataclass ──────────────────────────────────────────────

@dataclass
class ActionPlan:
    """Structured result of the planning pipeline.

    Inspectable by other tools and serialisable to a human-readable string
    via ``render_action_plan()``.
    """
    request: str
    intent: str                             # "query" | "modify" | "view" | "compound"
    keywords: List[str]
    top_stems: List[Tuple[int, Dict]]       # (score, stem_dict) sorted descending
    chain_candidates: List[Dict]            # Stems that qualified for chaining
    lib_matches: List[Tuple[int, str, Any]] # (score, key, func)
    api_matches: List[Tuple[int, str, Any]] # (score, full_name, member)
    recommendation: str                     # "single_stem" | "chain" | "external" | "custom" | "none"
    confidence: str                         # "high" | "medium" | "low"
    lib_error: Optional[str] = None        # Surfaced (not swallowed) search errors
    api_error: Optional[str] = None


# ── Pipeline stages ───────────────────────────────────────────────────

def _extract_keywords(user_request: str) -> List[str]:
    """Return a cleaned, stop-word-filtered keyword list from the request.

    Splits on whitespace and punctuation so "WallType" yields ["walltype"]
    and camelCase or hyphenated terms are kept together.
    Falls back to short tokens only if no long tokens survive filtering.
    """
    import re
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9]*", user_request.lower())
    keywords = [t for t in tokens if len(t) > 2 and t not in _STOP_WORDS]
    if not keywords:
        keywords = [t for t in tokens if len(t) > 1 and t not in _STOP_WORDS]
    return keywords


def _classify_intent(keywords: List[str]) -> str:
    """Classify request intent from its keyword set.

    Returns one of: "query" | "modify" | "view" | "compound"

    "compound" is returned when signals for both modification and read
    operations are present (e.g. "get walls then delete duplicates").
    Defaults to "query" (read-only) when no explicit signals are found.
    """
    kw_set = set(keywords)
    has_modify = bool(kw_set & _MODIFY_SIGNALS)
    has_view   = bool(kw_set & _VIEW_SIGNALS)
    has_query  = bool(kw_set & _QUERY_SIGNALS)

    if has_modify and (has_query or has_view):
        return "compound"
    if has_modify:
        return "modify"
    if has_view:
        return "view"
    return "query"


def _score_stems(
    keywords: List[str],
    all_stems: List[Dict],
    intent: str,
) -> List[Tuple[int, Dict]]:
    """Score stems against keywords using weighted field matching.

    Weights:
      ID match:          3 pts  (most discriminating — concise and specific)
      Name match:        2 pts
      Description match: 1 pt
      Intent alignment:  +2 boost when the stem's category matches intent

    Returns list of (score, stem_dict) sorted descending, zeros excluded.
    """
    intent_category_map: Dict[str, set] = {
        "query":    {"query"},
        "modify":   {"modify"},
        "view":     {"view"},
        "compound": {"query", "modify", "view"},
    }
    aligned = intent_category_map.get(intent, set())

    matches = []
    for s in all_stems:
        id_text   = s["id"].lower()
        name_text = s["name"].lower()
        desc_text = s["description"].lower()
        score = 0
        for kw in keywords:
            if kw in id_text:   score += 3
            if kw in name_text: score += 2
            if kw in desc_text: score += 1
        if score == 0:
            continue
        if s.get("category") in aligned:
            score += 2
        matches.append((score, s))

    matches.sort(key=lambda x: x[0], reverse=True)
    return matches


def _evaluate_chain(
    top_stems: List[Tuple[int, Dict]],
    min_score: int = STEM_CONFIDENCE_THRESHOLD,
) -> List[Dict]:
    """Return chain candidates filtered to stems that independently meet the
    minimum confidence threshold.

    This prevents low-scoring tangential stems from inflating the chain
    recommendation. Only promotes a chain when at least two qualified stems
    exist across different categories or within the same category.
    """
    if len(top_stems) <= 1:
        return []

    qualified = [(score, s) for score, s in top_stems if score >= min_score]
    if len(qualified) <= 1:
        return []

    by_cat: Dict[str, List[Dict]] = {}
    for _score, s in qualified:
        by_cat.setdefault(s["category"], []).append(s)

    if len(by_cat) > 1 or any(len(v) > 1 for v in by_cat.values()):
        return [s for _score, s in qualified[:6]]
    return []


def _search_external_libs(
    keywords: List[str],
) -> Tuple[List[Tuple[int, str, Any]], Optional[str]]:
    """Search external library indexes.

    Returns (matches, error_string_or_None).
    Errors are surfaced rather than swallowed so the plan can report them.
    Uses a set for O(1) deduplication instead of a repeated list scan.
    """
    lib_matches: List[Tuple[int, str, Any]] = []
    lib_error: Optional[str] = None
    try:
        from external_stems.tools import _get_index as _get_lib_index

        lib_index = _get_lib_index()
        seen: set = set()
        for kw in keywords[:5]:
            for func in lib_index.search(kw, max_results=5):
                key = "{}.{}".format(func.module_path, func.name)
                if key not in seen:
                    seen.add(key)
                    score = sum(
                        1
                        for k in keywords
                        if k in func.name.lower()
                        or (func.docstring and k in func.docstring.lower())
                    )
                    lib_matches.append((score, key, func))
        lib_matches.sort(key=lambda x: x[0], reverse=True)
    except Exception as e:
        lib_error = str(e)
    return lib_matches[:10], lib_error


def _search_revit_api(
    keywords: List[str],
) -> Tuple[List[Tuple[int, str, Any]], Optional[str]]:
    """Search the Revit API documentation index.

    Returns (matches, error_string_or_None).
    Errors are surfaced rather than swallowed.
    Uses a set for O(1) deduplication.
    """
    api_matches: List[Tuple[int, str, Any]] = []
    api_error: Optional[str] = None
    try:
        from external_stems.tools import _get_api_index

        api_index = _get_api_index()
        seen: set = set()
        for kw in keywords[:5]:
            for member in api_index.search(kw, max_results=5):
                if member.full_name not in seen:
                    seen.add(member.full_name)
                    score = sum(
                        1
                        for k in keywords
                        if k in member.full_name.lower()
                        or (member.summary and k in member.summary.lower())
                    )
                    api_matches.append((score, member.full_name, member))
        api_matches.sort(key=lambda x: x[0], reverse=True)
    except Exception as e:
        api_error = str(e)
    return api_matches[:10], api_error


def _select_recommendation(
    top_stems: List[Tuple[int, Dict]],
    chain_candidates: List[Dict],
    lib_matches: List[Tuple[int, str, Any]],
    api_matches: List[Tuple[int, str, Any]],
) -> Tuple[str, str]:
    """Derive recommendation and confidence from collected results.

    Returns (recommendation, confidence):
      recommendation: "single_stem" | "chain" | "external" | "custom" | "none"
      confidence:     "high" | "medium" | "low"
    """
    if top_stems and top_stems[0][0] >= STEM_CONFIDENCE_THRESHOLD:
        best_score = top_stems[0][0]
        confidence = "high" if best_score >= STEM_CONFIDENCE_THRESHOLD * 2 else "medium"
        if chain_candidates and len(chain_candidates) > 1:
            return "chain", confidence
        return "single_stem", confidence

    if lib_matches:
        return "external", "medium"

    if api_matches:
        return "custom", "low"

    return "none", "low"


# ── Public API ────────────────────────────────────────────────────────

def build_action_plan(user_request: str) -> ActionPlan:
    """Build a structured ActionPlan for a user request.

    Orchestrates the planning pipeline:
        extract → classify → search → evaluate → recommend

    Returns an ActionPlan dataclass.  Call render_action_plan() to convert
    to a human-readable string suitable for returning from an MCP tool.
    """
    from internal_stems import get_registry

    registry = get_registry()
    keywords = _extract_keywords(user_request)
    intent   = _classify_intent(keywords)

    if not keywords:
        return ActionPlan(
            request=user_request, intent=intent, keywords=[],
            top_stems=[], chain_candidates=[], lib_matches=[], api_matches=[],
            recommendation="none", confidence="low",
        )

    all_stems        = registry.list_all()
    top_stems        = _score_stems(keywords, all_stems, intent)[:10]
    chain_candidates = _evaluate_chain(top_stems)
    lib_matches, lib_error = _search_external_libs(keywords)
    api_matches, api_error = _search_revit_api(keywords)

    recommendation, confidence = _select_recommendation(
        top_stems, chain_candidates, lib_matches, api_matches
    )

    return ActionPlan(
        request          = user_request,
        intent           = intent,
        keywords         = keywords,
        top_stems        = top_stems,
        chain_candidates = chain_candidates,
        lib_matches      = lib_matches,
        api_matches      = api_matches,
        recommendation   = recommendation,
        confidence       = confidence,
        lib_error        = lib_error,
        api_error        = api_error,
    )


def render_action_plan(plan: ActionPlan) -> str:
    """Render an ActionPlan to a human-readable string for MCP tool responses."""
    lines = []
    lines.append("=" * 64)
    lines.append("  REVIT ACTION PLAN")
    lines.append("  Request: {}".format(plan.request))
    lines.append(
        "  Intent : {}  |  Confidence: {}".format(
            plan.intent.upper(), plan.confidence.upper()
        )
    )
    lines.append("=" * 64)

    if not plan.keywords:
        lines.append("\n  ✗ Could not extract meaningful keywords from this request.")
        lines.append("  Try a more specific description, e.g. 'list walls on Level 1'.")
        lines.append("\n" + "=" * 64)
        lines.append(
            "  ⚠ REMINDER: ALL code must be presented to the user for"
            " review and approval before execution.  Never auto-execute."
        )
        lines.append("=" * 64)
        return "\n".join(lines)

    lines.append("\n  Keywords: {}".format(", ".join(plan.keywords)))

    # Step 1
    lines.append("\n── STEP 1: Internal Stem Match ────────────────────")
    if plan.top_stems:
        best_score, best = plan.top_stems[0]
        lines.append("  ✓ Best match: {}  (score: {})".format(best["id"], best_score))
        lines.append("    Name: {}".format(best["name"]))
        lines.append("    Description: {}".format(best["description"]))
        tx_tag = " ⚠ modifies model" if best.get("requires_transaction") else " (read-only)"
        lines.append("    Transaction: {}".format(tx_tag))
        if best["parameters"]:
            lines.append("    Parameters needed:")
            for p in best["parameters"]:
                req = (
                    "required"
                    if p["required"]
                    else "optional (default: {})".format(p.get("default"))
                )
                lines.append(
                    "      - {} ({}, {}): {}".format(p["name"], p["type"], req, p["description"])
                )
        if len(plan.top_stems) > 1:
            lines.append("\n  Other relevant stems ({}):".format(len(plan.top_stems) - 1))
            for score, s in plan.top_stems[1:5]:
                tx = " ⚠" if s.get("requires_transaction") else ""
                lines.append(
                    "    - {} (score: {}): {}{}".format(s["id"], score, s["name"], tx)
                )
    else:
        lines.append("  ✗ No matching internal stem found.")

    # Step 2
    lines.append("\n── STEP 2: Stem Chain Possibility ─────────────────")
    if plan.chain_candidates:
        lines.append("  ✓ {} stems qualify for chaining:".format(len(plan.chain_candidates)))
        for s in plan.chain_candidates:
            tx = " ⚠ modifies" if s.get("requires_transaction") else " (read-only)"
            lines.append("    - {}: {}{}".format(s["id"], s["name"], tx))
        lines.append(
            "\n  → Use execute_stem_chain with these stem IDs to build"
            " a combined operation."
        )
    else:
        if plan.top_stems:
            lines.append("  — Single stem may suffice; chain not required.")
        else:
            lines.append("  ✗ No stems available to chain.")

    # Step 3
    lines.append("\n── STEP 3: External Stems & API Resources ─────────")
    if plan.lib_error:
        lines.append("  ⚠ External library search failed: {}".format(plan.lib_error))
    if plan.lib_matches:
        lines.append("  External libraries ({} matches):".format(len(plan.lib_matches)))
        for _score, key, func in plan.lib_matches[:5]:
            doc = ""
            if func.docstring:
                doc = " — " + func.docstring.strip().split("\n")[0][:70]
            tx = " [modifies model]" if func.requires_transaction else ""
            lines.append("    - {}{}{}".format(key, tx, doc))
        lines.append(
            "\n  → Use read_external_stem to inspect source, then"
            " compose_external_stem to build a script."
        )
    else:
        lines.append("  External libraries: no matches.")

    if plan.api_error:
        lines.append("  ⚠ Revit API search failed: {}".format(plan.api_error))
    if plan.api_matches:
        lines.append("\n  Revit API docs ({} matches):".format(len(plan.api_matches)))
        for _score, name, member in plan.api_matches[:5]:
            kind = "[{}]".format(member.kind)
            summary = ""
            if member.summary:
                summary = " — " + member.summary[:70]
            lines.append("    - {:<10s} {}{}".format(kind, name, summary))
        lines.append(
            "\n  → Use get_revit_api_class or get_revit_api_member for"
            " full signatures before writing code."
        )
    else:
        lines.append("  Revit API docs: no matches.")

    # Step 4
    lines.append("\n── STEP 4: Recommended Approach ───────────────────")
    rec = plan.recommendation
    if rec == "single_stem":
        _, best = plan.top_stems[0]
        lines.append("  ➤ SINGLE STEM: Use execute_stem with ID '{}'.".format(best["id"]))
        lines.append("    Confidence: {}".format(plan.confidence.upper()))
        lines.append("    Code will be returned for your review — not auto-executed.")
    elif rec == "chain":
        lines.append("  ➤ CHAIN: Use execute_stem_chain combining the stems above.")
        lines.append("    Confidence: {}".format(plan.confidence.upper()))
        lines.append("    Code will be returned for your review — not auto-executed.")
    elif rec == "external":
        lines.append("  ➤ EXTERNAL STEM: Compose a script using external library functions.")
        if plan.top_stems:
            lines.append("    Consider combining with internal stems where possible.")
        lines.append(
            "    Use compose_external_stem — code returned for review, not auto-executed."
        )
    elif rec == "custom":
        lines.append("  ➤ CUSTOM CODE: No stems or external functions match.")
        lines.append("    Write IronPython using the Revit API signatures found above.")
        lines.append("    Present the code to the user for approval before executing.")
    else:
        lines.append("  ✗ UNABLE TO SATISFY REQUEST with available resources.")

    # Step 5
    lines.append("\n── STEP 5: Coverage & Gaps ────────────────────────")
    has_stem = bool(plan.top_stems)
    has_lib  = bool(plan.lib_matches)
    has_api  = bool(plan.api_matches)

    if has_stem and (has_lib or has_api):
        lines.append(
            "  Coverage: GOOD — internal stems and reference material available."
        )
    elif has_stem:
        lines.append(
            "  Coverage: PARTIAL — internal stems available but no"
            " external stems / API references found."
        )
    elif has_lib or has_api:
        lines.append(
            "  Coverage: PARTIAL — external stems / API references found"
            " but no internal stems. Custom code will be required."
        )
    else:
        lines.append("  Coverage: NONE — no matching resources found.")
        lines.append("  Gaps:")
        lines.append("    - No internal stems matching: {}".format(plan.request))
        lines.append("    - No external library functions matching the request")
        lines.append("    - No Revit API members matching the request")
        lines.append(
            "\n  Consider broadening the request, checking available"
            " stems with list_internal_stems, or searching the"
            " external stems / API with different keywords."
        )

    lines.append("\n" + "=" * 64)
    lines.append(
        "  ⚠ REMINDER: ALL code must be presented to the user for"
        " review and approval before execution.  Never auto-execute."
    )
    lines.append("=" * 64)

    return "\n".join(lines)
