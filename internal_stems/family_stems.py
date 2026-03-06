# -*- coding: utf-8 -*-
"""
Family stems — family management, loading, and instance placement.

Based on patterns from duHast.Revit.Family.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_family_stems(registry: StemRegistry) -> None:
    """Register all family-related stems."""

    # ── Loaded families ─────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.loaded_families",
            name="Get Loaded Families",
            category="query",
            description=(
                "List all loaded (non-in-place) families in the model with "
                "category, type count, and whether they are editable."
            ),
            parameters=[
                StemParameter(
                    "category_filter",
                    "str",
                    "Optional category name to filter (e.g. 'Doors', 'Furniture'). "
                    "Leave empty for all families.",
                    required=False,
                    default="",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, Family

families = (FilteredElementCollector(doc)
    .OfClass(Family)
    .ToElements())

cat_filter = "{category_filter}".lower()
count = 0

for fam in sorted(families, key=lambda f: f.Name):
    if fam.IsInPlace:
        continue

    cat_name = ""
    try:
        if fam.FamilyCategory:
            cat_name = fam.FamilyCategory.Name
    except:
        pass

    if cat_filter and cat_filter not in cat_name.lower():
        continue

    type_count = 0
    try:
        type_ids = fam.GetFamilySymbolIds()
        type_count = type_ids.Count if type_ids else 0
    except:
        pass

    editable = ""
    try:
        editable = " | Editable: {{}}".format(fam.IsEditable)
    except:
        pass

    print("ID: {{}} | Name: {{}} | Category: {{}} | Types: {{}}{{}}".format(
        fam.Id.IntegerValue, fam.Name, cat_name, type_count, editable))
    count += 1

print("\\nTotal: {{}} loaded family(ies)".format(count))
""",
            output_description="List of loaded families with category and type count.",
        )
    )

    # ── In-place families ───────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.in_place_families",
            name="Get In-Place Families",
            category="query",
            description=(
                "List all in-place families in the model with their "
                "category and instance count."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, Family

families = (FilteredElementCollector(doc)
    .OfClass(Family)
    .ToElements())

count = 0
for fam in sorted(families, key=lambda f: f.Name):
    if not fam.IsInPlace:
        continue

    cat_name = ""
    try:
        if fam.FamilyCategory:
            cat_name = fam.FamilyCategory.Name
    except:
        pass

    instance_count = 0
    try:
        type_ids = fam.GetFamilySymbolIds()
        for tid in type_ids:
            sym = doc.GetElement(tid)
            if sym:
                deps = sym.GetDependentElements(
                    DB.ElementClassFilter(DB.FamilyInstance))
                instance_count += deps.Count
    except:
        pass

    print("ID: {{}} | Name: {{}} | Category: {{}} | Instances: {{}}".format(
        fam.Id.IntegerValue, fam.Name, cat_name, instance_count))
    count += 1

print("\\nTotal: {{}} in-place family(ies)".format(count))
""",
            output_description="List of in-place families with instance counts.",
        )
    )

    # ── Family types for a family ───────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.family_types",
            name="Get Types of a Family",
            category="query",
            description=(
                "List all types (symbols) of a specific family by name. "
                "Shows type name, instance count, and type ID."
            ),
            parameters=[
                StemParameter(
                    "family_name",
                    "str",
                    "Name of the family to list types for",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, Family, FamilyInstance, ElementClassFilter

families = FilteredElementCollector(doc).OfClass(Family).ToElements()
target = None
for fam in families:
    if fam.Name == "{family_name}":
        target = fam
        break

if target is None:
    print("Family '{family_name}' not found. Searching similar...")
    search = "{family_name}".lower()
    matches = [f for f in families if search in f.Name.lower()]
    if matches:
        for m in matches[:10]:
            print("  {{}}".format(m.Name))
    else:
        print("No matches found.")
else:
    type_ids = target.GetFamilySymbolIds()
    cat_name = target.FamilyCategory.Name if target.FamilyCategory else "?"
    print("Family: {{}} | Category: {{}} | In-Place: {{}}".format(
        target.Name, cat_name, target.IsInPlace))
    print("")

    inst_filter = ElementClassFilter(FamilyInstance)
    for tid in type_ids:
        sym = doc.GetElement(tid)
        if sym is None:
            continue
        instance_count = sym.GetDependentElements(inst_filter).Count
        print("  Type ID: {{}} | Name: {{}} | Instances: {{}}".format(
            tid.IntegerValue, sym.Name, instance_count))

    print("\\nTotal: {{}} type(s)".format(type_ids.Count))
""",
            output_description="List of types for a family with instance counts.",
        )
    )

    # ── Family instances by category ────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.family_instances_by_category",
            name="Get Family Instances by Category",
            category="query",
            description=(
                "List family instances filtered by a built-in category. "
                "Returns instance ID, family name, type name, and level."
            ),
            parameters=[
                StemParameter(
                    "category_name",
                    "str",
                    "Category name (e.g. 'Furniture', 'Mechanical Equipment', "
                    "'Plumbing Fixtures', 'Electrical Equipment')",
                ),
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of instances to return",
                    required=False,
                    default=100,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, FamilyInstance,
    ElementCategoryFilter, BuiltInParameter
)

category_map = {{
    "Furniture": BuiltInCategory.OST_Furniture,
    "Mechanical Equipment": BuiltInCategory.OST_MechanicalEquipment,
    "Plumbing Fixtures": BuiltInCategory.OST_PlumbingFixtures,
    "Electrical Equipment": BuiltInCategory.OST_ElectricalEquipment,
    "Electrical Fixtures": BuiltInCategory.OST_ElectricalFixtures,
    "Generic Models": BuiltInCategory.OST_GenericModel,
    "Specialty Equipment": BuiltInCategory.OST_SpecialityEquipment,
    "Casework": BuiltInCategory.OST_Casework,
    "Columns": BuiltInCategory.OST_Columns,
    "Structural Columns": BuiltInCategory.OST_StructuralColumns,
    "Structural Framing": BuiltInCategory.OST_StructuralFraming,
    "Lighting Fixtures": BuiltInCategory.OST_LightingFixtures,
    "Sprinklers": BuiltInCategory.OST_Sprinklers,
    "Communication Devices": BuiltInCategory.OST_CommunicationDevices,
    "Data Devices": BuiltInCategory.OST_DataDevices,
    "Fire Alarm Devices": BuiltInCategory.OST_FireAlarmDevices,
    "Nurse Call Devices": BuiltInCategory.OST_NurseCallDevices,
    "Security Devices": BuiltInCategory.OST_SecurityDevices,
    "Telephone Devices": BuiltInCategory.OST_TelephoneDevices,
    "Parking": BuiltInCategory.OST_Parking,
    "Entourage": BuiltInCategory.OST_Entourage,
    "Planting": BuiltInCategory.OST_Planting,
    "Site": BuiltInCategory.OST_Site,
}}

cat_name = "{category_name}"
bic = category_map.get(cat_name)
if bic is None:
    print("Unknown category: {{}}".format(cat_name))
    print("Available: {{}}".format(", ".join(sorted(category_map.keys()))))
else:
    instances = (FilteredElementCollector(doc)
        .OfClass(FamilyInstance)
        .WherePasses(ElementCategoryFilter(bic))
        .ToElements())

    limit = {limit}
    count = 0
    for inst in instances:
        if count >= limit:
            break

        sym = doc.GetElement(inst.GetTypeId())
        type_name = sym.Name if sym else "?"
        fam_name = ""
        try:
            fam_name = sym.Family.Name if sym and sym.Family else "?"
        except:
            pass

        level_str = ""
        try:
            lp = inst.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
            if lp:
                level_str = " | Level: {{}}".format(lp.AsValueString())
        except:
            pass

        loc_str = ""
        try:
            loc = inst.Location
            if loc and hasattr(loc, 'Point'):
                pt = loc.Point
                loc_str = " | Location: ({{}}, {{}}, {{}})".format(
                    round(pt.X, 2), round(pt.Y, 2), round(pt.Z, 2))
        except:
            pass

        print("ID: {{}} | Family: {{}} | Type: {{}}{{}}{{}}".format(
            inst.Id.IntegerValue, fam_name, type_name, level_str, loc_str))
        count += 1

    print("\\nTotal: {{}} instance(s) shown".format(count))
""",
            output_description="Family instances with family/type names, level, and location.",
        )
    )

    # ── Place family instance ───────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.place_family_instance",
            name="Place Family Instance",
            category="modify",
            description=(
                "Place a family instance at a specified XYZ point on a level. "
                "The family type must already be loaded in the project."
            ),
            parameters=[
                StemParameter(
                    "family_name",
                    "str",
                    "Name of the family",
                ),
                StemParameter(
                    "type_name",
                    "str",
                    "Name of the family type to place",
                ),
                StemParameter(
                    "level_name",
                    "str",
                    "Name of the level to place on",
                ),
                StemParameter(
                    "x",
                    "float",
                    "X coordinate (feet)",
                ),
                StemParameter(
                    "y",
                    "float",
                    "Y coordinate (feet)",
                ),
                StemParameter(
                    "z",
                    "float",
                    "Z coordinate (feet)",
                    required=False,
                    default=0.0,
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilySymbol, Level, XYZ, Structure
)

# Find family symbol
symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
target_sym = None
for s in symbols:
    try:
        if s.Family.Name == "{family_name}" and s.Name == "{type_name}":
            target_sym = s
            break
    except:
        continue

if target_sym is None:
    print("Family type '{family_name} : {type_name}' not found.")
    print("Searching for family '{family_name}'...")
    matches = [s for s in symbols
               if hasattr(s, 'Family') and s.Family and s.Family.Name == "{family_name}"]
    if matches:
        print("Available types:")
        for m in matches:
            print("  {{}}".format(m.Name))
    else:
        print("Family '{family_name}' is not loaded in the project.")
else:
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
        if not target_sym.IsActive:
            target_sym.Activate()
            doc.Regenerate()

        point = XYZ({x}, {y}, {z})
        instance = doc.Create.NewFamilyInstance(
            point, target_sym, level,
            Structure.StructuralType.NonStructural)

        print("Placed instance ID: {{}}".format(instance.Id.IntegerValue))
        print("Family: {family_name}")
        print("Type: {type_name}")
        print("Level: {level_name}")
        print("Location: ({x}, {y}, {z})")
""",
            output_description="Confirmation with new instance element ID.",
        )
    )

    # ── List family categories ──────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.family_categories",
            name="List Family Categories",
            category="query",
            description=(
                "List all categories that contain loaded family types, along "
                "with the count of family symbols in each category."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol

symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
cats = {{}}
for sym in symbols:
    try:
        cat_name = sym.Category.Name if sym.Category else "Unknown"
        cats[cat_name] = cats.get(cat_name, 0) + 1
    except:
        continue

for name in sorted(cats.keys()):
    print("{{}}: {{}} type(s)".format(name, cats[name]))
print("\\nTotal categories: {{}}".format(len(cats)))
""",
            output_description="Category names with family type counts, sorted alphabetically.",
        )
    )

    # ── List family types (flat list with optional filter) ──────────
    registry.register(
        Stem(
            stem_id="query.list_family_types",
            name="List Family Types (Flat)",
            category="query",
            description=(
                "Return a flat list of family name + type name pairs. "
                "Optionally filter by a case-insensitive substring match on "
                "the family or type name."
            ),
            parameters=[
                StemParameter(
                    "contains",
                    "str",
                    "Substring filter (case-insensitive) on family or type name. "
                    "Leave empty to list all.",
                    required=False,
                    default="",
                ),
                StemParameter(
                    "limit",
                    "int",
                    "Maximum number of results to return",
                    required=False,
                    default=50,
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol

symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
needle = "{contains}".lower()
limit = {limit}
count = 0

for sym in symbols:
    if count >= limit:
        break
    try:
        fam_name = sym.Family.Name
        type_name = sym.Name
        cat_name = sym.Category.Name if sym.Category else "Unknown"
        is_active = sym.IsActive

        if needle:
            if needle not in fam_name.lower() and needle not in type_name.lower():
                continue

        active_str = "Active" if is_active else "Inactive"
        print("Family: {{}} | Type: {{}} | Category: {{}} | {{}}".format(
            fam_name, type_name, cat_name, active_str))
        count += 1
    except:
        continue

print("\\nShowing {{}} result(s)".format(count))
if needle:
    print("Filter: '{{}}'".format(needle))
""",
            output_description="Flat list of family/type pairs with category and activation status.",
        )
    )
