# -*- coding: utf-8 -*-
"""View image export tool.

Only the image-export tool remains here because it returns binary
image data which cannot be handled by the stem execution pipeline.

View listing, properties, and element queries are now available via
internal stems: ``view.list_views``, ``view.get_properties``,
``view.elements_in_view``.
"""

from mcp.server.fastmcp import Context


def register_view_tools(mcp, revit_image):
    """Register view image export tool"""

    @mcp.tool()
    async def get_revit_view(view_name: str, ctx: Context = None):
        """Export a specific Revit view as an image"""
        return await revit_image(f"/get_view/{view_name}", ctx)
