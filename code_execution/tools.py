# -*- coding: utf-8 -*-
"""
MCP tool registration for the code execution package.

The set of tools registered depends on the ``allow_implicit_code_execution``
setting in ``config.yaml``:

**When ``false`` (default) — gated mode:**

- ``plan_revit_action``   — mandatory first step for any code request
- ``prepare_code``        — submit custom code for user review (returns code_id)
- ``execute_revit_code``  — runs *only* previously-prepared code by code_id
- ``list_pending_code``   — diagnostic: show pending code awaiting approval

**When ``true`` — implicit mode:**

- ``plan_revit_action``   — still recommended, but not enforced
- ``execute_revit_code``  — accepts raw code directly (old behaviour)
"""

from mcp.server.fastmcp import Context
from .workflow import build_action_plan, render_action_plan
from .executor import run_approved_code
from .pending import store_pending, pop_pending, list_pending


def register_code_execution_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register workflow + execution tools with the MCP server.

    Reads ``allow_implicit_code_execution`` from config.yaml to decide
    whether to register the gated (code_id) or direct (raw code) version
    of ``execute_revit_code``.
    """
    _ = revit_get, revit_image  # interface consistency

    # ── Read the config flag ──────────────────────────────────────
    from external_stems.config import load_server_config

    srv_cfg = load_server_config()
    implicit = srv_cfg.allow_implicit_code_execution

    # ── plan_revit_action (always registered) ─────────────────────

    @mcp.tool()
    async def plan_revit_action(
        user_request: str,
        ctx: Context = None,
    ) -> str:
        """
        ★ MANDATORY FIRST STEP — call this BEFORE writing or executing ANY code.

        This tool analyses a user's request against all available resources
        (internal stems, external stems, Revit API docs) and produces an
        ordered action plan following the strict workflow:

            Step 1 → Check for a single internal stem that fulfils the request.
            Step 2 → Check if multiple internal stems can be chained together.
            Step 3 → Search external stems (indexed libraries like duHast)
                     and Revit API classes/methods.  Combine with internal
                     stems if possible.
            Step 4 → Present the proposed code with full provenance to
                     the user.  Execution is NEVER automatic — always
                     wait for the user to approve.
            Step 5 → If no combination of available resources can satisfy
                     the request, clearly state the gaps.

        After receiving the plan, use the appropriate tool to prepare the
        code (execute_stem, execute_stem_chain, compose_external_stem, or
        prepare_code) and present it to the user.  Only call
        execute_revit_code AFTER the user has reviewed and approved.

        Args:
            user_request: A plain-language description of what the user
                          wants to achieve in Revit.

        Returns:
            A structured action plan with matched resources and next
            steps, or a gap analysis if the request cannot be fulfilled.
        """
        if ctx:
            await ctx.info("Analysing request against stems and external resources…")
        return render_action_plan(build_action_plan(user_request))

    # ── Branch: implicit vs gated ─────────────────────────────────

    if implicit:
        _register_implicit_tools(mcp, revit_post)
    else:
        _register_gated_tools(mcp, revit_post)


# ── Implicit mode (allow_implicit_code_execution: true) ───────────


def _register_implicit_tools(mcp, revit_post):
    """Register execute_revit_code that accepts raw code directly."""

    @mcp.tool()
    async def execute_revit_code(
        code: str,
        description: str = "Code execution",
        ctx: Context = None,
    ) -> str:
        """
        Execute IronPython code in Revit.

        The server is configured with ``allow_implicit_code_execution: true``,
        so this tool accepts code directly.

        The code has access to:
        - doc: The active Revit document
        - uidoc: The active UIDocument
        - DB: Revit API Database namespace (Autodesk.Revit.DB)
        - revit: pyRevit module
        - print(): Output text (returned in response)

        Tips:
        - Use getattr(element, 'Name', 'N/A') to safely access the Name property
        - Always use str.format() instead of f-strings (IronPython 2.7)
        - Encode output: use .encode('ascii', 'replace') to avoid Unicode errors
        - Check elements exist before use: if element:
        - Use hasattr() for optional properties
        - Wrap model-modifying code in a Transaction

        Args:
            code: The IronPython code to execute.
            description: Human-readable description of the operation.
        """
        try:
            result = await run_approved_code(code, description, revit_post, ctx)
        except (ConnectionError, ValueError, RuntimeError) as e:
            error_msg = "Error during code execution: {}".format(str(e))
            if ctx:
                await ctx.error(error_msg)
            return error_msg

        # Surface Revit-side errors clearly
        if isinstance(result, str) and any(
            marker in result.lower()
            for marker in ["error:", "traceback", "exception", "failed"]
        ):
            return (
                f"\u26a0 **Revit returned an error:**\n\n"
                f"```\n{result}\n```\n\n"
                f"Show this error to the user and fix the code before retrying."
            )

        return result


# ── Gated mode (allow_implicit_code_execution: false — default) ───


def _register_gated_tools(mcp, revit_post):
    """Register gated tools that require code_id from a preparation step."""

    @mcp.tool()
    async def prepare_code(
        code: str,
        description: str = "Custom code",
        source: str = "custom",
        ctx: Context = None,
    ) -> str:
        """
        Submit custom IronPython code for user review.

        Use this when no internal stem or external stem covers the
        request and you need to write code from scratch.  This tool
        does NOT execute anything — it stores the code and returns it
        with a ``code_id`` for the user to review.

        Also use this when re-preparing code after an error — pass the
        ``source`` from the original preparation to preserve the
        provenance chain.

        ╔══════════════════════════════════════════════════════════╗
        ║  DISPLAY RULES — you MUST follow ALL of these:          ║
        ║                                                          ║
        ║  1. Display the COMPLETE code block from this tool's     ║
        ║     response to the user VERBATIM — never summarise,     ║
        ║     truncate, paraphrase, or rewrite the code.           ║
        ║  2. Include the Code ID so the user can see it.          ║
        ║  3. Ask the user to review and approve before executing. ║
        ║  4. Do NOT call execute_revit_code until the user says   ║
        ║     yes.  Silence is not approval.                       ║
        ╚══════════════════════════════════════════════════════════╝

        ╔══════════════════════════════════════════════════════════╗
        ║  PROVENANCE RULE:                                        ║
        ║  Every script MUST start with a provenance comment block ║
        ║  recording what generated this code (stem ID, library    ║
        ║  function, or "custom") and a short description.         ║
        ║  If the code already has a provenance header, keep it    ║
        ║  and add an "# Updated: <reason>" line.                  ║
        ║  If it does not, add one before submitting the code.     ║
        ╚══════════════════════════════════════════════════════════╝

        The code has access to these globals in the Revit environment:
        - doc: The active Revit document
        - uidoc: The active UIDocument
        - DB: Revit API Database namespace (Autodesk.Revit.DB)
        - revit: pyRevit module
        - print(): Output text (returned in response)

        Tips for writing IronPython for Revit:
        - Use getattr(element, 'Name', 'N/A') to safely access the Name property
        - Always use str.format() instead of f-strings (IronPython 2.7)
        - Encode output: use .encode('ascii', 'replace') to avoid Unicode errors
        - Check elements exist before use: if element:
        - Use hasattr() for optional properties
        - Wrap model-modifying code in a Transaction

        Provenance header format you MUST include at the top of the code:
            # ── Provenance ──────────────────────────────────────
            # Source : custom | stem:<id> | external:<library>
            # Description: <what this code does>
            # Updated: <reason>  ← only if re-prepared after error
            # ────────────────────────────────────────────────────

        Args:
            code: The IronPython code to prepare for review.
                  MUST include a provenance header (see above).
            description: Human-readable description of what the code does.
            source: Origin of this code.  Use "custom" for new code.
                    When re-preparing after an error, preserve the
                    original source (e.g. "stem:query.elements_by_category"
                    or "external:duHast").

        Returns:
            The code with a code_id.  You MUST display the full code block
            to the user and wait for explicit approval.
        """
        # Ensure provenance header is present
        if not code.lstrip().startswith("# ── Provenance"):
            header_lines = [
                "# ── Provenance ──────────────────────────────────────",
                f"# Source     : {source}",
                f"# Description: {description}",
                "# ────────────────────────────────────────────────────",
            ]
            code = "\n".join(header_lines) + "\n" + code

        code_id = store_pending(code, description, source=source)

        if ctx:
            await ctx.info(f"Code prepared (ID: {code_id}) — awaiting user approval.")

        return (
            f"## Prepared Code — awaiting your approval\n\n"
            f"**Description:** {description}\n"
            f"**Source:** `{source}`\n"
            f"**Code ID:** `{code_id}`\n\n"
            f"```python\n{code}\n```\n\n"
            f"---\n\n"
            f"⚠ **DISPLAY INSTRUCTION:** You MUST include the COMPLETE "
            f"code block above in your message to the user — do NOT "
            f"summarise, truncate, or rewrite it.  The user needs to "
            f"see the exact code that will be executed.\n\n"
            f"Ask the user: *Please review the code above.  "
            f"Shall I go ahead and execute it?*"
        )

    @mcp.tool()
    async def execute_revit_code(
        code_id: str,
        ctx: Context = None,
    ) -> str:
        """
        Execute previously-prepared code in Revit by its code_id.

        ⚠ This tool does NOT accept raw code.  It only executes code
        that was previously prepared by one of these tools:
          - ``execute_stem`` / ``execute_stem_chain`` (internal stems)
          - ``compose_external_stem`` (external library code)
          - ``prepare_code`` (custom code)

        Each preparation tool returns a ``code_id``.  Pass that here
        ONLY after the user has reviewed the code and given explicit
        approval.

        If you do not have a code_id, you must first prepare the code
        using one of the tools listed above.

        ╔══════════════════════════════════════════════════════════╗
        ║  IF EXECUTION FAILS:                                     ║
        ║  1. Show the error to the user.                          ║
        ║  2. Prepare a FIXED version using prepare_code.          ║
        ║  3. Display the new code block to the user VERBATIM.     ║
        ║  4. Wait for the user to approve the fixed version.      ║
        ║  Do NOT silently retry or auto-fix without showing code. ║
        ╚══════════════════════════════════════════════════════════╝

        Args:
            code_id: The code identifier returned by a preparation tool.
                     Example: "a1b2c3d4"
        """
        try:
            code, description = pop_pending(code_id)
        except KeyError as e:
            return (
                f"❌ {e}\n\n"
                f"You must prepare code first using execute_stem, "
                f"compose_external_stem, or prepare_code, then present "
                f"it to the user for approval before executing."
            )

        try:
            result = await run_approved_code(code, description, revit_post, ctx)
        except (ConnectionError, ValueError, RuntimeError) as e:
            error_msg = "Error during code execution: {}".format(str(e))
            if ctx:
                await ctx.error(error_msg)
            return (
                f"\u274c **Execution failed:** {error_msg}\n\n"
                f"\u26a0 **REQUIRED NEXT STEPS:**\n"
                f"1. Show this error to the user.\n"
                f"2. Prepare a FIXED version of the code using `prepare_code`.\n"
                f"3. Display the full fixed code block to the user VERBATIM.\n"
                f"4. Wait for the user to approve before executing again.\n\n"
                f"Do NOT silently retry or auto-fix without showing the code."
            )

        # Check for Revit-side errors in the result
        if isinstance(result, str) and any(
            marker in result.lower()
            for marker in ["error:", "traceback", "exception", "failed"]
        ):
            return (
                f"\u26a0 **Revit returned an error:**\n\n"
                f"```\n{result}\n```\n\n"
                f"**REQUIRED NEXT STEPS:**\n"
                f"1. Show this error to the user.\n"
                f"2. Prepare a FIXED version of the code using `prepare_code`.\n"
                f"3. Display the full fixed code block to the user VERBATIM.\n"
                f"4. Wait for the user to approve before executing again.\n\n"
                f"Do NOT silently retry or auto-fix without showing the code."
            )

        return result

    @mcp.tool()
    async def list_pending_code() -> str:
        """
        List all code that has been prepared but not yet executed.

        Use this to check what code_ids are available if you've lost
        track, or to see if previously prepared code has expired.
        """
        pending = list_pending()
        if not pending:
            return "No pending code.  Use a preparation tool first."
        lines = ["Pending code awaiting approval:\n"]
        for entry in pending:
            lines.append(
                f"  • **{entry['code_id']}** — {entry['description']}\n"
                f"    Source: {entry['source']} | "
                f"Age: {entry['age_seconds']}s\n"
                f"    Preview: `{entry['code_preview']}`\n"
            )
        return "\n".join(lines)
