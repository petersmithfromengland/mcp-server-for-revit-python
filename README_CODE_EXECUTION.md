# Code Execution Workflow

This document describes the **gated code execution** system used by the Revit MCP Server. The system ensures that no IronPython code is sent to Revit without the user first seeing and approving it.

---

## Overview

All code destined for Revit passes through a three‑stage pipeline:

```
 ┌─────────────┐      ┌─────────────┐      ┌─────────────────┐
 │  1. PLAN    │ ───▸ │  2. PREPARE │ ───▸ │  3. EXECUTE     │
 │  (analyse)  │      │  (generate) │      │  (user‑approved)│
 └─────────────┘      └─────────────┘      └─────────────────┘
  plan_revit_action    execute_stem          execute_revit_code
                       execute_stem_chain       (code_id only)
                       compose_external_stem
                       prepare_code
```

1. **Plan** — `plan_revit_action` analyses the user's request against internal stems, external libraries, and Revit API docs to produce a structured action plan.
2. **Prepare** — a preparation tool generates the IronPython code, stores it in a pending store, and returns both the **full code block** and a **code\_id** for the user to review.
3. **Execute** — `execute_revit_code` accepts **only** a `code_id` (not raw code). It looks up the stored code and sends it to Revit via the pyRevit Routes API.

No stage can be skipped. The LLM cannot jump straight to execution because `execute_revit_code` refuses raw code strings — it requires a `code_id` that only exists after a preparation tool has stored it.

---

## Configuration

The execution mode is controlled by a single flag in `config.yaml`:

```yaml
allow_implicit_code_execution: false   # default — gated mode
```

| Value     | Mode     | Behaviour |
|-----------|----------|-----------|
| `false`   | **Gated** (default) | Code must be prepared → reviewed → approved → executed via `code_id`. |
| `true`    | **Implicit** | `execute_revit_code` accepts raw code directly (legacy behaviour, no approval gate). |

---

## The Pending Store (`code_execution/pending.py`)

The pending store is the architectural gate between preparation and execution.

### How it works

```
prepare_code("print('hello')", "Test")
         │
         ▼
  ┌──────────────────────────────┐
  │  _pending (in-memory dict)   │
  │                              │
  │  "a1b2c3d4" → {             │
  │    code: "print('hello')",   │
  │    description: "Test",      │
  │    source: "custom",         │
  │    timestamp: 1741209600     │
  │  }                           │
  └──────────────────────────────┘
         │
         ▼
  Returns code_id = "a1b2c3d4"
```

- **`store_pending(code, description, source)`** — generates a `code_id` (first 8 hex chars of the code's SHA-256 hash), stores the entry, and returns the `code_id`.
- **`pop_pending(code_id)`** — retrieves *and removes* the entry. Returns `(code, description)` or raises `KeyError` if not found.
- **`list_pending()`** — returns summaries of all pending entries (for diagnostics).
- **Expiry** — entries automatically expire after **10 minutes** (`EXPIRY_SECONDS = 600`).

Because `pop_pending` removes the entry, each `code_id` can only be executed **once**. Re-execution requires preparing the code again.

---

## Tools Reference

### Always registered

| Tool | Purpose |
|------|---------|
| `plan_revit_action` | **Mandatory first step.** Analyses the user request and returns a structured action plan with matched stems, external library functions, and Revit API members. |

### Gated mode tools (default)

| Tool | Stage | Description |
|------|-------|-------------|
| `execute_stem` | Prepare | Renders a single internal stem template with the given parameters. Returns code + `code_id`. |
| `execute_stem_chain` | Prepare | Renders multiple internal stems into a single script (with transaction wrapping if needed). Returns code + `code_id`. |
| `compose_external_stem` | Prepare | Inlines external library functions (e.g. duHast) into a self-contained IronPython script. Returns code + `code_id`. |
| `prepare_code` | Prepare | Stores arbitrary hand-written IronPython code. Returns code + `code_id`. |
| `execute_revit_code` | Execute | Accepts a `code_id`, looks up the pending code, sends it to Revit. **Refuses raw code.** |
| `list_pending_code` | Diagnostic | Lists all pending `code_id` entries with previews and ages. |

### Implicit mode tools (`allow_implicit_code_execution: true`)

| Tool | Description |
|------|-------------|
| `execute_revit_code` | Accepts raw code directly and sends it to Revit. No approval gate. |

---

## Preparation Tool Behaviour

Every preparation tool (`execute_stem`, `execute_stem_chain`, `compose_external_stem`, `prepare_code`) follows the same contract:

1. **Generates** the IronPython code (from a stem template, composed library functions, or raw input).
2. **Embeds provenance** — comment headers in the code itself recording which stem/library/parameters were used (see [Provenance](#provenance) below).
3. **Stores** the code via `store_pending()` and receives a `code_id`.
4. **Returns** a structured response containing:
   - The **full code block** in a fenced Markdown code block
   - The **Code ID**
   - Metadata (stem name, whether it modifies the model, etc.)
   - An explicit **DISPLAY INSTRUCTION** telling the LLM to show the code verbatim

---

## Provenance

**Every script that passes through the system MUST contain a provenance comment block at its top — on every preparation, including re-preparations after errors.**

Provenance is not optional metadata stored alongside the code; it is *embedded in the code itself* so the user always sees where the code came from when it is displayed.

### Why every iteration?

When code fails and is re-prepared via `prepare_code`, the provenance from the original stem or library would be lost unless it is carried forward. The system enforces this in two ways:

1. **Automatic injection** — `execute_stem`, `execute_stem_chain`, and `compose_external_stem` automatically prepend provenance headers to the generated code. The user never sees code from these tools without provenance.
2. **Enforcement in `prepare_code`** — if the code submitted to `prepare_code` does not already start with a `# ── Provenance` block, one is injected automatically using the `source` and `description` parameters. If a provenance block already exists (e.g. code adapted from a failed stem execution), it is preserved.

### The `source` parameter

`prepare_code` accepts a `source` parameter (default: `"custom"`) that preserves lineage:

| Source value | Meaning |
|-------------|---------|
| `custom` | Code written from scratch |
| `stem:<id>` | Code originally generated by an internal stem (e.g. `stem:query.elements_by_category`) |
| `stem_chain:<id1>,<id2>` | Code originally from a stem chain |
| `external:<library>` | Code originally composed from an external library |

When re-preparing code after an error, the LLM should pass the original source so the provenance chain is maintained.

### Provenance header formats

**Internal stem** (`execute_stem`):

```python
# ── Provenance ──────────────────────────────────────
# Stem ID   : query.elements_by_category
# Stem Name : Elements by Category
# Category  : query
# Description: Query elements from a specific Revit category
# Modifies Model: No (read-only)
# Parameters: {"category_name": "Walls", "limit": 50}
# ────────────────────────────────────────────────────
```

**Stem chain** (`execute_stem_chain`):

```python
# ── Stem Chain — Provenance ─────────────────────────
# Modifies Model: No (all read-only)
#   Step 1: Elements by Category (Stem ID: query.elements_by_category) [read-only]
#            Params: {"category_name": "Walls"}
#   Step 2: Count by Category (Stem ID: query.count_by_category) [read-only]
#            Params: {"category_names": "Doors,Windows"}
# ────────────────────────────────────────────────────
```

**External stem** (`compose_external_stem`):

```python
# ── Provenance ──────────────────────────────────────
# Source     : external
# Library    : duHast
# Functions  : get_all_wall_types, get_wall_type_name
#   - duHast.Revit.Walls.walls.get_all_wall_types
#   - duHast.Revit.Walls.walls.get_wall_type_name
# Modifies   : No (read-only)
# Inlined for pyRevit IronPython 2.7 compatibility
# ────────────────────────────────────────────────────
```

**Custom / re-prepared** (`prepare_code`):

```python
# ── Provenance ──────────────────────────────────────
# Source     : custom
# Description: List all wall types in the active document
# ────────────────────────────────────────────────────
```

When code is re-prepared after an error, the original source is preserved and an `Updated` line is added:

```python
# ── Provenance ──────────────────────────────────────
# Source     : stem:query.elements_by_category
# Description: List walls — fixed Unicode encoding
# Updated: Fixed str.format() and added .encode('ascii','replace')
# ────────────────────────────────────────────────────
```

---

## Error Handling

When `execute_revit_code` encounters an error (either a connection failure or a Revit-side error in the response), the workflow enforces a **full re-preparation cycle**:

1. The error is returned clearly to the LLM.
2. The LLM is instructed to **show the error to the user**.
3. A **fixed version** of the code must be prepared using `prepare_code`, passing the **original `source`** to preserve provenance lineage.
4. The fixed code must include a provenance header (auto-injected if missing) and be displayed **verbatim** for user review.
5. Execution only proceeds after the user approves again.

The LLM is explicitly prevented from silently retrying or auto-fixing code without user visibility.

### Re-preparation preserves provenance

When code originally generated by a stem fails and is re-prepared via `prepare_code`:

- The `source` parameter should carry the original origin (e.g. `"stem:query.elements_by_category"`) so the provenance chain is not broken.
- If the re-prepared code already contains a `# ── Provenance` block from the original stem, it is preserved as-is.
- If the code has been rewritten and no longer has the header, `prepare_code` automatically injects one using the `source` and `description` values.

---

## Display Rules

All preparation tools include prominent display instructions in both their docstrings and return values to ensure the LLM assistant presents code correctly:

```
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
```

These rules exist because LLMs tend to summarise or paraphrase tool responses. By embedding the instructions in the tool's own docstring and response text, the LLM receives them at the point of action.

---

## IronPython 2.7 Constraints

All code is executed in pyRevit's IronPython 2.7 runtime. Key constraints:

| Constraint | Guidance |
|-----------|----------|
| No f-strings | Use `str.format()` — e.g. `"Hello {}".format(name)` |
| Unicode errors | Encode output with `.encode('ascii', 'replace')` |
| Name property | Use `getattr(element, 'Name', 'N/A')` — the `.Name` property can throw |
| Null checks | Always check `if element:` before accessing properties |
| Transactions | Model-modifying code must be wrapped in a `Transaction` |
| Available globals | `doc`, `uidoc`, `DB` (Autodesk.Revit.DB), `revit`, `print()` |

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────┐
│                    MCP Client (LLM)                  │
└────────┬─────────────────────────────────────────────┘
         │
         │  MCP protocol (SSE / streamable-http)
         ▼
┌──────────────────────────────────────────────────────┐
│              FastMCP Server (main.py:8000)            │
│                                                      │
│  ┌────────────────┐  ┌───────────────────────────┐   │
│  │ plan_revit_    │  │ Preparation tools          │   │
│  │ action         │  │  • execute_stem            │   │
│  │ (workflow.py)  │  │  • execute_stem_chain      │   │
│  └───────┬────────┘  │  • compose_external_stem   │   │
│          │           │  • prepare_code            │   │
│          │           └─────────┬─────────────────┘   │
│          │                     │                      │
│          │            store_pending()                 │
│          │                     ▼                      │
│          │         ┌───────────────────┐              │
│          │         │  Pending Store    │              │
│          │         │  (pending.py)     │              │
│          │         │                   │              │
│          │         │  code_id → code   │              │
│          │         └─────────┬─────────┘              │
│          │                   │                        │
│          │           pop_pending()                    │
│          │                   ▼                        │
│          │         ┌───────────────────┐              │
│          │         │ execute_revit_code│              │
│          │         │ (code_id only)    │              │
│          │         └─────────┬─────────┘              │
│          │                   │                        │
│          │           run_approved_code()              │
│          │                   │                        │
└──────────┼───────────────────┼────────────────────────┘
           │                   │
           │                   │  HTTP POST /execute_code/
           │                   ▼
           │         ┌───────────────────┐
           │         │  pyRevit Routes   │
           │         │  (port 48884)     │
           │         │  IronPython 2.7   │
           │         └───────────────────┘
           │                   │
           │                   ▼
           │              ┌─────────┐
           │              │  Revit  │
           │              └─────────┘
           │
           └──── (analysis only — no execution)
```

---

## File Layout

```
code_execution/
├── __init__.py
├── tools.py       # MCP tool registration (branches on config flag)
├── workflow.py    # plan_revit_action — 5-step action planner
├── executor.py    # run_approved_code — sends code to pyRevit Routes
└── pending.py     # store_pending / pop_pending — the approval gate
```
