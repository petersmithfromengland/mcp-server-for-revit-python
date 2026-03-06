# -*- coding: utf-8 -*-
"""
Door and window stems — query and creation operations.

Based on patterns from duHast.Revit.Doors.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_door_window_stems(registry: StemRegistry) -> None:
    """Register all door and window stems."""

    # ── Door instances ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.door_instances",
            name="Get Door Instances",
            category="query",
            description=(
                "List placed door instances with type, family, host wall, "
                "level, from/to room, and mark. Distinguishes between "
                "basic wall doors and curtain wall doors."
            ),
            parameters=[
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of doors to return",
                    required=False,
                    default=100,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    FamilyInstance, ElementCategoryFilter
)

doors = (FilteredElementCollector(doc)
    .OfClass(FamilyInstance)
    .WherePasses(ElementCategoryFilter(BuiltInCategory.OST_Doors))
    .ToElements())

limit = {limit}
count = 0
for d in doors:
    if count >= limit:
        break

    sym = doc.GetElement(d.GetTypeId())
    type_name = sym.Name if sym else "Unknown"

    fam_name = ""
    try:
        fam = sym.Family if sym else None
        if fam:
            fam_name = " | Family: {{}}".format(fam.Name)
    except:
        pass

    host_str = ""
    try:
        host = d.Host
        if host:
            host_str = " | Host: {{}} (ID: {{}})".format(
                host.Name if hasattr(host, 'Name') else "?",
                host.Id.IntegerValue)
    except:
        pass

    level_str = ""
    try:
        lp = d.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if lp:
            level_str = " | Level: {{}}".format(lp.AsValueString())
    except:
        pass

    from_room = ""
    try:
        fr = d.FromRoom
        if fr:
            from_room = " | From: {{}} {{}}".format(
                fr.get_Parameter(BuiltInParameter.ROOM_NUMBER).AsString() or "",
                fr.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or "")
    except:
        pass

    to_room = ""
    try:
        tr = d.ToRoom
        if tr:
            to_room = " | To: {{}} {{}}".format(
                tr.get_Parameter(BuiltInParameter.ROOM_NUMBER).AsString() or "",
                tr.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or "")
    except:
        pass

    mark = ""
    try:
        mp = d.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if mp and mp.AsString():
            mark = " | Mark: {{}}".format(mp.AsString())
    except:
        pass

    print("ID: {{}} | Type: {{}}{{}}{{}}{{}}{{}}{{}}{{}}".format(
        d.Id.IntegerValue, type_name, fam_name, host_str,
        level_str, from_room, to_room, mark))
    count += 1

print("\\nTotal: {{}} door(s) shown".format(count))
""",
            output_description="List of door instances with host, rooms, and properties.",
        )
    )

    # ── Door/window types ───────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.door_window_types",
            name="Get Door and Window Types",
            category="query",
            description=(
                "List all door and/or window family types in the model "
                "with family name, type name, and instance count."
            ),
            parameters=[
                StemParameter(
                    "category_filter",
                    "str",
                    "Category to list: 'doors', 'windows', or 'both'",
                    required=False,
                    default="both",
                    choices=["doors", "windows", "both"],
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, FamilySymbol,
    FamilyInstance, ElementCategoryFilter
)

cat_filter = "{category_filter}".lower()

categories = []
if cat_filter in ("doors", "both"):
    categories.append(("DOORS", BuiltInCategory.OST_Doors))
if cat_filter in ("windows", "both"):
    categories.append(("WINDOWS", BuiltInCategory.OST_Windows))

for cat_label, bic in categories:
    print("=== {{}} ===".format(cat_label))

    symbols = (FilteredElementCollector(doc)
        .OfClass(FamilySymbol)
        .WherePasses(ElementCategoryFilter(bic))
        .ToElements())

    instances = (FilteredElementCollector(doc)
        .OfClass(FamilyInstance)
        .WherePasses(ElementCategoryFilter(bic))
        .ToElements())

    # Count instances per type
    type_counts = {{}}
    for inst in instances:
        tid = inst.GetTypeId().IntegerValue
        type_counts[tid] = type_counts.get(tid, 0) + 1

    for s in sorted(symbols, key=lambda x: x.Family.Name + " : " + x.Name if hasattr(x, 'Family') else x.Name):
        fam_name = s.Family.Name if hasattr(s, 'Family') and s.Family else "?"
        placed = type_counts.get(s.Id.IntegerValue, 0)
        print("ID: {{}} | {{}} : {{}} | Placed: {{}}".format(
            s.Id.IntegerValue, fam_name, s.Name, placed))

    print("Total types: {{}}\\n".format(len(symbols)))
""",
            output_description="List of door/window types with family name and instance count.",
        )
    )

    # ── Window instances ────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.window_instances",
            name="Get Window Instances",
            category="query",
            description=(
                "List placed window instances with type, family, host wall, "
                "level, sill height, and mark."
            ),
            parameters=[
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of windows to return",
                    required=False,
                    default=100,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    FamilyInstance, ElementCategoryFilter
)

windows = (FilteredElementCollector(doc)
    .OfClass(FamilyInstance)
    .WherePasses(ElementCategoryFilter(BuiltInCategory.OST_Windows))
    .ToElements())

limit = {limit}
count = 0
for w in windows:
    if count >= limit:
        break

    sym = doc.GetElement(w.GetTypeId())
    type_name = sym.Name if sym else "Unknown"

    fam_name = ""
    try:
        fam = sym.Family if sym else None
        if fam:
            fam_name = " | Family: {{}}".format(fam.Name)
    except:
        pass

    host_str = ""
    try:
        host = w.Host
        if host:
            host_str = " | Host: {{}} (ID: {{}})".format(
                host.Name if hasattr(host, 'Name') else "?",
                host.Id.IntegerValue)
    except:
        pass

    level_str = ""
    try:
        lp = w.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if lp:
            level_str = " | Level: {{}}".format(lp.AsValueString())
    except:
        pass

    sill_str = ""
    try:
        sp = w.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)
        if sp:
            sill_str = " | Sill Height: {{}}".format(sp.AsValueString())
    except:
        pass

    mark = ""
    try:
        mp = w.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if mp and mp.AsString():
            mark = " | Mark: {{}}".format(mp.AsString())
    except:
        pass

    print("ID: {{}} | Type: {{}}{{}}{{}}{{}}{{}}{{}}".format(
        w.Id.IntegerValue, type_name, fam_name, host_str,
        level_str, sill_str, mark))
    count += 1

print("\\nTotal: {{}} window(s) shown".format(count))
""",
            output_description="List of window instances with host, level, and properties.",
        )
    )

    # ── Place door in wall ──────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.place_door",
            name="Place Door in Wall",
            category="modify",
            description=(
                "Place a door instance in a wall at a specified location. "
                "The door type must already be loaded in the project."
            ),
            parameters=[
                StemParameter(
                    "door_type_name",
                    "str",
                    "Name of the door type (family type name)",
                ),
                StemParameter(
                    "wall_id",
                    "int",
                    "Element ID of the host wall",
                ),
                StemParameter(
                    "x",
                    "float",
                    "X coordinate for door placement (feet)",
                ),
                StemParameter(
                    "y",
                    "float",
                    "Y coordinate for door placement (feet)",
                ),
                StemParameter(
                    "z",
                    "float",
                    "Z coordinate for door placement (feet)",
                    required=False,
                    default=0.0,
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, FamilySymbol,
    ElementCategoryFilter, ElementId, XYZ, Structure
)

# Find door symbol
symbols = (FilteredElementCollector(doc)
    .OfClass(FamilySymbol)
    .WherePasses(ElementCategoryFilter(BuiltInCategory.OST_Doors))
    .ToElements())

door_sym = None
for s in symbols:
    if s.Name == "{door_type_name}":
        door_sym = s
        break

if door_sym is None:
    print("Door type '{door_type_name}' not found. Available:")
    for s in sorted(symbols, key=lambda x: x.Name):
        fam = s.Family.Name if hasattr(s, 'Family') and s.Family else "?"
        print("  {{}} : {{}}".format(fam, s.Name))
else:
    wall = doc.GetElement(ElementId({wall_id}))
    if wall is None:
        print("Wall not found: {wall_id}")
    else:
        if not door_sym.IsActive:
            door_sym.Activate()
            doc.Regenerate()

        level = doc.GetElement(wall.LevelId)
        location = XYZ({x}, {y}, {z})

        door = doc.Create.NewFamilyInstance(
            location, door_sym, wall, level,
            Structure.StructuralType.NonStructural)

        print("Placed door ID: {{}}".format(door.Id.IntegerValue))
        print("Type: {door_type_name}")
        print("In wall ID: {wall_id}")
""",
            output_description="Confirmation with new door element ID.",
        )
    )
