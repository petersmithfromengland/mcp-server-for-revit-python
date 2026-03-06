# -*- coding: utf-8 -*-
"""
External stems — indexed external Python libraries and Revit API docs.

External stems are code building blocks that live outside this
repository (e.g. duHast, other Revit helper packages).  Their paths
are configured in ``config.yaml`` at the repository root.

This package provides:
- ``config.py``         — reads config.yaml for library paths
- ``indexer.py``        — AST-based Python library indexer
- ``code_composer.py``  — inlines function source into IronPython scripts
- ``revit_api_index.py``— Revit API XML documentation parser
- ``tools.py``          — MCP tool registration
"""
