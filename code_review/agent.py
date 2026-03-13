# -*- coding: utf-8 -*-
"""
Code review sub-agent.

Receives the generated IronPython code plus the original user request and
uses MCP sampling (ctx.sample) to ask the connected Claude instance to
review the code.

No Anthropic API key is required — the request is handled by the same
Claude instance that called the main tool.
"""

import logging

from mcp.types import SamplingMessage, TextContent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a code reviewer for IronPython pyRevit scripts that use the duHast \
helper library and the Autodesk Revit API.

Review the provided code against these criteria:

CORRECTNESS
- Does the code correctly address the user's request?
- Are the right duHast functions used with the correct arguments?
- Are Revit API types imported from the correct namespaces?

SAFETY
- Are all write operations (create, delete, modify) wrapped in a Transaction?
- Are None and empty-list results handled before use?
- Are element IDs validated before calling doc.GetElement()?

PYREVIT CONVENTIONS
- Is the active document accessed via __revit__.ActiveUIDocument / .Document?
- Are results printed with print() or output.print_table() (not returned)?
- Is there no if __name__ == "__main__" guard?

OUTPUT FORMAT
Return a concise bullet-point review. If issues are found, quote the \
problematic line and explain the fix. If the code is correct, say so briefly. \
Do NOT reprint the full code unless you are providing a corrected version.
"""


async def review_code(
    user_request: str,
    code: str,
    ctx,
    max_tokens: int = 2048,
) -> str:
    """Use MCP sampling to ask the connected Claude instance to review IronPython code.

    Args:
        user_request: The original user request the code was written for.
        code: The IronPython code to review.
        ctx: FastMCP Context object — used to call ctx.sample().
        max_tokens: Maximum tokens in the response.

    Returns:
        Review output as a string.

    Raises:
        RuntimeError: If ctx is not available.
    """
    if ctx is None:
        raise RuntimeError(
            "ctx is required for code review — ensure main is called via MCP."
        )

    logger.info("Reviewing code via ctx.session.create_message, max_tokens=%d", max_tokens)
    logger.debug("Code to review: %d chars", len(code))

    user_message = (
        "Original user request:\n{request}\n\n"
        "Generated code to review:\n```python\n{code}\n```"
    ).format(request=user_request, code=code)

    result = await ctx.session.create_message(
        messages=[SamplingMessage(role="user", content=TextContent(type="text", text=user_message))],
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=max_tokens,
    )

    text = result.content.text
    logger.info("Code review complete: %d chars", len(text))
    return text
