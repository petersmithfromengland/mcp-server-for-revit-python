# -*- coding: utf-8 -*-
"""
Wall stems — wall-specific query and modification operations.

Based on patterns from duHast.Revit.Walls.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_wall_stems(registry: StemRegistry) -> None:
    """Register all wall-related stems."""

    # ── Wall types ──────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.wall_types",
            name="Get Wall Types",
            category="query",
            description=(
                "List all wall types in the model with their family kind "
                "(Basic, Curtain, Stacked), width, and function."
            ),
            parameters=[
                StemParameter(
                    "kind_filter",
                    "str",
                    "Filter by wall kind: 'basic', 'curtain', 'stacked', or 'all'",
                    required=False,
                    default="all",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, WallType, WallKind

wall_types = FilteredElementCollector(doc).OfClass(WallType).ToElements()
kind_filter = "{kind_filter}".lower()

kind_map = {{
    "basic": WallKind.Basic,
    "curtain": WallKind.Curtain,
    "stacked": WallKind.Stacked,
}}

count = 0
for wt in sorted(wall_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    try:
        wk = wt.Kind
        kind_name = str(wk).split(".")[-1] if "." in str(wk) else str(wk)
    except:
        kind_name = "Unknown"

    if kind_filter != "all":
        target_kind = kind_map.get(kind_filter)
        if target_kind is not None and wt.Kind != target_kind:
            continue

    width_str = ""
    try:
        width = wt.Width
        width_ft = round(width, 4)
        width_mm = round(width * 304.8, 1)
        width_str = " | Width: {{}}ft ({{}}mm)".format(width_ft, width_mm)
    except:
        pass

    func_str = ""
    try:
        func_param = wt.get_Parameter(DB.BuiltInParameter.WALL_ATTR_DEFN_OF_WALL_USAGE)
        if func_param:
            func_str = " | Function: {{}}".format(func_param.AsValueString())
    except:
        pass

    print("ID: {{}} | Name: {{}} | Kind: {{}}{{}}{{}}".format(
        wt.Id.IntegerValue, wt.Name, kind_name, width_str, func_str))
    count += 1

print("\\nTotal: {{}} wall type(s)".format(count))
""",
            output_description="List of wall types with ID, name, kind, width, and function.",
        )
    )

    # ── Wall instances ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.wall_instances",
            name="Get Wall Instances",
            category="query",
            description=(
                "List placed wall instances with length, height, area, "
                "level, location line type, and type name."
            ),
            parameters=[
                StemParameter(
                    "kind_filter",
                    "str",
                    "Filter by wall kind: 'basic', 'curtain', 'stacked', or 'all'",
                    required=False,
                    default="all",
                ),
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of walls to return",
                    required=False,
                    default=100,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter, WallKind
)

walls = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Walls)
    .WhereElementIsNotElementType()
    .ToElements())

kind_filter = "{kind_filter}".lower()
limit = {limit}
kind_map = {{
    "basic": WallKind.Basic,
    "curtain": WallKind.Curtain,
    "stacked": WallKind.Stacked,
}}

count = 0
for w in walls:
    if count >= limit:
        break

    try:
        wt = doc.GetElement(w.GetTypeId())
        wk = wt.Kind if wt else None
    except:
        wk = None

    if kind_filter != "all" and wk is not None:
        target_kind = kind_map.get(kind_filter)
        if target_kind is not None and wk != target_kind:
            continue

    kind_name = str(wk).split(".")[-1] if wk and "." in str(wk) else str(wk) if wk else "Unknown"
    type_name = wt.Name if wt else "Unknown"

    length_str = ""
    try:
        lp = w.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        if lp:
            length_str = " | Length: {{}}".format(lp.AsValueString())
    except:
        pass

    height_str = ""
    try:
        hp = w.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM)
        if hp:
            height_str = " | Height: {{}}".format(hp.AsValueString())
    except:
        pass

    area_str = ""
    try:
        ap = w.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
        if ap:
            area_str = " | Area: {{}}".format(ap.AsValueString())
    except:
        pass

    level_str = ""
    try:
        lvl = doc.GetElement(w.LevelId)
        if lvl:
            level_str = " | Level: {{}}".format(lvl.Name)
    except:
        pass

    loc_line = ""
    try:
        loc_param = w.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM)
        if loc_param:
            loc_line = " | Location Line: {{}}".format(loc_param.AsValueString())
    except:
        pass

    print("ID: {{}} | Type: {{}} | Kind: {{}}{{}}{{}}{{}}{{}}{{}}".format(
        w.Id.IntegerValue, type_name, kind_name,
        length_str, height_str, area_str, level_str, loc_line))
    count += 1

print("\\nTotal: {{}} wall(s) shown".format(count))
""",
            output_description="List of wall instances with properties.",
        )
    )

    # ── Curtain wall elements ───────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.curtain_wall_elements",
            name="Get Curtain Wall Elements",
            category="query",
            description=(
                "List panels and mullions of curtain walls. "
                "Returns panel type, mullion type, and host wall for each element."
            ),
            parameters=[
                StemParameter(
                    "element_type",
                    "str",
                    "Element type to list: 'panels', 'mullions', or 'all'",
                    required=False,
                    default="all",
                    choices=["panels", "mullions", "all"],
                ),
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of elements to return",
                    required=False,
                    default=100,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, Element
)

element_type = "{element_type}".lower()
limit = {limit}
count = 0

if element_type in ("panels", "all"):
    panels = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_CurtainWallPanels)
        .WhereElementIsNotElementType()
        .ToElements())
    print("=== CURTAIN WALL PANELS ===")
    for p in panels:
        if count >= limit:
            break
        pt = doc.GetElement(p.GetTypeId())
        pt_name = pt.Name if pt else "Unknown"
        host_str = ""
        try:
            host = p.Host
            if host:
                host_str = " | Host Wall ID: {{}}".format(host.Id.IntegerValue)
        except:
            pass
        print("ID: {{}} | Type: {{}}{{}}".format(
            p.Id.IntegerValue, pt_name, host_str))
        count += 1

if element_type in ("mullions", "all"):
    mullions = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_CurtainWallMullions)
        .WhereElementIsNotElementType()
        .ToElements())
    print("\\n=== CURTAIN WALL MULLIONS ===")
    for m in mullions:
        if count >= limit:
            break
        mt = doc.GetElement(m.GetTypeId())
        mt_name = mt.Name if mt else "Unknown"
        print("ID: {{}} | Type: {{}}".format(m.Id.IntegerValue, mt_name))
        count += 1

print("\\nTotal: {{}} element(s) shown".format(count))
""",
            output_description="List of curtain wall panels and/or mullions.",
        )
    )

    # ── Set wall location line ──────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.set_wall_location_line",
            name="Set Wall Location Line",
            category="modify",
            description=(
                "Set the wall location line reference for one or more walls. "
                "Options: Wall Centerline, Core Centerline, Finish Face: Exterior, "
                "Finish Face: Interior, Core Face: Exterior, Core Face: Interior."
            ),
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated wall element IDs",
                ),
                StemParameter(
                    "reference_type",
                    "str",
                    "Location line reference type",
                    choices=[
                        "Wall Centerline",
                        "Core Centerline",
                        "Finish Face: Exterior",
                        "Finish Face: Interior",
                        "Core Face: Exterior",
                        "Core Face: Interior",
                    ],
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId, BuiltInParameter, WallLocationLine

ref_map = {{
    "Wall Centerline": WallLocationLine.WallCenterline,
    "Core Centerline": WallLocationLine.CoreCenterline,
    "Finish Face: Exterior": WallLocationLine.FinishFaceExterior,
    "Finish Face: Interior": WallLocationLine.FinishFaceInterior,
    "Core Face: Exterior": WallLocationLine.CoreExterior,
    "Core Face: Interior": WallLocationLine.CoreInterior,
}}

ids = [int(x.strip()) for x in "{element_ids}".split(",")]
ref_type = "{reference_type}"
target = ref_map.get(ref_type)

if target is None:
    print("Unknown reference type: {{}}".format(ref_type))
    print("Available: {{}}".format(", ".join(ref_map.keys())))
else:
    updated = 0
    for eid_int in ids:
        elem = doc.GetElement(ElementId(eid_int))
        if elem is None:
            print("Element not found: {{}}".format(eid_int))
            continue
        param = elem.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM)
        if param is None or param.IsReadOnly:
            print("Cannot set location line on element {{}}".format(eid_int))
            continue
        param.Set(int(target))
        updated += 1
        print("Set location line to '{{}}' on wall {{}}".format(ref_type, eid_int))
    print("\\nUpdated {{}} wall(s)".format(updated))
""",
            output_description="Confirmation for each updated wall.",
        )
    )
