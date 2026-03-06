# -*- coding: utf-8 -*-
"""
Parameter stems — advanced parameter reading and writing operations.

Based on patterns from duHast.Revit.Common.parameter_get_utils
and duHast.Revit.Common.parameter_set_utils.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_parameter_stems(registry: StemRegistry) -> None:
    """Register all parameter-related stems."""

    # ── Detailed element parameters ─────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.element_parameters_detailed",
            name="Get Element Parameters (Detailed)",
            category="query",
            description=(
                "Get all parameters on an element with full details: "
                "name, storage type, value, is read-only, is shared, "
                "group, and built-in parameter name if applicable. "
                "More detailed than query.element_properties."
            ),
            parameters=[
                StemParameter(
                    "element_id",
                    "int",
                    "Element ID to inspect",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import ElementId, StorageType

elem = doc.GetElement(ElementId({element_id}))
if elem is None:
    print("Element not found: {element_id}")
else:
    type_name = ""
    try:
        et = doc.GetElement(elem.GetTypeId())
        if et:
            type_name = et.Name
    except:
        pass

    cat_name = elem.Category.Name if elem.Category else "N/A"
    print("Element ID: {element_id}")
    print("Category: {{}}".format(cat_name))
    print("Type: {{}}".format(type_name))
    print("")

    params = elem.GetOrderedParameters()
    print("=== INSTANCE PARAMETERS ({{}}) ===".format(params.Count))
    for p in params:
        name = p.Definition.Name
        storage = p.StorageType.ToString()
        read_only = "RO" if p.IsReadOnly else "RW"

        # Get value based on storage type
        try:
            if p.StorageType == StorageType.String:
                val = p.AsString() or ""
            elif p.StorageType == StorageType.Integer:
                val = str(p.AsInteger())
            elif p.StorageType == StorageType.Double:
                val_str = p.AsValueString()
                val = val_str if val_str else str(round(p.AsDouble(), 6))
            elif p.StorageType == StorageType.ElementId:
                eid = p.AsElementId()
                ref_elem = doc.GetElement(eid) if eid.IntegerValue != -1 else None
                val = "{{}} ({{}})".format(
                    eid.IntegerValue,
                    ref_elem.Name if ref_elem and hasattr(ref_elem, 'Name') else "")
            else:
                val = "N/A"
        except:
            val = "<error>"

        shared = ""
        try:
            if p.IsShared:
                shared = " | SHARED"
        except:
            pass

        group_str = ""
        try:
            group_str = " | Group: {{}}".format(p.Definition.ParameterGroup.ToString())
        except:
            pass

        print("  [{{}}] {{}} ({{}}): {{}}{{}}{{}}".format(
            read_only, name, storage, val, shared, group_str))

    # Type parameters
    try:
        et = doc.GetElement(elem.GetTypeId())
        if et:
            type_params = et.GetOrderedParameters()
            print("\\n=== TYPE PARAMETERS ({{}}) ===".format(type_params.Count))
            for p in type_params:
                name = p.Definition.Name
                storage = p.StorageType.ToString()
                read_only = "RO" if p.IsReadOnly else "RW"
                try:
                    if p.StorageType == StorageType.String:
                        val = p.AsString() or ""
                    elif p.StorageType == StorageType.Integer:
                        val = str(p.AsInteger())
                    elif p.StorageType == StorageType.Double:
                        val_str = p.AsValueString()
                        val = val_str if val_str else str(round(p.AsDouble(), 6))
                    elif p.StorageType == StorageType.ElementId:
                        val = str(p.AsElementId().IntegerValue)
                    else:
                        val = "N/A"
                except:
                    val = "<error>"
                print("  [{{}}] {{}} ({{}}): {{}}".format(
                    read_only, name, storage, val))
    except:
        pass
""",
            output_description="Full parameter listing with type, value, and read-only status.",
        )
    )

    # ── Get parameter by name ───────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.parameter_value_by_name",
            name="Get Parameter Value by Name",
            category="query",
            description=(
                "Get the value of a specific named parameter from one or "
                "more elements. Useful for reading a single parameter "
                "across multiple elements."
            ),
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs",
                ),
                StemParameter(
                    "parameter_name",
                    "str",
                    "Name of the parameter to read",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import ElementId, StorageType

ids = [int(x.strip()) for x in "{element_ids}".split(",")]
param_name = "{parameter_name}"

for eid_int in ids:
    elem = doc.GetElement(ElementId(eid_int))
    if elem is None:
        print("Element {{}}: NOT FOUND".format(eid_int))
        continue

    param = elem.LookupParameter(param_name)
    if param is None:
        print("Element {{}}: Parameter '{{}}' not found".format(eid_int, param_name))
        continue

    try:
        if param.StorageType == StorageType.String:
            val = param.AsString() or ""
        elif param.StorageType == StorageType.Integer:
            val = str(param.AsInteger())
        elif param.StorageType == StorageType.Double:
            val_str = param.AsValueString()
            val = val_str if val_str else str(round(param.AsDouble(), 6))
        elif param.StorageType == StorageType.ElementId:
            val = str(param.AsElementId().IntegerValue)
        else:
            val = "N/A"
    except Exception as e:
        val = "<error: {{}}>".format(e)

    print("Element {{}}: {{}} = {{}} ({{}}|{{}})".format(
        eid_int, param_name, val,
        param.StorageType.ToString(),
        "RO" if param.IsReadOnly else "RW"))
""",
            output_description="Parameter value for each element.",
        )
    )

    # ── Get built-in parameter ──────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.builtin_parameter",
            name="Get Built-in Parameter Value",
            category="query",
            description=(
                "Get the value of a Revit built-in parameter from an element. "
                "Built-in parameters use the BuiltInParameter enum name "
                "(e.g. WALL_USER_HEIGHT_PARAM, ROOM_AREA, HOST_AREA_COMPUTED)."
            ),
            parameters=[
                StemParameter(
                    "element_id",
                    "int",
                    "Element ID",
                ),
                StemParameter(
                    "builtin_param_name",
                    "str",
                    "BuiltInParameter enum name (e.g. 'WALL_USER_HEIGHT_PARAM')",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import ElementId, BuiltInParameter, StorageType

elem = doc.GetElement(ElementId({element_id}))
if elem is None:
    print("Element not found: {element_id}")
else:
    bip_name = "{builtin_param_name}"
    try:
        bip = getattr(BuiltInParameter, bip_name)
    except AttributeError:
        print("Unknown BuiltInParameter: {{}}".format(bip_name))
        print("Common examples: WALL_USER_HEIGHT_PARAM, ROOM_AREA, HOST_AREA_COMPUTED,")
        print("  ELEM_PARTITION_PARAM, ALL_MODEL_MARK, CURVE_ELEM_LENGTH,")
        print("  DOOR_WIDTH, DOOR_HEIGHT, FAMILY_LEVEL_PARAM")
        bip = None

    if bip is not None:
        param = elem.get_Parameter(bip)
        if param is None:
            print("Parameter '{{}}' not available on element {element_id}".format(bip_name))
        else:
            try:
                if param.StorageType == StorageType.String:
                    val = param.AsString() or ""
                elif param.StorageType == StorageType.Integer:
                    val = str(param.AsInteger())
                elif param.StorageType == StorageType.Double:
                    val_str = param.AsValueString()
                    raw = round(param.AsDouble(), 6)
                    val = "{{}} (raw: {{}})".format(val_str, raw) if val_str else str(raw)
                elif param.StorageType == StorageType.ElementId:
                    eid = param.AsElementId()
                    ref = doc.GetElement(eid) if eid.IntegerValue != -1 else None
                    val = "{{}} ({{}})".format(
                        eid.IntegerValue,
                        ref.Name if ref and hasattr(ref, 'Name') else "")
                else:
                    val = "N/A"
            except Exception as e:
                val = "<error: {{}}>".format(e)

            print("Element {element_id} | {{}} = {{}} | Type: {{}} | {{}}".format(
                bip_name, val,
                param.StorageType.ToString(),
                "Read-Only" if param.IsReadOnly else "Read-Write"))
""",
            output_description="Built-in parameter value with type info.",
        )
    )

    # ── Set built-in parameter ──────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.set_builtin_parameter",
            name="Set Built-in Parameter",
            category="modify",
            description=(
                "Set the value of a Revit built-in parameter on one or more "
                "elements. Uses the BuiltInParameter enum name."
            ),
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs",
                ),
                StemParameter(
                    "builtin_param_name",
                    "str",
                    "BuiltInParameter enum name (e.g. 'ALL_MODEL_MARK')",
                ),
                StemParameter(
                    "value",
                    "str",
                    "Value to set (auto-converted to the correct type)",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId, BuiltInParameter, StorageType

ids = [int(x.strip()) for x in "{element_ids}".split(",")]
bip_name = "{builtin_param_name}"
value_str = "{value}"

try:
    bip = getattr(BuiltInParameter, bip_name)
except AttributeError:
    print("Unknown BuiltInParameter: {{}}".format(bip_name))
    bip = None

if bip is not None:
    updated = 0
    for eid_int in ids:
        elem = doc.GetElement(ElementId(eid_int))
        if elem is None:
            print("Element not found: {{}}".format(eid_int))
            continue

        param = elem.get_Parameter(bip)
        if param is None:
            print("Parameter '{{}}' not found on element {{}}".format(bip_name, eid_int))
            continue

        if param.IsReadOnly:
            print("Parameter '{{}}' is read-only on element {{}}".format(bip_name, eid_int))
            continue

        try:
            if param.StorageType == StorageType.String:
                param.Set(value_str)
            elif param.StorageType == StorageType.Integer:
                param.Set(int(value_str))
            elif param.StorageType == StorageType.Double:
                try:
                    param.SetValueString(value_str)
                except:
                    param.Set(float(value_str))
            elif param.StorageType == StorageType.ElementId:
                param.Set(ElementId(int(value_str)))
            updated += 1
            print("Updated element {{}} | {{}} = {{}}".format(eid_int, bip_name, value_str))
        except Exception as e:
            print("Failed on element {{}}: {{}}".format(eid_int, e))

    print("\\nUpdated {{}} element(s)".format(updated))
""",
            output_description="Confirmation for each updated element.",
        )
    )

    # ── List category parameters ────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.category_parameters",
            name="List Category Parameters",
            category="query",
            description=(
                "List all available parameters on elements in a given "
                "category.  Shows parameter name, storage type, whether it "
                "has a value, and a sample value from the first element."
            ),
            parameters=[
                StemParameter(
                    "category_name",
                    "str",
                    "Revit category name (e.g. 'Walls', 'Doors', 'Rooms')",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import StorageType

cat_name = "{category_name}"

# Find category
categories = doc.Settings.Categories
target_cat = None
for c in categories:
    if c.Name == cat_name:
        target_cat = c
        break

if target_cat is None:
    print("Category '{{}}' not found".format(cat_name))
else:
    elems = (DB.FilteredElementCollector(doc)
        .OfCategoryId(target_cat.Id)
        .WhereElementIsNotElementType()
        .ToElements())

    if not elems:
        print("No elements in category '{{}}'".format(cat_name))
    else:
        sample = elems[0]
        params = []
        for p in sample.Parameters:
            try:
                pname = p.Definition.Name
                stype = p.StorageType.ToString()
                has_val = p.HasValue

                sample_val = "N/A"
                if has_val:
                    try:
                        if p.StorageType == StorageType.String:
                            sample_val = p.AsString() or ""
                        elif p.StorageType == StorageType.Integer:
                            sample_val = str(p.AsInteger())
                        elif p.StorageType == StorageType.Double:
                            vs = p.AsValueString()
                            sample_val = vs if vs else str(round(p.AsDouble(), 4))
                        elif p.StorageType == StorageType.ElementId:
                            eid = p.AsElementId()
                            if eid.IntegerValue != -1:
                                ref = doc.GetElement(eid)
                                if ref and hasattr(ref, 'Name'):
                                    sample_val = ref.Name
                                else:
                                    sample_val = str(eid.IntegerValue)
                            else:
                                sample_val = ""
                        else:
                            vs = p.AsValueString()
                            sample_val = vs if vs else ""
                    except:
                        sample_val = "<error>"

                params.append((pname, stype, has_val, sample_val))
            except:
                continue

        params.sort(key=lambda x: x[0])
        print("Parameters for '{{}}' ({{}} total):".format(cat_name, len(params)))
        print("")
        for pname, stype, has_val, sval in params:
            val_str = "{{}}".format(sval) if has_val else "(no value)"
            print("  {{}} [{{}}]: {{}}".format(pname, stype, val_str))
""",
            output_description="All parameter names with type and sample value.",
        )
    )
