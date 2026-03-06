# -*- coding: utf-8 -*-
"""
Room stems — extended room query and creation operations.

Based on patterns from duHast.Revit.Rooms.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_room_stems(registry: StemRegistry) -> None:
    """Register all room-related stems."""

    # ── All rooms with status ───────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.all_rooms",
            name="Get All Rooms with Status",
            category="query",
            description=(
                "List all rooms in the model with their placement status "
                "(placed, unplaced, not enclosed, redundant), area, level, "
                "and phase. Useful for model health checks."
            ),
            parameters=[
                StemParameter(
                    "status_filter",
                    "str",
                    "Filter: 'placed', 'unplaced', 'not_enclosed', 'redundant', or 'all'",
                    required=False,
                    default="all",
                ),
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of rooms to return",
                    required=False,
                    default=200,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    SpatialElementBoundaryOptions
)

rooms = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Rooms)
    .ToElements())

status_filter = "{status_filter}".lower()
limit = {limit}
count = 0
stats = {{"placed": 0, "unplaced": 0, "not_enclosed": 0, "redundant": 0}}

for r in rooms:
    if count >= limit:
        break

    # Determine status
    if r.Location is None:
        status = "unplaced"
    elif r.Area == 0:
        opts = SpatialElementBoundaryOptions()
        segs = r.GetBoundarySegments(opts)
        if segs and segs.Count > 0:
            status = "redundant"
        else:
            status = "not_enclosed"
    else:
        status = "placed"

    stats[status] = stats.get(status, 0) + 1

    if status_filter != "all" and status != status_filter:
        continue

    number = ""
    try:
        np = r.get_Parameter(BuiltInParameter.ROOM_NUMBER)
        if np:
            number = np.AsString() or ""
    except:
        pass

    name = ""
    try:
        nmp = r.get_Parameter(BuiltInParameter.ROOM_NAME)
        if nmp:
            name = nmp.AsString() or ""
    except:
        pass

    area_str = ""
    if status == "placed":
        try:
            area_str = " | Area: {{}}".format(
                r.get_Parameter(BuiltInParameter.ROOM_AREA).AsValueString())
        except:
            pass

    level_str = ""
    try:
        lvl = doc.GetElement(r.LevelId)
        if lvl:
            level_str = " | Level: {{}}".format(lvl.Name)
    except:
        pass

    phase_str = ""
    try:
        pp = r.get_Parameter(BuiltInParameter.ROOM_PHASE)
        if pp:
            phase_el = doc.GetElement(pp.AsElementId())
            if phase_el:
                phase_str = " | Phase: {{}}".format(phase_el.Name)
    except:
        pass

    dept_str = ""
    try:
        dp = r.get_Parameter(BuiltInParameter.ROOM_DEPARTMENT)
        if dp and dp.AsString():
            dept_str = " | Dept: {{}}".format(dp.AsString())
    except:
        pass

    print("ID: {{}} | {{}} - {{}} | Status: {{}}{{}}{{}}{{}}{{}}".format(
        r.Id.IntegerValue, number, name, status.upper(),
        area_str, level_str, phase_str, dept_str))
    count += 1

print("\\n--- Summary ---")
for k, v in sorted(stats.items()):
    print("  {{}}: {{}}".format(k, v))
print("Total rooms: {{}}".format(sum(stats.values())))
""",
            output_description="List of rooms with status, area, level, phase, and department.",
        )
    )

    # ── Room boundaries ─────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.room_boundaries",
            name="Get Room Boundary Elements",
            category="query",
            description=(
                "Get the boundary elements (walls, separation lines, etc.) "
                "of a specific room. Returns element type and ID for each "
                "boundary segment."
            ),
            parameters=[
                StemParameter(
                    "room_id",
                    "int",
                    "Element ID of the room",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    ElementId, SpatialElementBoundaryOptions, SpatialElementBoundaryLocation
)

room = doc.GetElement(ElementId({room_id}))
if room is None:
    print("Room not found: {room_id}")
else:
    print("Room: {{}} - {{}}".format(
        room.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString() or "",
        room.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString() or ""))

    opts = SpatialElementBoundaryOptions()
    opts.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish

    segments = room.GetBoundarySegments(opts)
    if segments is None or segments.Count == 0:
        print("No boundary segments found (room may be unplaced or not enclosed)")
    else:
        for loop_idx in range(segments.Count):
            loop = segments[loop_idx]
            print("\\n--- Boundary Loop {{}} ---".format(loop_idx + 1))
            for seg in loop:
                elem_id = seg.ElementId
                if elem_id.IntegerValue == -1:
                    print("  Segment: <room separation line or virtual>")
                else:
                    elem = doc.GetElement(elem_id)
                    if elem:
                        cat_name = elem.Category.Name if elem.Category else "Unknown"
                        print("  Segment: {{}} | ID: {{}} | Category: {{}}".format(
                            elem.Name if hasattr(elem, 'Name') else "?",
                            elem_id.IntegerValue, cat_name))
                    else:
                        print("  Segment: Element ID {{}} (not found)".format(
                            elem_id.IntegerValue))

        total_segs = sum(loop.Count for loop in segments)  # type: ignore
        print("\\nTotal: {{}} loop(s), {{}} segment(s)".format(
            segments.Count, total_segs))
""",
            output_description="Boundary elements of a room grouped by loop.",
        )
    )

    # ── Rooms in view ───────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.rooms_in_view",
            name="Get Rooms in View",
            category="query",
            description=(
                "List all rooms visible in a specific view. "
                "Returns room number, name, area, and level."
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
    FilteredElementCollector, BuiltInCategory, BuiltInParameter, View
)

# Find the view
views = FilteredElementCollector(doc).OfClass(View).ToElements()
target_view = None
for v in views:
    if hasattr(v, 'Name') and v.Name == "{view_name}":
        target_view = v
        break

if target_view is None:
    print("View '{view_name}' not found.")
else:
    rooms = (FilteredElementCollector(doc, target_view.Id)
        .OfCategory(BuiltInCategory.OST_Rooms)
        .ToElements())

    count = 0
    for r in rooms:
        number = ""
        try:
            np = r.get_Parameter(BuiltInParameter.ROOM_NUMBER)
            if np:
                number = np.AsString() or ""
        except:
            pass

        name = ""
        try:
            nmp = r.get_Parameter(BuiltInParameter.ROOM_NAME)
            if nmp:
                name = nmp.AsString() or ""
        except:
            pass

        area_str = ""
        try:
            if r.Area > 0:
                area_str = " | Area: {{}}".format(
                    r.get_Parameter(BuiltInParameter.ROOM_AREA).AsValueString())
        except:
            pass

        level_str = ""
        try:
            lvl = doc.GetElement(r.LevelId)
            if lvl:
                level_str = " | Level: {{}}".format(lvl.Name)
        except:
            pass

        print("ID: {{}} | {{}} - {{}}{{}}{{}}".format(
            r.Id.IntegerValue, number, name, area_str, level_str))
        count += 1

    print("\\nTotal: {{}} room(s) in view '{view_name}'".format(count))
""",
            output_description="Rooms visible in the specified view.",
        )
    )

    # ── Create room ─────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.create_room",
            name="Create Room",
            category="modify",
            description=(
                "Create a new room on a level at a specified location point. "
                "Optionally set the room name and number."
            ),
            parameters=[
                StemParameter(
                    "level_name",
                    "str",
                    "Name of the level to place the room on",
                ),
                StemParameter(
                    "x",
                    "float",
                    "X coordinate of room location (feet)",
                ),
                StemParameter(
                    "y",
                    "float",
                    "Y coordinate of room location (feet)",
                ),
                StemParameter(
                    "room_name",
                    "str",
                    "Name for the new room",
                    required=False,
                    default="",
                ),
                StemParameter(
                    "room_number",
                    "str",
                    "Number for the new room",
                    required=False,
                    default="",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, Level, BuiltInParameter, UV
)

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
    location = UV({x}, {y})
    room = doc.Create.NewRoom(level, location)

    room_name = "{room_name}"
    if room_name:
        np = room.get_Parameter(BuiltInParameter.ROOM_NAME)
        if np:
            np.Set(room_name)

    room_number = "{room_number}"
    if room_number:
        rnp = room.get_Parameter(BuiltInParameter.ROOM_NUMBER)
        if rnp:
            rnp.Set(room_number)

    print("Created room ID: {{}}".format(room.Id.IntegerValue))
    final_name = room.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or ""
    final_number = room.get_Parameter(BuiltInParameter.ROOM_NUMBER).AsString() or ""
    print("Number: {{}} | Name: {{}}".format(final_number, final_name))
    print("Level: {level_name}")
""",
            output_description="Confirmation with new room element ID, name, and number.",
        )
    )
