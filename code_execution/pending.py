# -*- coding: utf-8 -*-
"""
Pending execution store — the gate between code preparation and execution.

Every path to Revit code execution must go through this store:

    1.  A preparation tool (``execute_stem``, ``compose_external_stem``,
        ``prepare_code``, etc.) calls ``store_pending()`` which returns a
        short ``code_id``.
    2.  The preparation tool includes the code **and** the ``code_id`` in
        its response so the user can see the code in the chat.
    3.  ``execute_revit_code`` accepts **only** a ``code_id`` — it looks
        up the pending code and executes it.  Raw code strings are
        rejected.

This means no code can be executed unless it was first surfaced through
a tool response that the user can read.
"""

import hashlib
import time
from typing import Dict, Optional, Tuple

# ── In-memory store ────────────────────────────────────────────────
_pending: Dict[str, dict] = {}

# Pending entries expire after this many seconds (default: 10 minutes)
EXPIRY_SECONDS = 600


def store_pending(code: str, description: str, source: str = "unknown") -> str:
    """Store code for later execution and return a short code_id.

    Args:
        code: The IronPython code to store.
        description: Human-readable description of the operation.
        source: Where this code came from (e.g. "stem:query.elements_by_category",
                "external:duHast", "custom").

    Returns:
        A short hex code_id (first 8 chars of SHA-256).
    """
    _expire_old()
    code_id = hashlib.sha256(code.encode()).hexdigest()[:12]
    _pending[code_id] = {
        "code": code,
        "description": description,
        "source": source,
        "timestamp": time.time(),
    }
    return code_id


def pop_pending(code_id: str) -> Tuple[str, str]:
    """Retrieve and remove a pending execution by code_id.

    Returns:
        (code, description) tuple.

    Raises:
        KeyError: If the code_id is not found or has expired.
    """
    _expire_old()
    entry = _pending.pop(code_id, None)
    if entry is None:
        raise KeyError(
            f"Code ID '{code_id}' not found.  It may have expired or was "
            f"already executed.  Prepare the code again using a preparation "
            f"tool (execute_stem, compose_external_stem, or prepare_code) "
            f"and present it to the user for approval."
        )
    return entry["code"], entry["description"]


def list_pending() -> list:
    """Return summaries of all pending executions (for diagnostics)."""
    _expire_old()
    return [
        {
            "code_id": cid,
            "description": entry["description"],
            "source": entry["source"],
            "age_seconds": int(time.time() - entry["timestamp"]),
            "code_preview": (
                entry["code"][:120] + "…" if len(entry["code"]) > 120 else entry["code"]
            ),
        }
        for cid, entry in _pending.items()
    ]


def _expire_old():
    """Remove entries older than EXPIRY_SECONDS."""
    now = time.time()
    expired = [
        cid
        for cid, entry in _pending.items()
        if now - entry["timestamp"] > EXPIRY_SECONDS
    ]
    for cid in expired:
        del _pending[cid]
