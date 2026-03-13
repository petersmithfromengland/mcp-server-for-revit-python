# -*- coding: utf-8 -*-
"""
Single MCP tool: main

Registers one tool that handles the complete pipeline:
  1. AST+BM25 search    — finds relevant duHast functions
  2. Code production    — generates IronPython via sub-agent
  3. Code review        — reviews the generated code via sub-agent

code_production and code_review are called internally and are never
registered as MCP tools, so they do not appear in Claude's tool list.
"""

import asyncio
import logging

from mcp.server.fastmcp import Context
from .workflow import build_action_plan, render_action_plan

logger = logging.getLogger(__name__)


def register_code_execution_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register the single main tool with the MCP server."""

    @mcp.tool()
    async def main(
        user_request: str,
        ctx: Context = None,
    ) -> str:
        """
        The single entry point for all Revit operations.

        Call this tool for EVERY user request about Revit — whether the
        user wants to discover available functions, understand the model,
        or have code written and reviewed.

        It runs the full pipeline in one call:
          1. Searches the duHast BM25 keyword index (~2900 functions) to
             find the most relevant helper functions for the request.
          2. Generates a complete, runnable IronPython script using those
             functions via a code production sub-agent.
          3. Reviews the generated code for correctness, Revit API
             compliance, and best practice via a code review sub-agent.

        The response contains three sections:
          - Matched duHast functions with relevance scores and import paths
          - Generated IronPython code
          - Code review notes

        Present the code and review notes to the user and ask for
        approval before executing anything.

        Args:
            user_request: Plain-language description of what the user
                          wants to know or do in Revit.

        Returns:
            Matched duHast functions, generated IronPython code,
            and code review notes in a single structured response.
        """
        if ctx:
            await ctx.info("Searching duHast index...")
        logger.info("main called: %s", user_request[:200])

        # ----------------------------------------------------------------
        # Stage 1 — Discovery (AST+BM25 search + action plan)
        # ----------------------------------------------------------------
        loop = asyncio.get_event_loop()
        plan = await loop.run_in_executor(None, build_action_plan, user_request)
        discovery = render_action_plan(plan)
        logger.info(
            "main stage 1 complete: intent=%s, matches=%d, recommendation=%s",
            plan.intent, len(plan.rag_matches), plan.recommendation,
        )

        # ----------------------------------------------------------------
        # Stage 2 — Code production
        # ----------------------------------------------------------------
        if ctx:
            await ctx.info("Generating code...")
        try:
            from code_production.agent import generate_code
            generated = await generate_code(
                user_request=user_request,
                rag_context=discovery,
                ctx=ctx,
            )
            logger.info("main stage 2 complete: %d chars generated", len(generated))
        except (ImportError, RuntimeError) as exc:
            logger.error("Code production failed: %s", exc, exc_info=True)
            return "{}\n\nERROR (code production): {}".format(discovery, exc)

        # ----------------------------------------------------------------
        # Stage 3 — Code review
        # ----------------------------------------------------------------
        if ctx:
            await ctx.info("Reviewing code...")
        try:
            from code_review.agent import review_code
            review = await review_code(user_request=user_request, code=generated, ctx=ctx)
            logger.info("main stage 3 complete: %d chars review", len(review))
        except (ImportError, RuntimeError) as exc:
            logger.warning("Code review unavailable: %s", exc)
            review = "NOTE: Code review unavailable — {}".format(exc)

        # ----------------------------------------------------------------
        # Assemble response
        # ----------------------------------------------------------------
        lines = [
            "=== duHast Functions Found ===",
            "",
            discovery,
            "",
            "=== Generated IronPython Code ===",
            "",
            generated,
            "",
            "=== Code Review ===",
            "",
            review,
            "",
            "Present the code and review notes to the user. "
            "Ask for approval before executing anything.",
        ]
        logger.info("main complete for: %s", user_request[:100])
        return "\n".join(lines)
