# -*- coding: utf-8 -*-
"""
Code executor — the final execution step.

Sends user-approved IronPython code to the pyRevit Routes API
endpoint for execution inside Revit.
"""

import logging

logger = logging.getLogger(__name__)


async def run_approved_code(
    code: str,
    description: str,
    revit_post,
    ctx=None,
) -> str:
    """Execute code that has been reviewed and approved by the user.

    Args:
        code: The IronPython code to execute.
        description: Human-readable description of the operation.
        revit_post: The async POST function for the pyRevit Routes API.
        ctx: Optional MCP Context for logging.

    Returns:
        Formatted response string from Revit.
    """
    payload = {"code": code, "description": description}

    logger.info("Executing approved code: %s", description)
    logger.debug("Code payload length: %d chars", len(code))

    if ctx:
        await ctx.info("Executing approved code: {}".format(description))

    response = await revit_post("/execute_code/", payload, ctx)
    logger.info("Execution response received for: %s", description)
    logger.debug("Execution response: %s", str(response)[:500])

    if isinstance(response, dict):
        return str(response.get("result", response))
    return str(response)
