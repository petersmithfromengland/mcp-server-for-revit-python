# Stems — Pre-defined Code Building Blocks for Revit MCP

## What Are Stems?

Stems are **parameterized IronPython code templates** that constrain Revit code execution to safe, well-tested operations. Instead of allowing an LLM to write and execute arbitrary code inside Revit, stems provide a library of building blocks that the LLM selects from, fills in parameters, and runs.

Think of each stem as a function with a fixed body and named holes (parameters) that get filled in at runtime. The LLM never writes raw IronPython — it only **discovers** available stems, **chooses** the right one, **supplies** parameter values, and **executes** the rendered code through the existing Revit Routes API.

### Why Stems?

| Without Stems | With Stems |
|---|---|
| LLM writes arbitrary IronPython | LLM picks from a curated catalogue |
| Unpredictable API usage, easy to hit edge cases | Every template is hand-written and tested |
| Hard to audit what was executed | Every execution traces back to a known stem ID |
| Transaction handling is ad-hoc | Transactions are managed automatically by the registry |

---

## Architecture Overview

```
stems/                          ← Stem definitions (IronPython templates)
├── __init__.py                 ← Package entry — exports get_registry()
├── registry.py                 ← Core engine: Stem, StemParameter, StemRegistry
├── query_stems.py              ← Read-only query operations (9 stems)
├── modify_stems.py             ← Model-modifying operations (8 stems)
├── view_stems.py               ← View / UI operations (7 stems)
├── wall_stems.py               ← Wall queries and modifications (4 stems)
├── floor_ceiling_stems.py      ← Floor and ceiling operations (5 stems)
├── room_stems.py               ← Room queries and creation (4 stems)
├── door_window_stems.py        ← Door and window queries + placement (4 stems)
├── family_stems.py             ← Family management (5 stems)
├── level_grid_stems.py         ← Level and grid operations (7 stems)
├── parameter_stems.py          ← Advanced parameter read/write (4 stems)
├── workset_phase_group_stems.py← Workset, phase, group, design option ops (7 stems)
├── material_link_stems.py      ← Material queries and linked models (4 stems)
└── sheet_schedule_filter_stems.py ← Sheets, schedules, filters, templates (10 stems)

tools/
├── stem_tools.py               ← MCP tool definitions that expose stems to the LLM
└── __init__.py                 ← Registers stem_tools alongside other tools
```

### Data Flow

```
LLM (Claude)
  │
  ├─ list_stems() ──────────────────────────────────► StemRegistry.list_all()
  │                                                         │
  ├─ preview_stem_execution(stem_id, params) ──────► render code (dry run)
  │                                                         │
  ├─ execute_stem(stem_id, params) ────────────────► StemRegistry.render_stem()
  │                                                         │
  │   or                                                    ▼
  │                                               rendered IronPython code
  ├─ execute_stem_chain(steps) ────────────────────► StemRegistry.render_chain()
  │                                                         │
  │                                                         ▼
  │                                               POST /execute_code/ ──► Revit
  │                                                         │
  └─ receives output ◄─────────────────────────────── stdout capture
```

---

## MCP Tools Exposed to Claude

These are the tools an LLM client sees when connected to the MCP server:

| Tool | Purpose |
|---|---|
| `list_stems` | Browse all stems, filter by category (`query`, `modify`, `view`), or search by keyword. Always call this first. |
| `execute_stem` | Run a single stem with parameters. **Read-only stems execute immediately; modification stems return the code for review.** |
| `execute_stem_chain` | Run multiple stems sequentially. **If any step modifies the model, the full code is returned for review instead of executing.** Read-only chains execute immediately. |
| `get_stem_details` | Inspect a stem's full definition, parameters, and raw code template. |
| `preview_stem_execution` | **Dry-run / debug tool.** Shows the parameter resolution, execution plan, and generated IronPython code that *would* be sent to Revit — without actually executing anything. Use for verification and debugging. |

### Execution Modes

Stems follow a **review-before-execute** policy for any operation that modifies the Revit model:

| Stem Type | Behaviour | Example |
|---|---|---|
| Read-only (`requires_transaction=False`) | Auto-executed immediately; result returned | `query.elements_by_category`, `view.list_views` |
| Model-modifying (`requires_transaction=True`) | Code returned as a **code block for review** with stem ID/name comments | `modify.set_parameter`, `view.set_scale` |

When a modification stem (or a chain containing one) is invoked via `execute_stem` / `execute_stem_chain`, the tool:

1. Renders the full IronPython code (including transaction wrapping)
2. Adds **comment headers** with the Stem ID, name, description, and parameters
3. Returns the code inside a fenced code block with a warning message
4. The user (or LLM) can review the code, then pass it to `execute_revit_code` to run it

This ensures no model changes happen without explicit approval.

### Typical LLM Workflow

1. **Discover:** Call `list_stems()` (optionally with `category="query"` or `search="wall"`)
2. **Understand:** Call `get_stem_details("query.elements_by_category")` to see parameters and code
3. **Preview:** Call `preview_stem_execution(stem_id="query.elements_by_category", params='{"category_name": "Walls"}')` to see the full generated code without executing
4. **Execute (read-only):** Call `execute_stem("query.elements_by_category", '{"category_name": "Walls"}')` — runs immediately, result returned
5. **Execute (modification):** Call `execute_stem("modify.set_parameter", '{"element_ids": "123", ...}')` — code block returned for review
6. **Approve & Run:** After reviewing the returned code, pass it to `execute_revit_code` to run it in Revit
7. **Compose:** Call `execute_stem_chain` with multiple steps — same review/auto-execute rules apply based on whether the chain modifies the model

---

## Available Stems Reference

### Core Query Stems (read-only, no transaction)

| Stem ID | Description |
|---|---|
| `query.elements_by_category` | Collect element instances in a category (ID, name, type, level) |
| `query.count_by_category` | Count instances across one or more categories |
| `query.element_properties` | Get all parameter values for an element by ID |
| `query.elements_by_parameter` | Filter elements where a parameter matches a value |
| `query.element_location` | Get XYZ location / bounding box of an element |
| `query.list_categories` | List all categories that have elements in the model |
| `query.room_data` | Room details: number, name, area, level, department |
| `query.list_sheets` | Sheets with number, name, and placed views |
| `query.model_warnings` | Retrieve model warnings with affected element IDs |

### Core Modify Stems (auto-wrapped in transaction)

| Stem ID | Description |
|---|---|
| `modify.set_parameter` | Set a parameter value on elements by ID |
| `modify.delete_elements` | Delete elements by ID |
| `modify.move_element` | Move elements by a translation vector (feet) |
| `modify.copy_element` | Copy elements with an offset |
| `modify.rotate_element` | Rotate elements around their vertical axis (degrees) |
| `modify.create_wall` | Create a straight wall between two points on a level |
| `modify.create_floor` | Create a rectangular floor on a level |
| `modify.rename_view` | Rename a view |

### View Stems (mixed — transaction only where noted)

| Stem ID | Transaction? | Description |
|---|---|---|
| `view.switch_active` | No | Switch the active view by name |
| `view.list_views` | No | List non-template views with type and scale |
| `view.get_properties` | No | Get detailed properties of a view |
| `view.elements_in_view` | No | Count visible elements by category in a view |
| `view.set_scale` | Yes | Set view scale |
| `view.set_detail_level` | Yes | Set detail level (Coarse / Medium / Fine) |
| `view.create_3d` | Yes | Create a new isometric 3D view |

### Wall Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.wall_types` | No | List all wall types with family, width, and function |
| `query.wall_instances` | No | List wall instances with length, height, area, and level |
| `query.curtain_wall_elements` | No | List curtain wall sub-elements (panels, mullions) |
| `modify.set_wall_location_line` | Yes | Set wall location line reference (Center, Interior, Exterior, etc.) |

### Floor & Ceiling Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.floor_types` | No | List all floor types with family and structure info |
| `query.floor_instances` | No | List floor instances with area, level, and slope |
| `query.ceiling_types` | No | List all ceiling types with family info |
| `query.ceiling_instances` | No | List ceiling instances with area and level |
| `modify.create_ceiling` | Yes | Create a rectangular ceiling on a level |

### Room Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.all_rooms` | No | List all rooms (placed, unplaced, enclosed status) |
| `query.room_boundaries` | No | Get room boundary elements (walls, separators) |
| `query.rooms_in_view` | No | List rooms visible in a specific view |
| `modify.create_room` | Yes | Create a room at a point on a level |

### Door & Window Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.door_instances` | No | List door instances with host wall, level, room info |
| `query.door_window_types` | No | List all door or window types by category |
| `query.window_instances` | No | List window instances with host wall and sill height |
| `modify.place_door` | Yes | Place a door instance in a wall by family type ID |

### Family Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.loaded_families` | No | List all loaded families by category |
| `query.in_place_families` | No | List in-place (model-in-place) families |
| `query.family_types` | No | List all types within a family |
| `query.family_instances_by_category` | No | List family instances filtered by category |
| `modify.place_family_instance` | Yes | Place a family instance at an XYZ point on a level |

### Level & Grid Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.levels` | No | List all levels with elevation and type |
| `query.level_elevation` | No | Get a specific level's elevation in feet and meters |
| `query.level_types` | No | List all level types in the model |
| `query.grids` | No | List all grids with start/end points and curve type |
| `query.grids_in_view` | No | List grids visible in a specific view |
| `modify.set_grids_2d` | Yes | Switch all grids in a view to 2D extents |
| `modify.toggle_grid_bubbles` | Yes | Toggle grid bubbles on/off at start or end |

### Parameter Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.element_parameters_detailed` | No | Get all parameters of an element with storage type, read-only flag, etc. |
| `query.parameter_value_by_name` | No | Get a specific named parameter value from multiple elements |
| `query.builtin_parameter` | No | Read a BuiltInParameter value from an element by enum name |
| `modify.set_builtin_parameter` | Yes | Set a BuiltInParameter value on an element by enum name |

### Workset, Phase & Group Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.worksets` | No | List all user worksets with element counts |
| `query.element_workset` | No | Get the workset of a specific element |
| `query.phases` | No | List all phases with element counts |
| `query.groups` | No | List all model and detail groups with instance counts |
| `query.design_options` | No | List all design option sets and options |
| `modify.create_workset` | Yes | Create a new user workset |
| `modify.change_element_workset` | Yes | Move elements to a different workset |

### Material & Link Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.materials` | No | List all materials with color, class, and transparency |
| `query.element_material` | No | Get all materials used by an element (including paint) |
| `query.revit_links` | No | List Revit and CAD links with status and instance counts |
| `query.image_links` | No | List image types with file paths |

### Sheet, Schedule, Filter & Template Stems

| Stem ID | Transaction? | Description |
|---|---|---|
| `query.sheets` | No | List all sheets with number, name, revision, viewport count |
| `query.sheet_detail` | No | Get detailed sheet info with viewports and title block |
| `query.schedules` | No | List all schedules with category and sheet placement status |
| `query.view_filters` | No | List all view filters with optional usage info |
| `query.unused_view_filters` | No | Find filters not applied to any view or template |
| `query.view_templates` | No | List view templates with type, filter count, usage count |
| `query.unused_view_templates` | No | Find unused view templates (not assigned to any view) |
| `query.views_not_on_sheet` | No | Find views not placed on any sheet |
| `modify.apply_filter_to_view` | Yes | Apply an existing filter to a view |
| `modify.create_sheet` | Yes | Create a new sheet with a title block |

---

## How to Add a New Stem

### 1. Choose the Right File

| If your stem… | Add it to |
|---|---|
| Reads data without changing the model | `stems/query_stems.py` |
| Modifies the Revit model | `stems/modify_stems.py` |
| Operates on views or the UI | `stems/view_stems.py` |
| Doesn't fit any of the above | Create a new file: `stems/<category>_stems.py` |

### 2. Write the Stem Definition

Every stem is registered by calling `registry.register(Stem(...))` inside the module's `register_*_stems()` function. Here's the anatomy of a stem:

```python
from .registry import StemRegistry, Stem, StemParameter

def register_query_stems(registry: StemRegistry) -> None:

    registry.register(
        Stem(
            # ── Identity ──────────────────────────────────────
            stem_id="query.my_new_stem",        # Unique ID: category.snake_case_name
            name="My New Stem",                  # Human-readable name
            category="query",                    # Must match file category
            description="What this stem does.",  # Shown to the LLM

            # ── Parameters ────────────────────────────────────
            parameters=[
                StemParameter(
                    "param_name",       # Name used in {param_name} placeholders
                    "str",              # Type: "str", "int", "float", "bool", "list"
                    "Description",      # Shown to the LLM
                    required=True,      # Default: True
                    default=None,       # Default value if not required
                    choices=None,       # Optional: ["A", "B", "C"]
                ),
            ],

            # ── Behaviour ─────────────────────────────────────
            requires_transaction=False,  # Set True for model-modifying stems
            output_description="What the stem prints.",

            # ── Code Template ─────────────────────────────────
            code_template="""\
# IronPython code that runs inside Revit.
# Available globals: doc, uidoc, DB, revit, print
#
# Parameter placeholders use {param_name} syntax.
# Use {{ and }} for literal braces (e.g. Python dicts, .format() calls).

value = "{param_name}"
print("Parameter value: {{}}".format(value))
""",
        )
    )
```

### 3. Template Syntax Rules

| Syntax | Meaning | Example |
|---|---|---|
| `{param_name}` | Replaced with the parameter value | `"{category_name}"` → `"Walls"` |
| `{{` | Literal `{` in output (for Python dicts/format) | `category_map = {{` → `category_map = {` |
| `}}` | Literal `}` in output | `}}` → `}` |

**Important:** Stem code templates must **never** include transaction code (`Transaction`, `t.Start()`, `t.Commit()`, etc.). The registry automatically wraps modification stems in a transaction at render time.

### 4. Globals Available in Code Templates

These variables are injected into the IronPython execution namespace by the Revit-side `code_execution.py` route:

| Variable | Type | Description |
|---|---|---|
| `doc` | `Document` | The active Revit document |
| `uidoc` | `UIDocument` | The active UI document (for view switching, etc.) |
| `DB` | `namespace` | `Autodesk.Revit.DB` — the Revit API Database namespace |
| `revit` | `module` | The pyRevit module |
| `print` | `function` | Captured print — output is returned in the response |

### 5. Register a New Category (if needed)

If you created a new file `stems/material_stems.py`:

1. Add your `register_material_stems(registry)` function in the new file
2. Import and call it from `stems/registry.py` in `_load_builtin_stems()`:

```python
def _load_builtin_stems(registry: StemRegistry) -> None:
    from .query_stems import register_query_stems
    from .modify_stems import register_modify_stems
    from .view_stems import register_view_stems
    from .material_stems import register_material_stems  # ← add

    register_query_stems(registry)
    register_modify_stems(registry)
    register_view_stems(registry)
    register_material_stems(registry)  # ← add
```

That's it. The new stems are automatically picked up by all MCP tools (`list_stems`, `execute_stem`, etc.) because they read from the shared `StemRegistry` singleton.

---

## How Stems Become Discoverable by Claude

For Claude (or any LLM connected via MCP) to use a stem, it goes through this chain:

```
Stem registered in registry
        ↓
list_stems tool returns it
        ↓
Claude sees it in tool output
        ↓
Claude calls execute_stem with the ID and params
```

There is **nothing else to configure**. As long as your stem is registered with `registry.register(Stem(...))` and the module is imported in `_load_builtin_stems()`, the stem appears automatically in `list_stems` output and can be executed.

### Checklist for New Stems

- [ ] Stem ID follows the `category.snake_case_name` convention
- [ ] Name and description are clear — Claude reads these to decide which stem to use
- [ ] Parameters have descriptive names and descriptions
- [ ] `requires_transaction` is set correctly (True for any model modification)
- [ ] Code template uses `{{` / `}}` for literal braces
- [ ] Code template does **not** include transaction code
- [ ] Output uses `print()` so results are captured
- [ ] The module's `register_*_stems()` function is called from `_load_builtin_stems()` in `registry.py`
- [ ] Tested with `preview_stem_execution` before live use

---

## Debugging and Previewing

### preview_stem_execution

The `preview_stem_execution` tool is a dry-run debugger. It shows exactly what would happen without touching Revit:

```
preview_stem_execution(
    stem_id="modify.move_element",
    params='{"element_ids": "12345", "dx": 5.0, "dy": 0.0}'
)
```

Output includes:
- Stem identity and description
- Parameter validation results (✓ valid / ✗ missing or invalid)
- Execution plan (transaction or not)
- Full numbered source code that would be sent to Revit

For chains:

```
preview_stem_execution(
    steps='[
        {"stem_id": "query.elements_by_category", "params": {"category_name": "Walls"}},
        {"stem_id": "modify.move_element", "params": {"element_ids": "100", "dx": 10, "dy": 0}}
    ]'
)
```

### Testing from Python

You can also test stem rendering directly without the MCP server:

```python
from stems import get_registry

registry = get_registry()

# List all stems
for s in registry.list_all():
    print(s["id"], "-", s["name"])

# Render a single stem
code = registry.render_stem("query.elements_by_category", {"category_name": "Walls", "limit": 10})
print(code)

# Render a chain
code = registry.render_chain([
    {"stem_id": "query.count_by_category", "params": {"category_names": "Walls,Doors"}},
    {"stem_id": "query.list_categories", "params": {}},
])
print(code)
```

---

## Transaction Handling

Stems never contain their own transaction code. Instead, the `StemRegistry` handles transactions at render time:

- **`render_stem()`** — If the stem has `requires_transaction=True`, the rendered code is wrapped in a `DB.Transaction` / `t.Start()` / `try` / `t.Commit()` / `except` / `t.RollBack()` block.
- **`render_chain()`** — If *any* step in the chain requires a transaction, the *entire* chain is wrapped in a **single** shared transaction. This prevents nested transactions (which Revit doesn't support) and ensures atomic rollback.
- **Read-only stems** — No transaction wrapping. The code runs as-is.
