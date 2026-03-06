# -*- coding: utf-8 -*-
"""
Code executor — the final execution step.

Sends user-approved IronPython code to the pyRevit Routes API
endpoint for execution inside Revit.
"""


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
    from tools.utils import format_response

    payload = {"code": code, "description": description}

    if ctx:
        await ctx.info("Executing approved code: {}".format(description))

    response = await revit_post("/execute_code/", payload, ctx)
    return format_response(response)
