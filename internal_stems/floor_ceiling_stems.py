# -*- coding: utf-8 -*-
"""
Floor and ceiling stems — query and creation operations.

Based on patterns from duHast.Revit.Floors and duHast.Revit.Ceilings.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_floor_ceiling_stems(registry: StemRegistry) -> None:
    """Register all floor and ceiling stems."""

    # ── Floor types ─────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.floor_types",
            name="Get Floor Types",
            category="query",
            description=(
                "List all floor types in the model with name, "
                "family name (Floor vs Foundation Slab), and if available, "
                "the default thickness."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, FloorType, BuiltInParameter

floor_types = FilteredElementCollector(doc).OfClass(FloorType).ToElements()
count = 0
for ft in sorted(floor_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    fam_name = ""
    try:
        fp = ft.get_Parameter(BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        if fp:
            fam_name = " | Family: {{}}".format(fp.AsString())
    except:
        pass

    thick_str = ""
    try:
        cs = ft.GetCompoundStructure()
        if cs:
            total = sum(cs.GetLayerWidth(i) for i in range(cs.LayerCount))
            thick_str = " | Thickness: {{}}ft ({{}}mm)".format(
                round(total, 4), round(total * 304.8, 1))
    except:
        pass

    print("ID: {{}} | Name: {{}}{{}}{{}}".format(
        ft.Id.IntegerValue, ft.Name, fam_name, thick_str))
    count += 1

print("\\nTotal: {{}} floor type(s)".format(count))
""",
            output_description="List of floor types with ID, name, family, and thickness.",
        )
    )

    # ── Floor instances ─────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.floor_instances",
            name="Get Floor Instances",
            category="query",
            description=(
                "List placed floor instances with area, level, "
                "type name, and slope info."
            ),
            parameters=[
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of floors to return",
                    required=False,
                    default=100,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter
)

floors = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Floors)
    .WhereElementIsNotElementType()
    .ToElements())

limit = {limit}
count = 0
for f in floors:
    if count >= limit:
        break

    ft = doc.GetElement(f.GetTypeId())
    type_name = ft.Name if ft else "Unknown"

    area_str = ""
    try:
        ap = f.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
        if ap:
            area_str = " | Area: {{}}".format(ap.AsValueString())
    except:
        pass

    level_str = ""
    try:
        lp = f.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if lp:
            level_str = " | Level: {{}}".format(lp.AsValueString())
    except:
        pass

    offset_str = ""
    try:
        op = f.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
        if op:
            offset_str = " | Offset: {{}}".format(op.AsValueString())
    except:
        pass

    slope_str = ""
    try:
        sp = f.get_Parameter(BuiltInParameter.ROOF_SLOPE)
        if sp and sp.AsDouble() != 0:
            slope_str = " | Slope: {{}}".format(sp.AsValueString())
    except:
        pass

    print("ID: {{}} | Type: {{}}{{}}{{}}{{}}{{}}".format(
        f.Id.IntegerValue, type_name, area_str, level_str, offset_str, slope_str))
    count += 1

print("\\nTotal: {{}} floor(s) shown".format(count))
""",
            output_description="List of floor instances with properties.",
        )
    )

    # ── Ceiling types ───────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.ceiling_types",
            name="Get Ceiling Types",
            category="query",
            description=(
                "List all ceiling types in the model with name and family name."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, BuiltInParameter

ceiling_types = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Ceilings)
    .WhereElementIsElementType()
    .ToElements())

count = 0
for ct in sorted(ceiling_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    fam_name = ""
    try:
        fp = ct.get_Parameter(BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        if fp:
            fam_name = " | Family: {{}}".format(fp.AsString())
    except:
        pass

    print("ID: {{}} | Name: {{}}{{}}".format(
        ct.Id.IntegerValue, ct.Name, fam_name))
    count += 1

print("\\nTotal: {{}} ceiling type(s)".format(count))
""",
            output_description="List of ceiling types with ID, name, and family.",
        )
    )

    # ── Ceiling instances ───────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.ceiling_instances",
            name="Get Ceiling Instances",
            category="query",
            description=(
                "List placed ceiling instances with area, level, "
                "height offset, and type name."
            ),
            parameters=[
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of ceilings to return",
                    required=False,
                    default=100,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter
)

ceilings = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Ceilings)
    .WhereElementIsNotElementType()
    .ToElements())

limit = {limit}
count = 0
for c in ceilings:
    if count >= limit:
        break

    ct = doc.GetElement(c.GetTypeId())
    type_name = ct.Name if ct else "Unknown"

    area_str = ""
    try:
        ap = c.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
        if ap:
            area_str = " | Area: {{}}".format(ap.AsValueString())
    except:
        pass

    level_str = ""
    try:
        lp = c.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if lp:
            level_str = " | Level: {{}}".format(lp.AsValueString())
    except:
        pass

    height_str = ""
    try:
        hp = c.get_Parameter(BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM)
        if hp:
            height_str = " | Height Offset: {{}}".format(hp.AsValueString())
    except:
        pass

    print("ID: {{}} | Type: {{}}{{}}{{}}{{}}".format(
        c.Id.IntegerValue, type_name, area_str, level_str, height_str))
    count += 1

print("\\nTotal: {{}} ceiling(s) shown".format(count))
""",
            output_description="List of ceiling instances with properties.",
        )
    )

    # ── Create ceiling ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.create_ceiling",
            name="Create Ceiling",
            category="modify",
            description=(
                "Create a rectangular ceiling on a specified level with a "
                "given ceiling type. Points are in feet."
            ),
            parameters=[
                StemParameter(
                    "level_name",
                    "str",
                    "Name of the level to place the ceiling on",
                ),
                StemParameter(
                    "ceiling_type_name",
                    "str",
                    "Name of the ceiling type to use",
                ),
                StemParameter(
                    "x1",
                    "float",
                    "X coordinate of first corner (feet)",
                ),
                StemParameter(
                    "y1",
                    "float",
                    "Y coordinate of first corner (feet)",
                ),
                StemParameter(
                    "x2",
                    "float",
                    "X coordinate of opposite corner (feet)",
                ),
                StemParameter(
                    "y2",
                    "float",
                    "Y coordinate of opposite corner (feet)",
                ),
                StemParameter(
                    "height_offset",
                    "float",
                    "Height offset above level (feet)",
                    required=False,
                    default=0.0,
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, Level, BuiltInCategory, BuiltInParameter,
    XYZ, CurveLoop, Line, ElementId
)
import clr
clr.AddReference("RevitAPI")

# Find level
levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
level = None
for lv in levels:
    if lv.Name == "{level_name}":
        level = lv
        break
if level is None:
    print("Level '{level_name}' not found. Available:")
    for lv in levels:
        print("  " + lv.Name)
else:
    # Find ceiling type
    ceiling_types = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Ceilings)
        .WhereElementIsElementType()
        .ToElements())
    ct = None
    for t in ceiling_types:
        if t.Name == "{ceiling_type_name}":
            ct = t
            break
    if ct is None:
        print("Ceiling type '{ceiling_type_name}' not found. Available:")
        for t in ceiling_types:
            print("  " + t.Name)
    else:
        x1, y1 = {x1}, {y1}
        x2, y2 = {x2}, {y2}
        p0 = XYZ(x1, y1, 0)
        p1 = XYZ(x2, y1, 0)
        p2 = XYZ(x2, y2, 0)
        p3 = XYZ(x1, y2, 0)
        loop = CurveLoop()
        loop.Append(Line.CreateBound(p0, p1))
        loop.Append(Line.CreateBound(p1, p2))
        loop.Append(Line.CreateBound(p2, p3))
        loop.Append(Line.CreateBound(p3, p0))
        try:
            ceiling = DB.Ceiling.Create(doc, [loop], ct.Id, level.Id)
            offset = {height_offset}
            if offset != 0.0:
                hp = ceiling.get_Parameter(BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM)
                if hp:
                    hp.Set(offset)
            print("Created ceiling ID: {{}}".format(ceiling.Id.IntegerValue))
            print("Type: {ceiling_type_name}")
            print("Level: {level_name}")
        except Exception as e:
            print("Failed to create ceiling: {{}}".format(e))
""",
            output_description="Confirmation with new ceiling element ID.",
        )
    )
