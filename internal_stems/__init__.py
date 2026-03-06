# -*- coding: utf-8 -*-
"""
Internal Stems — high-use code building blocks for Revit MCP.

Internal stems are parameterized IronPython code templates that constrain
code execution to safe, well-tested operations.  Instead of allowing
arbitrary code, the LLM composes operations from these building blocks.

These are the most frequently needed patterns: collectors, room data,
wall creation, view management, etc.
"""

from .registry import StemRegistry, get_registry

__all__ = ["StemRegistry", "get_registry"]
