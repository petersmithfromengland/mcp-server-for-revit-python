# -*- coding: utf-8 -*-
"""
Internal stem tools — MCP tool definitions that expose the internal
stems system.

These tools replace arbitrary code execution with a constrained,
stem-based approach.  The LLM discovers available internal stems, then
prepares them individually or as chains for user review.
"""

import json
from mcp.server.fastmcp import Context
from typing import Dict, Any, List, Optional
from code_execution.pending import store_pending


def register_internal_stem_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register internal-stem-related tools with the MCP server."""
    _ = revit_get, revit_image  # Unused but kept for interface consistency

    from internal_stems import get_registry

    registry = get_registry()

    @mcp.tool()
    async def list_stems(
        category: str = None,
        search: str = None,
        ctx: Context = None,
    ) -> str:
        """
        List available internal code stems (pre-defined Revit operations).

        Internal stems are safe, parameterized building blocks for
        interacting with Revit.  Browse all stems here, or let
        plan_revit_action search stems automatically as part of the
        mandatory workflow.

        Args:
            category: Filter by category - "query", "modify", or "view".
                      Leave empty to list all stems.
            search: Search stems by name or description (case-insensitive).

        Returns:
            List of stems with their IDs, descriptions, and parameters.
        """
        if ctx:
            await ctx.info("Listing available internal stems...")

        if search:
            stems = registry.search(search)
        elif category:
            stems = registry.list_by_category(category)
        else:
            stems = registry.list_all()

        if not stems:
            return "No internal stems found matching your criteria."

        lines = []
        current_cat = None
        for s in stems:
            if s["category"] != current_cat:
                current_cat = s["category"]
                lines.append(f"\n=== {current_cat.upper()} STEMS ===")

            lines.append(f"\n  {s['id']}")
            lines.append(f"    {s['name']}: {s['description']}")

            if s["parameters"]:
                lines.append("    Parameters:")
                for p in s["parameters"]:
                    req = (
                        "required"
                        if p["required"]
                        else f"optional, default={p.get('default', 'None')}"
                    )
                    choices = f", choices: {p['choices']}" if p.get("choices") else ""
                    lines.append(
                        f"      - {p['name']} ({p['type']}, {req}{choices}): {p['description']}"
                    )
            if s.get("requires_transaction"):
                lines.append("    ⚠ Modifies model (uses transaction)")

        lines.append(f"\n\nTotal: {len(stems)} internal stem(s)")
        categories = registry.categories()
        lines.append(f"Categories: {', '.join(categories)}")

        return "\n".join(lines)

    @mcp.tool()
    async def execute_stem(
        stem_id: str,
        params: str = "{}",
        ctx: Context = None,
    ) -> str:
        """
        Prepare a single internal stem for execution in Revit.

        ⚠ WORKFLOW REQUIREMENT: Call plan_revit_action FIRST to determine
        whether a stem is the right approach.  This tool is Step 4 in the
        mandatory workflow.

        This tool NEVER auto-executes code.  It always returns the
        rendered IronPython code along with provenance references
        (stem ID, description, parameters) for the user to review.

        After the user approves, pass the code_id to execute_revit_code.

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

        PROVENANCE: This tool automatically embeds a provenance
        comment block at the top of every script it generates,
        recording the stem ID, name, category, parameters, and
        whether it modifies the model.  The provenance block is
        part of the code and MUST be included when you display it.

        Args:
                     "modify.set_parameter", "view.switch_active")
            params: JSON string of parameters for the stem.
                    Example: '{"category_name": "Walls", "limit": 50}'

        Returns:
            The rendered code with full provenance for user review.
            You MUST display the full code block to the user and wait
            for explicit approval.
        """
        try:
            if isinstance(params, str):
                param_dict = json.loads(params)
            else:
                param_dict = params

            stem = registry.get(stem_id)
            if not stem:
                available = registry.list_all()
                suggestions = [
                    s["id"]
                    for s in available
                    if any(part in s["id"] for part in stem_id.split("."))
                ]
                msg = f"Unknown stem: '{stem_id}'."
                if suggestions:
                    msg += f" Did you mean: {', '.join(suggestions[:5])}?"
                msg += " Use list_stems to see all available stems."
                return msg

            code = registry.render_stem(stem_id, param_dict)

            if ctx:
                await ctx.info(f"Stem '{stem.name}' — returning code for user review.")

            modifies = (
                "YES ⚠ (uses transaction)"
                if stem.requires_transaction
                else "No (read-only)"
            )
            header_lines = [
                f"# ── Provenance ──────────────────────────────────────",
                f"# Stem ID   : {stem.id}",
                f"# Stem Name : {stem.name}",
                f"# Category  : {stem.category}",
                f"# Description: {stem.description}",
                f"# Modifies Model: {modifies}",
                f"# Parameters: {json.dumps(param_dict)}",
                f"# ────────────────────────────────────────────────────",
            ]
            header = "\n".join(header_lines) + "\n"

            full_code = header + code
            code_id = store_pending(
                full_code, stem.description, source=f"stem:{stem.id}"
            )

            return (
                f"## Prepared Code — awaiting your approval\n\n"
                f"**Stem: {stem.name}** (`{stem.id}`)\n"
                f"**Modifies model:** {modifies}\n"
                f"**Code ID:** `{code_id}`\n\n"
                f"```python\n{full_code}\n```\n\n"
                f"---\n\n"
                f"⚠ **DISPLAY INSTRUCTION:** You MUST include the COMPLETE "
                f"code block above in your message to the user — do NOT "
                f"summarise, truncate, or rewrite it.  The user needs to "
                f"see the exact code that will be executed.\n\n"
                f"Ask the user: *Please review the code above.  "
                f"Shall I go ahead and execute it?*"
            )

        except json.JSONDecodeError as e:
            return f'Invalid JSON in params: {e}. Provide params as a JSON string like: \'{{"key": "value"}}\''
        except ValueError as e:
            return f"Parameter error: {e}"
        except (ConnectionError, RuntimeError) as e:
            error_msg = f"Error preparing stem: {e}"
            if ctx:
                await ctx.error(error_msg)
            return error_msg

    @mcp.tool()
    async def execute_stem_chain(
        steps: str,
        ctx: Context = None,
    ) -> str:
        """
        Prepare a chain of internal stems for execution in Revit.

        ⚠ WORKFLOW REQUIREMENT: Call plan_revit_action FIRST to determine
        the right combination of stems.  This tool is Step 4 in the
        mandatory workflow.

        This tool NEVER auto-executes code.  It renders all steps into a
        single IronPython script with full provenance and returns it for
        user review.

        If any step modifies the model, the entire chain is wrapped in a
        single transaction with rollback-on-error.

        After the user approves, pass the code_id to execute_revit_code.

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

        PROVENANCE: This tool automatically embeds a provenance
        comment block at the top of every script it generates,
        listing each chained stem, its parameters, and whether the
        chain modifies the model.  The provenance block is part of
        the code and MUST be included when you display it.

        Args:
            steps: JSON string — an array of step objects.
                   Each step: {"stem_id": "...", "params": {...}}
                   Example: '[
                     {"stem_id": "query.elements_by_category", "params": {"category_name": "Walls"}},
                     {"stem_id": "query.count_by_category", "params": {"category_names": "Doors,Windows"}}
                   ]'

        Returns:
            The rendered code with full provenance for user review.
            You MUST display the full code block to the user and wait
            for explicit approval.
        """
        try:
            if isinstance(steps, str):
                step_list = json.loads(steps)
            else:
                step_list = steps

            if not isinstance(step_list, list) or len(step_list) == 0:
                return (
                    "Steps must be a non-empty JSON array of {stem_id, params} objects."
                )

            any_modifying = False
            for i, step in enumerate(step_list):
                sid = step.get("stem_id")
                if not sid:
                    return f"Step {i + 1} is missing 'stem_id'."
                stem = registry.get(sid)
                if not stem:
                    return f"Unknown stem in step {i + 1}: '{sid}'. Use list_stems to see available stems."
                if stem.requires_transaction:
                    any_modifying = True

            code = registry.render_chain(step_list)

            if ctx:
                await ctx.info(
                    f"Stem chain ({len(step_list)} steps) — returning code for user review."
                )

            modifies = (
                "YES ⚠ (single transaction with rollback)"
                if any_modifying
                else "No (all read-only)"
            )
            header_lines = [
                "# ── Stem Chain — Provenance ─────────────────────────",
                f"# Modifies Model: {modifies}",
            ]
            for i, step in enumerate(step_list):
                s = registry.get(step["stem_id"])
                tag = "⚠ MODIFIES" if s.requires_transaction else "read-only"
                p = step.get("params", {})
                header_lines.append(
                    f"#   Step {i + 1}: {s.name} (Stem ID: {s.id}) [{tag}]"
                )
                if p:
                    header_lines.append(f"#            Params: {json.dumps(p)}")
            header_lines.append(
                "# ────────────────────────────────────────────────────"
            )
            header = "\n".join(header_lines) + "\n\n"

            stem_names = [registry.get(s["stem_id"]).name for s in step_list]
            description = " → ".join(stem_names)

            full_code = header + code
            stem_ids = ", ".join(s.get("stem_id", "") for s in step_list)
            code_id = store_pending(
                full_code, description, source=f"stem_chain:{stem_ids}"
            )

            return (
                f"## Prepared Code — awaiting your approval\n\n"
                f"**Stem Chain: {description}**\n"
                f"**Modifies model:** {modifies}\n"
                f"**Code ID:** `{code_id}`\n\n"
                f"```python\n{full_code}\n```\n\n"
                f"---\n\n"
                f"⚠ **DISPLAY INSTRUCTION:** You MUST include the COMPLETE "
                f"code block above in your message to the user — do NOT "
                f"summarise, truncate, or rewrite it.  The user needs to "
                f"see the exact code that will be executed.\n\n"
                f"Ask the user: *Please review the code above.  "
                f"Shall I go ahead and execute it?*"
            )

        except json.JSONDecodeError as e:
            return f"Invalid JSON in steps: {e}"
        except ValueError as e:
            return f"Chain error: {e}"
        except (ConnectionError, RuntimeError) as e:
            error_msg = f"Error preparing stem chain: {e}"
            if ctx:
                await ctx.error(error_msg)
            return error_msg

    @mcp.tool()
    async def get_stem_details(
        stem_id: str,
        ctx: Context = None,
    ) -> str:
        """
        Get full details about a specific internal stem, including its
        code template.

        Use this to understand exactly what a stem does before executing it.

        Args:
            stem_id: The stem identifier (e.g. "query.elements_by_category")

        Returns:
            Full stem details including parameters and code template.
        """
        stem = registry.get(stem_id)
        if not stem:
            return f"Unknown stem: '{stem_id}'. Use list_stems to see available stems."

        lines = [
            f"=== {stem.name} ===",
            f"ID: {stem.id}",
            f"Category: {stem.category}",
            f"Description: {stem.description}",
            f"Requires Transaction: {stem.requires_transaction}",
        ]

        if stem.output_description:
            lines.append(f"Output: {stem.output_description}")

        if stem.parameters:
            lines.append("\nParameters:")
            for p in stem.parameters:
                req = "required" if p.required else f"optional (default: {p.default})"
                lines.append(f"  {p.name} ({p.param_type}, {req})")
                lines.append(f"    {p.description}")
                if p.choices:
                    lines.append(f"    Choices: {p.choices}")

        lines.append(f"\nCode Template:\n```python\n{stem.code_template}\n```")

        return "\n".join(lines)

    @mcp.tool()
    async def preview_stem_execution(
        stem_id: str = None,
        params: str = "{}",
        steps: str = None,
        ctx: Context = None,
    ) -> str:
        """
        Preview and explain how internal stems will be used WITHOUT
        executing anything in Revit.

        This is a dry-run / debug tool. It shows:
        - Which stem(s) were selected and why
        - How parameters are validated and applied
        - The final IronPython code that WOULD be sent to Revit
        - Whether a transaction would be used
        - A step-by-step walkthrough of what the code does

        Use this to verify your plan before calling execute_stem or
        execute_stem_chain.

        Provide EITHER stem_id+params (single stem) OR steps (chain).

        Args:
            stem_id: A single stem ID to preview.
            params: JSON string of parameters for the single stem.
            steps: JSON string — array of step objects for a chain preview.

        Returns:
            A detailed explanation of the execution plan and the
            generated IronPython code, without executing anything.
        """
        try:
            lines = []

            if steps:
                if isinstance(steps, str):
                    step_list = json.loads(steps)
                else:
                    step_list = steps

                if not isinstance(step_list, list) or len(step_list) == 0:
                    return "Steps must be a non-empty JSON array of {stem_id, params} objects."

                lines.append("=" * 60)
                lines.append(
                    "  STEM CHAIN PREVIEW (DRY RUN — nothing will be executed)"
                )
                lines.append("=" * 60)
                lines.append(f"\nChain length: {len(step_list)} step(s)\n")

                any_txn = False
                for i, step in enumerate(step_list):
                    sid = step.get("stem_id", "")
                    sparams = step.get("params", {})
                    stem = registry.get(sid)

                    lines.append(f"── Step {i + 1} {'─' * 45}")
                    if not stem:
                        lines.append(f"  ✗ UNKNOWN STEM: '{sid}'")
                        lines.append(
                            f"    This step would FAIL. Use list_stems to find valid IDs."
                        )
                        continue

                    if stem.requires_transaction:
                        any_txn = True

                    lines.append(f"  Stem: {stem.name}  ({stem.id})")
                    lines.append(f"  Category: {stem.category}")
                    lines.append(f"  Description: {stem.description}")
                    lines.append(f"  Requires Transaction: {stem.requires_transaction}")

                    lines.append(
                        f"\n  Parameters supplied: {json.dumps(sparams, indent=4)}"
                    )
                    lines.append(f"  Parameter validation:")
                    for p in stem.parameters:
                        raw = sparams.get(p.name)
                        status = (
                            "✓"
                            if raw is not None
                            else ("✓ default" if not p.required else "✗ MISSING")
                        )
                        effective = raw if raw is not None else p.default
                        lines.append(
                            f"    {status} {p.name} ({p.param_type}): {effective!r}"
                        )
                        if p.choices:
                            lines.append(f"        Allowed: {p.choices}")

                    lines.append("")

                lines.append(f"\n{'─' * 60}")
                if any_txn:
                    lines.append(
                        "⚠ Transaction: YES — the chain contains model-modifying steps."
                    )
                    lines.append(
                        "  All steps will be wrapped in a SINGLE Revit transaction."
                    )
                    lines.append("  On error, ALL changes roll back.")
                else:
                    lines.append("Transaction: No — all steps are read-only.")

                try:
                    code = registry.render_chain(step_list)
                    lines.append(f"\n{'─' * 60}")
                    lines.append("GENERATED CODE (what would be sent to Revit):")
                    lines.append(f"{'─' * 60}")
                    for line_num, line in enumerate(code.splitlines(), 1):
                        lines.append(f"  {line_num:4d} | {line}")
                except ValueError as ve:
                    lines.append(f"\n✗ Code generation failed: {ve}")

            elif stem_id:
                if isinstance(params, str):
                    param_dict = json.loads(params)
                else:
                    param_dict = params

                stem = registry.get(stem_id)
                if not stem:
                    available = registry.list_all()
                    suggestions = [
                        s["id"]
                        for s in available
                        if any(part in s["id"] for part in stem_id.split("."))
                    ]
                    msg = f"Unknown stem: '{stem_id}'."
                    if suggestions:
                        msg += f" Did you mean: {', '.join(suggestions[:5])}?"
                    msg += " Use list_stems to see all available stems."
                    return msg

                lines.append("=" * 60)
                lines.append("  STEM PREVIEW (DRY RUN — nothing will be executed)")
                lines.append("=" * 60)

                lines.append(f"\n  Stem: {stem.name}")
                lines.append(f"  ID: {stem.id}")
                lines.append(f"  Category: {stem.category}")
                lines.append(f"  Description: {stem.description}")
                lines.append(f"  Requires Transaction: {stem.requires_transaction}")
                if stem.output_description:
                    lines.append(f"  Expected Output: {stem.output_description}")

                lines.append(f"\n{'─' * 60}")
                lines.append("PARAMETER RESOLUTION:")
                lines.append(f"  Supplied: {json.dumps(param_dict, indent=4)}")
                lines.append("")

                all_valid = True
                for p in stem.parameters:
                    raw = param_dict.get(p.name)
                    if raw is not None:
                        try:
                            validated = p.validate(raw)
                            lines.append(
                                f"  ✓ {p.name}: {raw!r} → {validated!r} ({p.param_type})"
                            )
                        except ValueError as ve:
                            lines.append(f"  ✗ {p.name}: {raw!r} — INVALID: {ve}")
                            all_valid = False
                    elif not p.required:
                        lines.append(
                            f"  ✓ {p.name}: (not supplied) → default {p.default!r}"
                        )
                    else:
                        lines.append(f"  ✗ {p.name}: MISSING (required)")
                        all_valid = False
                    if p.choices:
                        lines.append(f"      Allowed values: {p.choices}")

                lines.append(f"\n{'─' * 60}")
                lines.append("EXECUTION PLAN:")
                if stem.requires_transaction:
                    lines.append("  1. Open a Revit Transaction")
                    lines.append(f"  2. Execute '{stem.name}' code")
                    lines.append("  3. Commit transaction (or rollback on error)")
                else:
                    lines.append(
                        f"  1. Execute '{stem.name}' code (no transaction needed)"
                    )

                if all_valid:
                    try:
                        code = registry.render_stem(stem_id, param_dict)
                        lines.append(f"\n{'─' * 60}")
                        lines.append("GENERATED CODE (what would be sent to Revit):")
                        lines.append(f"{'─' * 60}")
                        for line_num, line in enumerate(code.splitlines(), 1):
                            lines.append(f"  {line_num:4d} | {line}")
                        lines.append(f"\n  Total: {len(code.splitlines())} lines")
                    except ValueError as ve:
                        lines.append(f"\n  ✗ Code generation failed: {ve}")
                else:
                    lines.append(
                        f"\n  ✗ Cannot generate code — fix parameter errors above."
                    )

            else:
                return (
                    "Provide either stem_id (for a single stem preview) "
                    "or steps (for a chain preview)."
                )

            lines.append(f"\n{'=' * 60}")
            lines.append("  END OF PREVIEW — no code was executed")
            lines.append("=" * 60)

            return "\n".join(lines)

        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        except Exception as e:
            return f"Preview error: {e}"
