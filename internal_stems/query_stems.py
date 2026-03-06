# -*- coding: utf-8 -*-
"""
Query stems — read-only operations for inspecting the Revit model.

These stems never modify the model and do not require transactions.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_query_stems(registry: StemRegistry) -> None:
    """Register all query stems."""

    # ── Elements by category ────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.elements_by_category",
            name="Get Elements by Category",
            category="query",
            description=(
                "Collect all element instances in a given Revit category. "
                "Returns element ID, name, type name, and level for each element."
            ),
            parameters=[
                StemParameter(
                    "category_name",
                    "str",
                    "Revit category name (e.g. 'Walls', 'Doors', 'Windows', 'Floors')",
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
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector
import clr

category_map = {{
    "Walls": BuiltInCategory.OST_Walls,
    "Doors": BuiltInCategory.OST_Doors,
    "Windows": BuiltInCategory.OST_Windows,
    "Floors": BuiltInCategory.OST_Floors,
    "Ceilings": BuiltInCategory.OST_Ceilings,
    "Roofs": BuiltInCategory.OST_Roofs,
    "Columns": BuiltInCategory.OST_Columns,
    "Structural Columns": BuiltInCategory.OST_StructuralColumns,
    "Structural Framing": BuiltInCategory.OST_StructuralFraming,
    "Rooms": BuiltInCategory.OST_Rooms,
    "Furniture": BuiltInCategory.OST_Furniture,
    "Mechanical Equipment": BuiltInCategory.OST_MechanicalEquipment,
    "Plumbing Fixtures": BuiltInCategory.OST_PlumbingFixtures,
    "Electrical Equipment": BuiltInCategory.OST_ElectricalEquipment,
    "Electrical Fixtures": BuiltInCategory.OST_ElectricalFixtures,
    "Pipes": BuiltInCategory.OST_PipeCurves,
    "Ducts": BuiltInCategory.OST_DuctCurves,
    "Stairs": BuiltInCategory.OST_Stairs,
    "Railings": BuiltInCategory.OST_StairsRailing,
    "Generic Models": BuiltInCategory.OST_GenericModel,
    "Parking": BuiltInCategory.OST_Parking,
    "Site": BuiltInCategory.OST_Site,
    "Topography": BuiltInCategory.OST_Topography,
    "Curtain Panels": BuiltInCategory.OST_CurtainWallPanels,
    "Curtain Wall Mullions": BuiltInCategory.OST_CurtainWallMullions,
}}

cat_name = "{category_name}"
bic = category_map.get(cat_name)
if bic is None:
    print("Unknown category: " + cat_name)
    print("Available: " + ", ".join(sorted(category_map.keys())))
else:
    elems = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
    limit = {limit}
    count = 0
    for e in elems:
        if count >= limit:
            break
        ename = getattr(e, 'Name', 'N/A')
        eid = e.Id.IntegerValue
        etype = ''
        try:
            t = doc.GetElement(e.GetTypeId())
            if t:
                etype = getattr(t, 'Name', '')
        except:
            pass
        level_name = ''
        try:
            if hasattr(e, 'LevelId') and e.LevelId and e.LevelId.IntegerValue != -1:
                lev = doc.GetElement(e.LevelId)
                if lev:
                    level_name = getattr(lev, 'Name', '')
        except:
            pass
        print("ID: {{}} | Name: {{}} | Type: {{}} | Level: {{}}".format(eid, ename, etype, level_name))
        count += 1
    print("\\nTotal found: {{}} (showing {{}})".format(len(list(elems)), min(limit, len(list(elems)))))
""",
            output_description="One line per element with ID, name, type, and level. Summary count at end.",
        )
    )

    # ── Count elements by category ──────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.count_by_category",
            name="Count Elements by Category",
            category="query",
            description="Count the number of element instances in one or more categories.",
            parameters=[
                StemParameter(
                    "category_names",
                    "list",
                    "Comma-separated category names (e.g. 'Walls,Doors,Windows')",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

category_map = {{
    "Walls": BuiltInCategory.OST_Walls,
    "Doors": BuiltInCategory.OST_Doors,
    "Windows": BuiltInCategory.OST_Windows,
    "Floors": BuiltInCategory.OST_Floors,
    "Ceilings": BuiltInCategory.OST_Ceilings,
    "Roofs": BuiltInCategory.OST_Roofs,
    "Columns": BuiltInCategory.OST_Columns,
    "Rooms": BuiltInCategory.OST_Rooms,
    "Furniture": BuiltInCategory.OST_Furniture,
    "Stairs": BuiltInCategory.OST_Stairs,
    "Generic Models": BuiltInCategory.OST_GenericModel,
    "Structural Columns": BuiltInCategory.OST_StructuralColumns,
    "Structural Framing": BuiltInCategory.OST_StructuralFraming,
    "Mechanical Equipment": BuiltInCategory.OST_MechanicalEquipment,
    "Plumbing Fixtures": BuiltInCategory.OST_PlumbingFixtures,
    "Electrical Equipment": BuiltInCategory.OST_ElectricalEquipment,
    "Pipes": BuiltInCategory.OST_PipeCurves,
    "Ducts": BuiltInCategory.OST_DuctCurves,
}}

names = "{category_names}".split(",")
for name in names:
    name = name.strip()
    bic = category_map.get(name)
    if bic is None:
        print("Unknown category: " + name)
    else:
        elems = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
        print("{{}}: {{}}".format(name, len(list(elems))))
""",
            output_description="One line per category with the count.",
        )
    )

    # ── Element properties ──────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.element_properties",
            name="Get Element Properties",
            category="query",
            description=(
                "Retrieve all parameter values for a specific element by its ID."
            ),
            parameters=[
                StemParameter(
                    "element_id",
                    "int",
                    "The integer element ID",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import ElementId

eid = ElementId({element_id})
elem = doc.GetElement(eid)
if elem is None:
    print("Element not found: {element_id}")
else:
    print("Element: {{}} (ID: {element_id})".format(getattr(elem, 'Name', 'N/A')))
    print("Category: {{}}".format(elem.Category.Name if elem.Category else 'N/A'))

    type_elem = doc.GetElement(elem.GetTypeId())
    if type_elem:
        print("Type: {{}}".format(getattr(type_elem, 'Name', 'N/A')))

    print("\\n--- Instance Parameters ---")
    for p in elem.Parameters:
        try:
            pname = p.Definition.Name
            if p.HasValue:
                if p.StorageType.ToString() == "String":
                    val = p.AsString()
                elif p.StorageType.ToString() == "Double":
                    val = p.AsDouble()
                elif p.StorageType.ToString() == "Integer":
                    val = p.AsInteger()
                elif p.StorageType.ToString() == "ElementId":
                    val = p.AsElementId().IntegerValue
                else:
                    val = p.AsValueString()
                print("  {{}} = {{}}".format(pname, val))
        except:
            pass

    if type_elem:
        print("\\n--- Type Parameters ---")
        for p in type_elem.Parameters:
            try:
                pname = p.Definition.Name
                if p.HasValue:
                    if p.StorageType.ToString() == "String":
                        val = p.AsString()
                    elif p.StorageType.ToString() == "Double":
                        val = p.AsDouble()
                    elif p.StorageType.ToString() == "Integer":
                        val = p.AsInteger()
                    elif p.StorageType.ToString() == "ElementId":
                        val = p.AsElementId().IntegerValue
                    else:
                        val = p.AsValueString()
                    print("  {{}} = {{}}".format(pname, val))
            except:
                pass
""",
            output_description="All instance and type parameters with their values.",
        )
    )

    # ── Elements by parameter value ─────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.elements_by_parameter",
            name="Filter Elements by Parameter Value",
            category="query",
            description=(
                "Find elements in a category where a specific parameter matches a value."
            ),
            parameters=[
                StemParameter(
                    "category_name",
                    "str",
                    "Revit category name (e.g. 'Walls', 'Doors')",
                ),
                StemParameter(
                    "parameter_name",
                    "str",
                    "Parameter name to filter on",
                ),
                StemParameter(
                    "parameter_value",
                    "str",
                    "Value to match (string comparison)",
                ),
                StemParameter(
                    "limit",
                    "int",
                    "Maximum results to return",
                    required=False,
                    default=50,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

category_map = {{
    "Walls": BuiltInCategory.OST_Walls,
    "Doors": BuiltInCategory.OST_Doors,
    "Windows": BuiltInCategory.OST_Windows,
    "Floors": BuiltInCategory.OST_Floors,
    "Rooms": BuiltInCategory.OST_Rooms,
    "Furniture": BuiltInCategory.OST_Furniture,
    "Columns": BuiltInCategory.OST_Columns,
    "Generic Models": BuiltInCategory.OST_GenericModel,
    "Ceilings": BuiltInCategory.OST_Ceilings,
    "Roofs": BuiltInCategory.OST_Roofs,
    "Stairs": BuiltInCategory.OST_Stairs,
    "Structural Columns": BuiltInCategory.OST_StructuralColumns,
    "Structural Framing": BuiltInCategory.OST_StructuralFraming,
    "Mechanical Equipment": BuiltInCategory.OST_MechanicalEquipment,
    "Plumbing Fixtures": BuiltInCategory.OST_PlumbingFixtures,
    "Pipes": BuiltInCategory.OST_PipeCurves,
    "Ducts": BuiltInCategory.OST_DuctCurves,
}}

cat_name = "{category_name}"
param_name = "{parameter_name}"
param_val = "{parameter_value}"
limit = {limit}

bic = category_map.get(cat_name)
if bic is None:
    print("Unknown category: " + cat_name)
else:
    elems = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
    matches = []
    for e in elems:
        for p in e.Parameters:
            try:
                if p.Definition.Name == param_name:
                    val = p.AsValueString() or p.AsString() or str(p.AsDouble())
                    if val and param_val.lower() in val.lower():
                        matches.append(e)
                    break
            except:
                pass
    count = 0
    for e in matches:
        if count >= limit:
            break
        print("ID: {{}} | Name: {{}}".format(e.Id.IntegerValue, getattr(e, 'Name', 'N/A')))
        count += 1
    print("\\nMatched: {{}} of {{}} total".format(len(matches), len(list(elems))))
""",
            output_description="Matching elements with IDs, plus match/total count.",
        )
    )

    # ── Element location ────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.element_location",
            name="Get Element Location",
            category="query",
            description="Get the XYZ location/geometry of an element by ID.",
            parameters=[
                StemParameter("element_id", "int", "The integer element ID"),
            ],
            code_template="""\
from Autodesk.Revit.DB import ElementId

eid = ElementId({element_id})
elem = doc.GetElement(eid)
if elem is None:
    print("Element not found: {element_id}")
else:
    print("Element: {{}} (ID: {element_id})".format(getattr(elem, 'Name', 'N/A')))
    loc = elem.Location
    if loc is None:
        print("No location data available")
    elif hasattr(loc, 'Point'):
        pt = loc.Point
        print("Location Point: X={{}}, Y={{}}, Z={{}}".format(pt.X, pt.Y, pt.Z))
        if hasattr(loc, 'Rotation'):
            print("Rotation: {{}}".format(loc.Rotation))
    elif hasattr(loc, 'Curve'):
        crv = loc.Curve
        sp = crv.GetEndPoint(0)
        ep = crv.GetEndPoint(1)
        print("Location Curve:")
        print("  Start: X={{}}, Y={{}}, Z={{}}".format(sp.X, sp.Y, sp.Z))
        print("  End:   X={{}}, Y={{}}, Z={{}}".format(ep.X, ep.Y, ep.Z))
        print("  Length: {{}}".format(crv.Length))
    else:
        print("Location type: {{}}".format(type(loc).__name__))

    bb = elem.get_BoundingBox(None)
    if bb:
        print("Bounding Box:")
        print("  Min: X={{}}, Y={{}}, Z={{}}".format(bb.Min.X, bb.Min.Y, bb.Min.Z))
        print("  Max: X={{}}, Y={{}}, Z={{}}".format(bb.Max.X, bb.Max.Y, bb.Max.Z))
""",
            output_description="Location point/curve coordinates and bounding box.",
        )
    )

    # ── List categories in model ────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.list_categories",
            name="List Model Categories",
            category="query",
            description="List all categories that have elements in the current model.",
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector

cats = doc.Settings.Categories
results = []
for cat in cats:
    try:
        count = FilteredElementCollector(doc).OfCategoryId(cat.Id).WhereElementIsNotElementType().GetElementCount()
        if count > 0:
            results.append((cat.Name, count))
    except:
        pass

results.sort(key=lambda x: x[1], reverse=True)
for name, count in results:
    print("{{}}: {{}}".format(name, count))
print("\\nTotal categories with elements: {{}}".format(len(results)))
""",
            output_description="Category names with element counts, sorted by count.",
        )
    )

    # ── Get room data ───────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.room_data",
            name="Get Room Data",
            category="query",
            description="Get detailed information about all rooms including area, number, level, and department.",
            parameters=[
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of rooms to return",
                    required=False,
                    default=50,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector, BuiltInParameter

rooms = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements()
limit = {limit}
count = 0
for r in rooms:
    if count >= limit:
        break
    try:
        name = getattr(r, 'Name', 'N/A')
        number = r.get_Parameter(BuiltInParameter.ROOM_NUMBER)
        number_val = number.AsString() if number and number.HasValue else 'N/A'
        area = r.get_Parameter(BuiltInParameter.ROOM_AREA)
        area_val = area.AsValueString() if area and area.HasValue else 'N/A'
        level = r.get_Parameter(BuiltInParameter.ROOM_LEVEL_ID)
        level_val = ''
        if level and level.HasValue:
            lev_elem = doc.GetElement(level.AsElementId())
            if lev_elem:
                level_val = getattr(lev_elem, 'Name', '')
        dept = r.get_Parameter(BuiltInParameter.ROOM_DEPARTMENT)
        dept_val = dept.AsString() if dept and dept.HasValue else ''
        print("Room {{}} - {{}} | Area: {{}} | Level: {{}} | Dept: {{}}".format(
            number_val, name, area_val, level_val, dept_val))
        count += 1
    except:
        pass
print("\\nTotal rooms: {{}} (showing {{}})".format(len(list(rooms)), min(limit, len(list(rooms)))))
""",
            output_description="Room details: number, name, area, level, department.",
        )
    )

    # ── Get sheets ──────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.list_sheets",
            name="List Sheets",
            category="query",
            description="List all sheets in the model with their number, name, and placed views.",
            parameters=[
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of sheets",
                    required=False,
                    default=50,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, ViewSheet

sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
limit = {limit}
count = 0
for s in sorted(sheets, key=lambda x: getattr(x, 'SheetNumber', '')):
    if count >= limit:
        break
    try:
        num = getattr(s, 'SheetNumber', 'N/A')
        name = getattr(s, 'Name', 'N/A')
        views_on_sheet = s.GetAllPlacedViews()
        view_names = []
        for vid in views_on_sheet:
            v = doc.GetElement(vid)
            if v:
                view_names.append(getattr(v, 'Name', ''))
        print("{{}} - {{}} | Views: {{}}".format(num, name, ", ".join(view_names) if view_names else "None"))
        count += 1
    except:
        pass
print("\\nTotal sheets: {{}}".format(len(list(sheets))))
""",
            output_description="Sheet number, name, and placed view names.",
        )
    )

    # ── Warnings / errors ───────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.model_warnings",
            name="Get Model Warnings",
            category="query",
            description="Retrieve all warnings/errors currently in the Revit model.",
            parameters=[
                StemParameter(
                    "limit",
                    "int",
                    "Maximum warnings to return",
                    required=False,
                    default=50,
                ),
            ],
            code_template="""\
warnings = doc.GetWarnings()
limit = {limit}
count = 0
for w in warnings:
    if count >= limit:
        break
    desc = w.GetDescriptionText()
    elem_ids = [e.IntegerValue for e in w.GetFailingElements()]
    print("Warning: {{}} | Elements: {{}}".format(desc, elem_ids))
    count += 1
print("\\nTotal warnings: {{}} (showing {{}})".format(len(warnings), min(limit, len(warnings))))
""",
            output_description="Warning descriptions with affected element IDs.",
        )
    )

    # ── Comprehensive model info ────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.model_info",
            name="Get Comprehensive Model Info",
            category="query",
            description=(
                "Retrieve a comprehensive overview of the current Revit model: "
                "project info (name, number, client), element counts by 13 major "
                "categories, warnings summary, levels with elevations, rooms with "
                "area/level, views & sheets breakdown, and linked model status."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    View, ViewType, ViewSheet
)

# ── Project Information ──────────────────────────────────
print("=== PROJECT INFO ===")
try:
    pi = doc.ProjectInformation
    print("  Name: {{}}".format(pi.Name or "Not Set"))
    print("  Number: {{}}".format(pi.Number or "Not Set"))
    print("  Client: {{}}".format(pi.ClientName or "Not Set"))
except:
    pass
print("  File: {{}}".format(doc.Title or "Untitled"))

# ── Element Counts ───────────────────────────────────────
print("\\n=== ELEMENT COUNTS ===")
cat_map = [
    ("Walls", BuiltInCategory.OST_Walls),
    ("Floors", BuiltInCategory.OST_Floors),
    ("Ceilings", BuiltInCategory.OST_Ceilings),
    ("Roofs", BuiltInCategory.OST_Roofs),
    ("Doors", BuiltInCategory.OST_Doors),
    ("Windows", BuiltInCategory.OST_Windows),
    ("Stairs", BuiltInCategory.OST_Stairs),
    ("Railings", BuiltInCategory.OST_StairsRailing),
    ("Columns", BuiltInCategory.OST_Columns),
    ("Structural Framing", BuiltInCategory.OST_StructuralFraming),
    ("Furniture", BuiltInCategory.OST_Furniture),
    ("Lighting Fixtures", BuiltInCategory.OST_LightingFixtures),
    ("Plumbing Fixtures", BuiltInCategory.OST_PlumbingFixtures),
]
total = 0
for name, bic in cat_map:
    try:
        cnt = (FilteredElementCollector(doc)
            .OfCategory(bic)
            .WhereElementIsNotElementType()
            .GetElementCount())
        if cnt > 0:
            print("  {{}}: {{}}".format(name, cnt))
        total += cnt
    except:
        pass
print("  ---")
print("  Total: {{}}".format(total))

# ── Warnings ─────────────────────────────────────────────
print("\\n=== MODEL HEALTH ===")
try:
    warns = doc.GetWarnings()
    print("  Total warnings: {{}}".format(len(warns)))
except:
    print("  Warnings: N/A")

# ── Levels ───────────────────────────────────────────────
print("\\n=== LEVELS ===")
try:
    lvls = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Levels)
        .WhereElementIsNotElementType()
        .ToElements())
    lvl_list = []
    for lv in lvls:
        try:
            lvl_list.append((getattr(lv, 'Name', '?'), round(lv.Elevation, 2)))
        except:
            lvl_list.append((getattr(lv, 'Name', '?'), '?'))
    lvl_list.sort(key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0)
    for n, e in lvl_list:
        print("  {{}} (elev: {{}})".format(n, e))
    print("  Total: {{}}".format(len(lvl_list)))
except:
    print("  N/A")

# ── Rooms ────────────────────────────────────────────────
print("\\n=== ROOMS ===")
try:
    rooms = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Rooms)
        .WhereElementIsNotElementType()
        .ToElements())
    placed = 0
    unplaced = 0
    for rm in rooms:
        try:
            a = rm.Area
            if a > 0:
                placed += 1
            else:
                unplaced += 1
        except:
            unplaced += 1
    print("  Total: {{}} (placed: {{}}, unplaced: {{}})".format(
        len(list(rooms)), placed, unplaced))
except:
    print("  N/A")

# ── Views & Sheets ───────────────────────────────────────
print("\\n=== VIEWS & SHEETS ===")
try:
    all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
    valid = [v for v in all_views
             if hasattr(v, 'IsTemplate') and not v.IsTemplate
             and v.ViewType != ViewType.Internal
             and v.ViewType != ViewType.ProjectBrowser]
    fp = sum(1 for v in valid if v.ViewType == ViewType.FloorPlan)
    el = sum(1 for v in valid if v.ViewType == ViewType.Elevation)
    sc = sum(1 for v in valid if v.ViewType == ViewType.Section)
    td = sum(1 for v in valid if v.ViewType == ViewType.ThreeD)
    sh = sum(1 for v in valid if v.ViewType == ViewType.Schedule)
    print("  Total views: {{}}".format(len(valid)))
    print("    Floor Plans: {{}}".format(fp))
    print("    Elevations: {{}}".format(el))
    print("    Sections: {{}}".format(sc))
    print("    3D Views: {{}}".format(td))
    print("    Schedules: {{}}".format(sh))
except:
    print("  Views: N/A")
try:
    sheets = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Sheets)
        .WhereElementIsNotElementType()
        .GetElementCount())
    print("  Sheets: {{}}".format(sheets))
except:
    print("  Sheets: N/A")

# ── Linked Models ────────────────────────────────────────
print("\\n=== LINKED MODELS ===")
try:
    from Autodesk.Revit.DB import RevitLinkInstance
    links = (FilteredElementCollector(doc)
        .OfClass(RevitLinkInstance)
        .ToElements())
    if links:
        for lnk in links:
            try:
                lnk_name = getattr(lnk, 'Name', 'Unknown')
                lnk_doc = lnk.GetLinkDocument()
                loaded = "Loaded" if lnk_doc else "Not Loaded"
                pinned = "Pinned" if getattr(lnk, 'Pinned', False) else "Unpinned"
                print("  {{}} | {{}} | {{}}".format(lnk_name, loaded, pinned))
            except:
                pass
        print("  Total: {{}}".format(len(list(links))))
    else:
        print("  None")
except:
    print("  N/A")
""",
            output_description=(
                "Full model overview: project info, element counts, "
                "warnings, levels, rooms, views/sheets, linked models."
            ),
        )
    )
