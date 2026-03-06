# -*- coding: utf-8 -*-
"""Status / health-check tool.

Only the bare health-check remains here.  Model information is now
available via the ``query.model_info`` internal stem.
"""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_status_tools(mcp, revit_get):
    """Register status-related tools"""

    @mcp.tool()
    async def get_revit_status(ctx: Context) -> str:
        """Check if the Revit MCP API is active and responding"""
        response = await revit_get("/status/", ctx, timeout=10.0)
        return format_response(response)
