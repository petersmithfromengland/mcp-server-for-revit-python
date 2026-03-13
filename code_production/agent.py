# -*- coding: utf-8 -*-
"""
Code production sub-agent.

Receives a user request and the duHast RAG context (matched functions with
import statements) and uses MCP sampling (ctx.sample) to ask the connected
Claude instance to generate complete, runnable IronPython code for pyRevit.

No Anthropic API key is required — the request is handled by the same
Claude instance that called the main tool.
"""

import logging

from mcp.types import SamplingMessage, TextContent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert IronPython developer specialising in pyRevit scripts that use the \
duHast helper library and the Autodesk Revit API.

You will receive:
1. A user request describing what they want to do in Revit.
2. A RAG search result listing the most relevant duHast functions, \
   their full signatures, docstrings, and ready-to-use import statements.

Your job is to produce a COMPLETE, RUNNABLE pyRevit IronPython script that:
- Imports the exact duHast functions shown in the RAG results using the \
  provided import statements.
- Imports any Revit API types needed (Autodesk.Revit.DB, etc.).
- Accesses the active document via __revit__.ActiveUIDocument / .Document.
- Wraps any write operations in a Revit Transaction.
- Prints results with print() or output.print_table() for tabular data.
- Handles None / empty list results gracefully.
- Includes a brief comment above each logical block explaining what it does.
- Does NOT include if __name__ == "__main__" guards (not needed in pyRevit).

Return ONLY the Python code block, with no prose before or after it.
"""


async def generate_code(
    user_request: str,
    rag_context: str,
    ctx,
    max_tokens: int = 4096,
) -> str:
    """Use MCP sampling to ask the connected Claude instance to generate IronPython code.

    Args:
        user_request: The original user request.
        rag_context: The rendered RAG search result (functions + imports).
        ctx: FastMCP Context object — used to call ctx.sample().
        max_tokens: Maximum tokens in the response.

    Returns:
        Generated IronPython code as a string.

    Raises:
        RuntimeError: If ctx is not available.
    """
    if ctx is None:
        raise RuntimeError(
            "ctx is required for code production — ensure main is called via MCP."
        )

    logger.info("Generating code via ctx.session.create_message, max_tokens=%d", max_tokens)
    logger.debug("User request: %s", user_request[:200])
    logger.debug("RAG context length: %d chars", len(rag_context))

    user_message = (
        "User request:\n{request}\n\n"
        "Relevant duHast functions found by RAG search:\n{context}"
    ).format(request=user_request, context=rag_context)

    result = await ctx.session.create_message(
        messages=[SamplingMessage(role="user", content=TextContent(type="text", text=user_message))],
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=max_tokens,
    )

    text = result.content.text
    logger.info("Code generation complete: %d chars", len(text))
    return text
