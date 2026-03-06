# -*- coding: utf-8 -*-
"""
Level and grid stems — query and modification operations.

Based on patterns from duHast.Revit.Levels and duHast.Revit.Grids.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_level_grid_stems(registry: StemRegistry) -> None:
    """Register all level and grid stems."""

    # ── Levels with elevations ──────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.levels",
            name="Get Levels",
            category="query",
            description=(
                "List all levels in the model sorted by elevation. "
                "Shows elevation in feet and metric, plus level type."
            ),
            parameters=[
                StemParameter(
                    "sort_order",
                    "str",
                    "Sort by elevation: 'ascending' or 'descending'",
                    required=False,
                    default="ascending",
                    choices=["ascending", "descending"],
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, Level, BuiltInParameter

levels = (FilteredElementCollector(doc)
    .OfClass(Level)
    .ToElements())

reverse = "{sort_order}" == "descending"
sorted_levels = sorted(levels, key=lambda l: l.ProjectElevation, reverse=reverse)

for lv in sorted_levels:
    elev_ft = round(lv.ProjectElevation, 4)
    elev_mm = round(lv.ProjectElevation * 304.8, 1)

    type_name = ""
    try:
        lt = doc.GetElement(lv.GetTypeId())
        if lt:
            type_name = " | Type: {{}}".format(lt.Name)
    except:
        pass

    story_str = ""
    try:
        bp = lv.get_Parameter(BuiltInParameter.LEVEL_IS_BUILDING_STORY)
        if bp:
            story_str = " | Building Story: {{}}".format("Yes" if bp.AsInteger() == 1 else "No")
    except:
        pass

    print("ID: {{}} | Name: {{}} | Elevation: {{}}ft ({{}}mm){{}}{{}}".format(
        lv.Id.IntegerValue, lv.Name, elev_ft, elev_mm, type_name, story_str))

print("\\nTotal: {{}} level(s)".format(len(sorted_levels)))
""",
            output_description="List of levels with elevations and type.",
        )
    )

    # ── Level elevation by name ─────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.level_elevation",
            name="Get Level Elevation by Name",
            category="query",
            description=(
                "Get the elevation of a specific level by name. "
                "Returns both project elevation and survey elevation."
            ),
            parameters=[
                StemParameter(
                    "level_name",
                    "str",
                    "Name of the level",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, Level

levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
found = False
for lv in levels:
    if lv.Name == "{level_name}":
        print("Level: {{}}".format(lv.Name))
        print("Project Elevation: {{}} ft ({{}} mm)".format(
            round(lv.ProjectElevation, 4),
            round(lv.ProjectElevation * 304.8, 1)))
        print("Elevation: {{}} ft ({{}} mm)".format(
            round(lv.Elevation, 4),
            round(lv.Elevation * 304.8, 1)))
        print("Element ID: {{}}".format(lv.Id.IntegerValue))
        found = True
        break

if not found:
    print("Level '{level_name}' not found. Available:")
    for lv in sorted(levels, key=lambda l: l.ProjectElevation):
        print("  {{}} ({{}} ft)".format(lv.Name, round(lv.ProjectElevation, 4)))
""",
            output_description="Level elevation details.",
        )
    )

    # ── Grid data ───────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.grids",
            name="Get Grids",
            category="query",
            description=(
                "List all grids in the model with their name, type, "
                "curve type (linear or arc), and extent coordinates."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, Grid, Line, Arc

grids = FilteredElementCollector(doc).OfClass(Grid).ToElements()

linear = 0
arc_count = 0
for g in sorted(grids, key=lambda x: x.Name):
    grid_type = doc.GetElement(g.GetTypeId())
    type_name = grid_type.Name if grid_type else "?"

    curve = g.Curve
    if isinstance(curve, Line):
        curve_type = "Linear"
        linear += 1
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
        extent_str = "Start: ({{}}, {{}}) | End: ({{}}, {{}})".format(
            round(start.X, 2), round(start.Y, 2),
            round(end.X, 2), round(end.Y, 2))
    elif isinstance(curve, Arc):
        curve_type = "Arc"
        arc_count += 1
        center = curve.Center
        radius = round(curve.Radius, 2)
        extent_str = "Center: ({{}}, {{}}) | Radius: {{}}".format(
            round(center.X, 2), round(center.Y, 2), radius)
    else:
        curve_type = "Multi-segment"
        extent_str = ""

    print("ID: {{}} | Name: {{}} | Type: {{}} | Curve: {{}} | {{}}".format(
        g.Id.IntegerValue, g.Name, type_name, curve_type, extent_str))

print("\\nTotal: {{}} grid(s) ({{}} linear, {{}} arc)".format(
    len(grids), linear, arc_count))
""",
            output_description="List of grids with type, curve shape, and extents.",
        )
    )

    # ── Grids in view ───────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.grids_in_view",
            name="Get Grids in View",
            category="query",
            description=(
                "List grids visible in a specific view with their "
                "bubble visibility status and extent type (2D/3D)."
            ),
            parameters=[
                StemParameter(
                    "view_name",
                    "str",
                    "Name of the view to query",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, Grid, View, DatumExtentType, DatumEnds
)

# Find view
views = FilteredElementCollector(doc).OfClass(View).ToElements()
target_view = None
for v in views:
    if hasattr(v, 'Name') and v.Name == "{view_name}":
        target_view = v
        break

if target_view is None:
    print("View '{view_name}' not found.")
else:
    grids = (FilteredElementCollector(doc, target_view.Id)
        .OfClass(Grid)
        .ToElements())

    for g in sorted(grids, key=lambda x: x.Name):
        bubble_0 = ""
        bubble_1 = ""
        extent_type = ""
        try:
            bubble_0 = "Visible" if g.IsBubbleVisibleInView(DatumEnds.End0, target_view) else "Hidden"
            bubble_1 = "Visible" if g.IsBubbleVisibleInView(DatumEnds.End1, target_view) else "Hidden"
        except:
            bubble_0 = "N/A"
            bubble_1 = "N/A"

        try:
            ext = g.GetDatumExtentTypeInView(DatumEnds.End0, target_view)
            extent_type = "2D" if ext == DatumExtentType.ViewSpecific else "3D"
        except:
            extent_type = "?"

        print("ID: {{}} | Name: {{}} | Extent: {{}} | Bubble End0: {{}} | Bubble End1: {{}}".format(
            g.Id.IntegerValue, g.Name, extent_type, bubble_0, bubble_1))

    print("\\nTotal: {{}} grid(s) in view '{view_name}'".format(len(grids)))
""",
            output_description="Grids visible in view with bubble visibility and 2D/3D status.",
        )
    )

    # ── Set grids to 2D ─────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.set_grids_2d",
            name="Set Grids to 2D in View",
            category="modify",
            description=(
                "Set all grids in a view to 2D (view-specific) extents. "
                "This is useful for controlling grid display per view."
            ),
            parameters=[
                StemParameter(
                    "view_name",
                    "str",
                    "Name of the view to modify grids in",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, Grid, View, DatumExtentType, DatumEnds
)

# Find view
views = FilteredElementCollector(doc).OfClass(View).ToElements()
target_view = None
for v in views:
    if hasattr(v, 'Name') and v.Name == "{view_name}":
        target_view = v
        break

if target_view is None:
    print("View '{view_name}' not found.")
else:
    grids = (FilteredElementCollector(doc, target_view.Id)
        .OfClass(Grid)
        .ToElements())

    changed = 0
    for g in grids:
        try:
            g.SetDatumExtentType(DatumEnds.End0, target_view, DatumExtentType.ViewSpecific)
            g.SetDatumExtentType(DatumEnds.End1, target_view, DatumExtentType.ViewSpecific)
            changed += 1
            print("Set grid '{{}}' to 2D".format(g.Name))
        except Exception as e:
            print("Failed to set grid '{{}}' to 2D: {{}}".format(g.Name, e))

    print("\\nChanged {{}} grid(s) to 2D in view '{view_name}'".format(changed))
""",
            output_description="Confirmation for each grid changed to 2D.",
        )
    )

    # ── Toggle grid bubbles ─────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.toggle_grid_bubbles",
            name="Toggle Grid Bubbles",
            category="modify",
            description=(
                "Show or hide grid bubbles at a specific end for all "
                "grids in a view, or toggle their current state."
            ),
            parameters=[
                StemParameter(
                    "view_name",
                    "str",
                    "Name of the view",
                ),
                StemParameter(
                    "end",
                    "str",
                    "Which end: 'end0', 'end1', or 'both'",
                    choices=["end0", "end1", "both"],
                ),
                StemParameter(
                    "action",
                    "str",
                    "Action: 'show', 'hide', or 'toggle'",
                    choices=["show", "hide", "toggle"],
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, Grid, View, DatumEnds
)

# Find view
views = FilteredElementCollector(doc).OfClass(View).ToElements()
target_view = None
for v in views:
    if hasattr(v, 'Name') and v.Name == "{view_name}":
        target_view = v
        break

if target_view is None:
    print("View '{view_name}' not found.")
else:
    grids = (FilteredElementCollector(doc, target_view.Id)
        .OfClass(Grid)
        .ToElements())

    end_choice = "{end}"
    action = "{action}"
    ends = []
    if end_choice in ("end0", "both"):
        ends.append(DatumEnds.End0)
    if end_choice in ("end1", "both"):
        ends.append(DatumEnds.End1)

    changed = 0
    for g in grids:
        for datum_end in ends:
            try:
                if action == "show":
                    g.ShowBubbleInView(datum_end, target_view)
                elif action == "hide":
                    g.HideBubbleInView(datum_end, target_view)
                elif action == "toggle":
                    if g.IsBubbleVisibleInView(datum_end, target_view):
                        g.HideBubbleInView(datum_end, target_view)
                    else:
                        g.ShowBubbleInView(datum_end, target_view)
                changed += 1
            except Exception as e:
                print("Failed on grid '{{}}': {{}}".format(g.Name, e))

    print("{{}} bubble(s) on {{}} grid(s) in view '{view_name}'".format(
        action.title() + ("d" if action != "show" else "n"), changed))
""",
            output_description="Confirmation of grid bubble changes.",
        )
    )

    # ── Level types ─────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.level_types",
            name="Get Level Types",
            category="query",
            description=("List all level types and level head types in the model."),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, FamilySymbol
)

# Level types
level_types = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Levels)
    .WhereElementIsElementType()
    .ToElements())

print("=== LEVEL TYPES ===")
for lt in sorted(level_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    print("ID: {{}} | Name: {{}}".format(lt.Id.IntegerValue, lt.Name))
print("Total: {{}}".format(len(level_types)))

# Level head types
print("\\n=== LEVEL HEAD TYPES ===")
heads = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_LevelHeads)
    .WhereElementIsElementType()
    .ToElements())

for h in sorted(heads, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    fam_name = ""
    if isinstance(h, FamilySymbol) and h.Family:
        fam_name = " | Family: {{}}".format(h.Family.Name)
    print("ID: {{}} | Name: {{}}{{}}".format(
        h.Id.IntegerValue, h.Name, fam_name))
print("Total: {{}}".format(len(heads)))

# Grid types
print("\\n=== GRID TYPES ===")
grid_types = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Grids)
    .WhereElementIsElementType()
    .ToElements())

for gt in sorted(grid_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    print("ID: {{}} | Name: {{}}".format(gt.Id.IntegerValue, gt.Name))
print("Total: {{}}".format(len(grid_types)))
""",
            output_description="Level types, level head types, and grid types.",
        )
    )
