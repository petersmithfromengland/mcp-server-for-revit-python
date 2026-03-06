# -*- coding: utf-8 -*-
"""
Tool registration — core Revit MCP tools.

Only the health-check tool remains here.  All other Revit interactions
(including view image export) have been migrated to internal stems
(see ``internal_stems/``).
"""


def register_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func=None):
    """Register the core Revit tools with the MCP server.

    Only ``get_revit_status`` (health-check) remains as a direct tool.
    View export is now the ``view.export_image`` stem.

    Other tool groups registered separately:
      - ``internal_stems.tools.register_internal_stem_tools``
      - ``external_stems.tools.register_external_stem_tools``
      - ``code_execution.tools.register_code_execution_tools``
    """
    from .status_tools import register_status_tools

    register_status_tools(mcp_server, revit_get_func)
