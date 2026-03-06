# -*- coding: utf-8 -*-
"""
Modify stems — operations that change the Revit model.

All modification stems set ``requires_transaction = True`` so the
registry wraps them in a transaction automatically (both for single
execution via ``render_stem`` and chains via ``render_chain``).

Do NOT include transaction code in code_template — it is added by the
registry layer.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_modify_stems(registry: StemRegistry) -> None:
    """Register all model-modification stems."""

    # ── Set parameter value ─────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.set_parameter",
            name="Set Element Parameter",
            category="modify",
            description=(
                "Set a parameter value on one or more elements by ID. "
                "Supports string, number, and integer parameter types."
            ),
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs (e.g. '12345,67890')",
                ),
                StemParameter(
                    "parameter_name",
                    "str",
                    "Name of the parameter to set",
                ),
                StemParameter(
                    "parameter_value",
                    "str",
                    "Value to set (will be auto-converted to correct type)",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId

ids = [int(x.strip()) for x in "{element_ids}".split(",")]
param_name = "{parameter_name}"
param_val = "{parameter_value}"

updated = 0
for eid_int in ids:
    elem = doc.GetElement(ElementId(eid_int))
    if elem is None:
        print("Element not found: {{}}".format(eid_int))
        continue
    param = elem.LookupParameter(param_name)
    if param is None:
        print("Parameter '{{}}' not found on element {{}}".format(param_name, eid_int))
        continue
    if param.IsReadOnly:
        print("Parameter '{{}}' is read-only on element {{}}".format(param_name, eid_int))
        continue
    storage = param.StorageType.ToString()
    if storage == "String":
        param.Set(param_val)
    elif storage == "Double":
        param.Set(float(param_val))
    elif storage == "Integer":
        param.Set(int(param_val))
    else:
        param.Set(param_val)
    updated += 1
    print("Updated element {{}}".format(eid_int))
print("\\nSuccessfully updated {{}} element(s)".format(updated))
""",
            output_description="Confirmation for each updated element.",
        )
    )

    # ── Delete elements ─────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.delete_elements",
            name="Delete Elements",
            category="modify",
            description="Delete one or more elements by their IDs.",
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs to delete",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId
from System.Collections.Generic import List

ids = [int(x.strip()) for x in "{element_ids}".split(",")]

id_list = List[ElementId]()
for eid_int in ids:
    elem = doc.GetElement(ElementId(eid_int))
    if elem is None:
        print("Element not found: {{}}".format(eid_int))
    else:
        id_list.Add(ElementId(eid_int))
        print("Queued for deletion: {{}} (ID: {{}})".format(getattr(elem, 'Name', 'N/A'), eid_int))
if id_list.Count > 0:
    deleted = doc.Delete(id_list)
    print("\\nDeleted {{}} element(s)".format(deleted.Count))
else:
    print("No valid elements to delete")
""",
            output_description="Confirmation of deleted elements.",
        )
    )

    # ── Move element ────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.move_element",
            name="Move Element",
            category="modify",
            description="Move one or more elements by a translation vector (in feet).",
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs to move",
                ),
                StemParameter("dx", "float", "Translation in X direction (feet)"),
                StemParameter("dy", "float", "Translation in Y direction (feet)"),
                StemParameter(
                    "dz",
                    "float",
                    "Translation in Z direction (feet)",
                    required=False,
                    default=0.0,
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId, XYZ, ElementTransformUtils
from System.Collections.Generic import List

ids = [int(x.strip()) for x in "{element_ids}".split(",")]
translation = XYZ({dx}, {dy}, {dz})

id_list = List[ElementId]()
for eid_int in ids:
    elem = doc.GetElement(ElementId(eid_int))
    if elem:
        id_list.Add(ElementId(eid_int))
    else:
        print("Element not found: {{}}".format(eid_int))
if id_list.Count > 0:
    ElementTransformUtils.MoveElements(doc, id_list, translation)
    print("Moved {{}} element(s) by ({dx}, {dy}, {dz})".format(id_list.Count))
else:
    print("No valid elements to move")
""",
            output_description="Confirmation of moved elements.",
        )
    )

    # ── Copy element ────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.copy_element",
            name="Copy Element",
            category="modify",
            description="Copy one or more elements by a translation vector (in feet).",
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs to copy",
                ),
                StemParameter("dx", "float", "Offset in X direction (feet)"),
                StemParameter("dy", "float", "Offset in Y direction (feet)"),
                StemParameter(
                    "dz",
                    "float",
                    "Offset in Z direction (feet)",
                    required=False,
                    default=0.0,
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId, XYZ, ElementTransformUtils
from System.Collections.Generic import List

ids = [int(x.strip()) for x in "{element_ids}".split(",")]
translation = XYZ({dx}, {dy}, {dz})

id_list = List[ElementId]()
for eid_int in ids:
    elem = doc.GetElement(ElementId(eid_int))
    if elem:
        id_list.Add(ElementId(eid_int))
    else:
        print("Element not found: {{}}".format(eid_int))
if id_list.Count > 0:
    new_ids = ElementTransformUtils.CopyElements(doc, id_list, translation)
    print("Copied {{}} element(s). New IDs: {{}}".format(
        len(new_ids), [eid.IntegerValue for eid in new_ids]))
else:
    print("No valid elements to copy")
""",
            output_description="New element IDs created by the copy.",
        )
    )

    # ── Rotate element ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.rotate_element",
            name="Rotate Element",
            category="modify",
            description="Rotate elements around a vertical axis at their location (angle in degrees).",
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs to rotate",
                ),
                StemParameter(
                    "angle_degrees",
                    "float",
                    "Rotation angle in degrees (counter-clockwise)",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId, XYZ, Line, ElementTransformUtils
import math

ids = [int(x.strip()) for x in "{element_ids}".split(",")]
angle_rad = math.radians({angle_degrees})

rotated = 0
for eid_int in ids:
    elem = doc.GetElement(ElementId(eid_int))
    if elem is None:
        print("Element not found: {{}}".format(eid_int))
        continue
    loc = elem.Location
    if loc is None:
        print("No location for element {{}}".format(eid_int))
        continue
    if hasattr(loc, 'Point'):
        center = loc.Point
    elif hasattr(loc, 'Curve'):
        center = loc.Curve.Evaluate(0.5, True)
    else:
        print("Cannot determine center of element {{}}".format(eid_int))
        continue
    axis = Line.CreateBound(center, center + XYZ(0, 0, 1))
    ElementTransformUtils.RotateElement(doc, ElementId(eid_int), axis, angle_rad)
    rotated += 1
    print("Rotated element {{}} by {angle_degrees} degrees".format(eid_int))
print("\\nRotated {{}} element(s)".format(rotated))
""",
            output_description="Confirmation of rotation per element.",
        )
    )

    # ── Create wall ─────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.create_wall",
            name="Create Wall",
            category="modify",
            description="Create a straight wall between two points on a specified level.",
            parameters=[
                StemParameter("start_x", "float", "Start point X coordinate (feet)"),
                StemParameter("start_y", "float", "Start point Y coordinate (feet)"),
                StemParameter("end_x", "float", "End point X coordinate (feet)"),
                StemParameter("end_y", "float", "End point Y coordinate (feet)"),
                StemParameter(
                    "level_name", "str", "Name of the level to place the wall on"
                ),
                StemParameter(
                    "height",
                    "float",
                    "Wall height in feet",
                    required=False,
                    default=10.0,
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    XYZ, Line, Wall, FilteredElementCollector, Level, BuiltInParameter
)

start = XYZ({start_x}, {start_y}, 0)
end = XYZ({end_x}, {end_y}, 0)
line = Line.CreateBound(start, end)

# Find level
levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
level = None
for lev in levels:
    if getattr(lev, 'Name', '') == "{level_name}":
        level = lev
        break

if level is None:
    print("Level '{level_name}' not found. Available levels:")
    for lev in levels:
        print("  " + getattr(lev, 'Name', ''))
else:
    wall = Wall.Create(doc, line, level.Id, False)
    height_param = wall.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM)
    if height_param:
        height_param.Set({height})
    print("Wall created: ID {{}}".format(wall.Id.IntegerValue))
    print("Length: {{}} ft".format(line.Length))
    print("Level: {level_name}")
    print("Height: {height} ft")
""",
            output_description="New wall ID, length, level, and height.",
        )
    )

    # ── Create floor ────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.create_floor",
            name="Create Rectangular Floor",
            category="modify",
            description="Create a rectangular floor on a specified level.",
            parameters=[
                StemParameter("min_x", "float", "Minimum X coordinate (feet)"),
                StemParameter("min_y", "float", "Minimum Y coordinate (feet)"),
                StemParameter("max_x", "float", "Maximum X coordinate (feet)"),
                StemParameter("max_y", "float", "Maximum Y coordinate (feet)"),
                StemParameter("level_name", "str", "Name of the level for the floor"),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    XYZ, Line, CurveLoop, FilteredElementCollector,
    Level, FloorType, Floor
)
from System.Collections.Generic import List

# Build rectangular profile
p1 = XYZ({min_x}, {min_y}, 0)
p2 = XYZ({max_x}, {min_y}, 0)
p3 = XYZ({max_x}, {max_y}, 0)
p4 = XYZ({min_x}, {max_y}, 0)

loop = CurveLoop()
loop.Append(Line.CreateBound(p1, p2))
loop.Append(Line.CreateBound(p2, p3))
loop.Append(Line.CreateBound(p3, p4))
loop.Append(Line.CreateBound(p4, p1))

loops = List[CurveLoop]()
loops.Add(loop)

# Find level
levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
level = None
for lev in levels:
    if getattr(lev, 'Name', '') == "{level_name}":
        level = lev
        break

if level is None:
    print("Level '{level_name}' not found. Available levels:")
    for lev in levels:
        print("  " + getattr(lev, 'Name', ''))
else:
    # Get default floor type
    floor_types = FilteredElementCollector(doc).OfClass(FloorType).ToElements()
    floor_type = floor_types[0] if floor_types else None

    if floor_type is None:
        print("No floor types available")
    else:
        floor = Floor.Create(doc, loops, floor_type.Id, level.Id)
        print("Floor created: ID {{}}".format(floor.Id.IntegerValue))
        print("Level: {level_name}")
        width = abs({max_x} - {min_x})
        depth = abs({max_y} - {min_y})
        print("Size: {{}} x {{}} ft".format(width, depth))
""",
            output_description="New floor ID, level, and dimensions.",
        )
    )

    # ── Rename view ─────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.rename_view",
            name="Rename View",
            category="modify",
            description="Rename a view in the model.",
            parameters=[
                StemParameter("current_name", "str", "Current view name"),
                StemParameter("new_name", "str", "New view name"),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View

views = FilteredElementCollector(doc).OfClass(View).ToElements()
target = None
for v in views:
    if getattr(v, 'Name', '') == "{current_name}":
        target = v
        break

if target is None:
    print("View '{current_name}' not found. Available views:")
    for v in views:
        if not v.IsTemplate:
            print("  " + getattr(v, 'Name', ''))
else:
    target.Name = "{new_name}"
    print("View renamed: '{current_name}' -> '{new_name}'")
""",
            output_description="Confirmation of rename.",
        )
    )
