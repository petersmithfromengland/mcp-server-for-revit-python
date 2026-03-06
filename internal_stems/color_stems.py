# -*- coding: utf-8 -*-
"""
Color stems — element colour overrides based on parameter values.

Converted from the original ``revit_mcp/colors.py`` route handlers.
All helper functions are inlined in the code templates so that each
stem is fully self-contained when sent to ``/execute_code/``.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_color_stems(registry: StemRegistry) -> None:
    """Register all colour-override stems."""

    # ── Color elements by parameter value ───────────────────────────
    registry.register(
        Stem(
            stem_id="modify.color_by_parameter",
            name="Color Elements by Parameter",
            category="modify",
            description=(
                "Apply colour overrides to all elements in a category, "
                "grouped by the value of a chosen parameter.  Each unique "
                "parameter value gets a distinct colour.  Optionally use a "
                "gradient (blue→red) instead of distinct colours, or supply "
                "custom hex colours.  Operates on the active view."
            ),
            parameters=[
                StemParameter(
                    "category_name",
                    "str",
                    "Revit category name (e.g. 'Walls', 'Doors', 'Rooms')",
                ),
                StemParameter(
                    "parameter_name",
                    "str",
                    "Parameter name to group/colour by (e.g. 'Mark', 'Level', 'Type Name')",
                ),
                StemParameter(
                    "use_gradient",
                    "bool",
                    "Use a blue-to-red gradient instead of distinct colours",
                    required=False,
                    default="false",
                ),
                StemParameter(
                    "custom_colors",
                    "str",
                    "Optional comma-separated hex colours (e.g. '#FF0000,#00FF00,#0000FF'). "
                    "Leave empty to auto-generate.",
                    required=False,
                    default="",
                ),
            ],
            requires_transaction=True,
            code_template="""\
import random
from collections import defaultdict

# ── Helper: distinct colour palette ──────────────────────────────
_BASE_COLORS = [
    (255,0,0),(0,255,0),(0,0,255),(255,255,0),(255,0,255),
    (0,255,255),(255,128,0),(128,0,255),(255,128,128),(128,255,128),
    (128,128,255),(255,255,128),(128,0,0),(0,128,0),(0,0,128),
    (128,128,0),(128,0,128),(0,128,128),(192,192,192),(128,128,128),
    (255,192,203),(255,165,0),(255,20,147),(50,205,50),(30,144,255),
]

def _distinct_colors(n):
    cols = []
    for i in range(n):
        if i < len(_BASE_COLORS):
            r, g, b = _BASE_COLORS[i]
        else:
            base = _BASE_COLORS[i % len(_BASE_COLORS)]
            factor = max(0.3, 1.0 - (i // len(_BASE_COLORS)) * 0.15)
            r = int(base[0] * factor)
            g = int(base[1] * factor)
            b = int(base[2] * factor)
        cols.append(DB.Color(r, g, b))
    return cols

def _gradient_colors(n):
    if n <= 1:
        return [DB.Color(255, 0, 0)]
    cols = []
    for i in range(n):
        ratio = float(i) / (n - 1)
        r = int(255 * ratio)
        g = int(255 * (1 - abs(2 * ratio - 1)))
        b = int(255 * (1 - ratio))
        cols.append(DB.Color(r, g, b))
    return cols

def _interpolate_color(pos):
    pos = max(0.0, min(1.0, pos))
    r = int(255 * pos)
    g = int(255 * (1 - abs(2 * pos - 1)))
    b = int(255 * (1 - pos))
    return DB.Color(r, g, b)

def _hex_to_rgb(h):
    h = h.lstrip("#")
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (255, 0, 0)

def _solid_fill_id(document):
    collector = DB.FilteredElementCollector(document).OfClass(DB.FillPatternElement)
    for pe in collector:
        pat = pe.GetFillPattern()
        if pat.IsSolidFill:
            return pe.Id
    return None

def _safe_color_hex(c):
    try:
        return "#{{0:02x}}{{1:02x}}{{2:02x}}".format(
            max(0, min(255, int(c.Red))),
            max(0, min(255, int(c.Green))),
            max(0, min(255, int(c.Blue))))
    except Exception:
        return "#ff0000"

def _get_param_for_sorting(element, pname):
    for p in element.Parameters:
        if p.Definition.Name == pname:
            if not p.HasValue:
                return ("None", "None")
            if p.StorageType == DB.StorageType.Double:
                raw = p.AsDouble()
                disp = p.AsValueString() or str(raw)
                return (raw, disp)
            elif p.StorageType == DB.StorageType.Integer:
                try:
                    if hasattr(p.Definition, "GetDataType"):
                        pt = p.Definition.GetDataType()
                        if hasattr(DB, "SpecTypeId") and hasattr(DB.SpecTypeId, "Boolean"):
                            if pt == DB.SpecTypeId.Boolean.YesNo:
                                bv = "True" if p.AsInteger() == 1 else "False"
                                return (bv, bv)
                    elif hasattr(p.Definition, "ParameterType"):
                        pt = p.Definition.ParameterType
                        if pt == DB.ParameterType.YesNo:
                            bv = "True" if p.AsInteger() == 1 else "False"
                            return (bv, bv)
                    iv = p.AsInteger()
                    dv = p.AsValueString() or str(iv)
                    return (iv, dv)
                except:
                    iv = p.AsInteger()
                    return (iv, str(iv))
            elif p.StorageType == DB.StorageType.String:
                sv = p.AsString() or "None"
                return (sv, sv)
            elif p.StorageType == DB.StorageType.ElementId:
                eid = p.AsElementId()
                if eid and eid != DB.ElementId.InvalidElementId:
                    try:
                        el = element.Document.GetElement(eid)
                        if el and hasattr(el, "Name"):
                            nm = el.Name or "None"
                            return (nm, nm)
                    except:
                        pass
                return ("None", "None")
            else:
                vs = p.AsValueString() or "None"
                return (vs, vs)
    # Try type parameters
    try:
        et = element.Document.GetElement(element.GetTypeId())
        if et:
            for p in et.Parameters:
                if p.Definition.Name == pname:
                    if not p.HasValue:
                        return ("None", "None")
                    if p.StorageType == DB.StorageType.Double:
                        raw = p.AsDouble()
                        disp = p.AsValueString() or str(raw)
                        return (raw, disp)
                    elif p.StorageType == DB.StorageType.Integer:
                        iv = p.AsInteger()
                        dv = p.AsValueString() or str(iv)
                        return (iv, dv)
                    elif p.StorageType == DB.StorageType.String:
                        sv = p.AsString() or "None"
                        return (sv, sv)
                    elif p.StorageType == DB.StorageType.ElementId:
                        eid = p.AsElementId()
                        if eid and eid != DB.ElementId.InvalidElementId:
                            try:
                                el = element.Document.GetElement(eid)
                                if el and hasattr(el, "Name"):
                                    nm = el.Name or "None"
                                    return (nm, nm)
                            except:
                                pass
                        return ("None", "None")
                    else:
                        vs = p.AsValueString() or "None"
                        return (vs, vs)
    except:
        pass
    return ("None", "None")

def _safe_float(s):
    if not s or s == "None":
        return float("inf")
    try:
        clean = str(s).strip()
        idx = 0
        for ch in reversed(clean):
            if ch.isdigit() or ch == "." or ch == "-" or ch == "+":
                break
            idx += 1
        num = clean[:-idx] if idx > 0 else clean
        return float(num)
    except (ValueError, TypeError):
        return float("inf")

# ── Main logic ───────────────────────────────────────────────────
cat_name = "{category_name}"
param_name = "{parameter_name}"
use_grad = "{use_gradient}".lower() in ("true", "1", "yes")
custom_hex = "{custom_colors}".strip()

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
        print("No elements found in category '{{}}'".format(cat_name))
    else:
        # Group by parameter value
        groups = defaultdict(list)
        value_data = {{}}
        for el in elems:
            raw, disp = _get_param_for_sorting(el, param_name)
            groups[disp].append(el)
            if disp not in value_data:
                value_data[disp] = raw

        def _sort_key(dv):
            rv = value_data[dv]
            if dv == "None" or rv == "None":
                return (2, 0)
            if dv in ("True", "False"):
                return (1, 0 if dv == "False" else 1)
            if isinstance(rv, (int, float)):
                return (0, rv)
            try:
                nv = _safe_float(dv)
                if nv != float("inf"):
                    return (0, nv)
            except:
                pass
            return (1.5, str(dv).lower())

        sorted_vals = sorted(groups.keys(), key=_sort_key)
        val_count = len(sorted_vals)

        # Determine if numeric gradient is appropriate
        numeric_keywords = ["length", "area", "volume", "height",
                            "width", "thickness", "longueur"]
        is_numeric_grad = use_grad and any(
            kw in param_name.lower() for kw in numeric_keywords)

        # Build value positions for numeric gradient
        value_positions = {{}}
        if is_numeric_grad:
            num_vals = []
            for dv in sorted_vals:
                rv = value_data[dv]
                if isinstance(rv, (int, float)):
                    num_vals.append(rv)
            if num_vals:
                mn, mx = min(num_vals), max(num_vals)
                for dv in sorted_vals:
                    rv = value_data[dv]
                    if isinstance(rv, (int, float)) and mx != mn:
                        value_positions[dv] = (rv - mn) / (mx - mn)
                    else:
                        value_positions[dv] = 0.5
            else:
                for i, dv in enumerate(sorted_vals):
                    value_positions[dv] = float(i) / max(1, val_count - 1)

        # Generate colours
        if custom_hex:
            hex_list = [h.strip() for h in custom_hex.split(",") if h.strip()]
            colors = [DB.Color(*_hex_to_rgb(h)) for h in hex_list[:val_count]]
            if len(colors) < val_count:
                colors.extend(_distinct_colors(val_count - len(colors)))
        elif use_grad and is_numeric_grad:
            colors = [_interpolate_color(value_positions.get(dv, 0.5))
                      for dv in sorted_vals]
        elif use_grad:
            colors = _gradient_colors(val_count)
        else:
            colors = _distinct_colors(val_count)

        # Apply overrides
        solid_id = _solid_fill_id(doc)
        active_view = doc.ActiveView
        colored = 0

        for i, pv in enumerate(sorted_vals):
            color = colors[i] if i < len(colors) else DB.Color(
                random.randint(0,255), random.randint(0,255), random.randint(0,255))
            ogs = DB.OverrideGraphicSettings()
            ogs.SetProjectionLineColor(color)
            ogs.SetSurfaceForegroundPatternColor(color)
            ogs.SetCutForegroundPatternColor(color)
            ogs.SetCutLineColor(color)
            ogs.SetProjectionLineWeight(3)
            if solid_id is not None:
                ogs.SetSurfaceForegroundPatternId(solid_id)
                ogs.SetCutForegroundPatternId(solid_id)
            for el in groups[pv]:
                try:
                    active_view.SetElementOverrides(el.Id, ogs)
                    colored += 1
                except:
                    pass

        print("Colored {{}} elements in {{}} groups".format(colored, val_count))
        print("Category: {{}}".format(cat_name))
        print("Parameter: {{}}".format(param_name))
        print("Mode: {{}}".format(
            "numeric gradient" if is_numeric_grad
            else "gradient" if use_grad
            else "custom" if custom_hex
            else "distinct"))
        print("")
        for i, pv in enumerate(sorted_vals):
            c = colors[i] if i < len(colors) else None
            hex_str = _safe_color_hex(c) if c else "N/A"
            print("  {{}} -> {{}} ({{}} elements)".format(
                pv, hex_str, len(groups[pv])))
""",
            output_description=(
                "Summary of coloured elements: count, groups, and colour "
                "assignment per parameter value."
            ),
        )
    )

    # ── Clear colour overrides ──────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.clear_color_overrides",
            name="Clear Element Color Overrides",
            category="modify",
            description=(
                "Remove all graphic overrides (colour, line weight, fill "
                "pattern) from elements in a category in the active view."
            ),
            parameters=[
                StemParameter(
                    "category_name",
                    "str",
                    "Revit category name (e.g. 'Walls', 'Doors', 'Rooms')",
                ),
            ],
            requires_transaction=True,
            code_template="""\
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
        print("No elements found in category '{{}}'".format(cat_name))
    else:
        active_view = doc.ActiveView
        empty_ogs = DB.OverrideGraphicSettings()
        cleared = 0
        for el in elems:
            try:
                active_view.SetElementOverrides(el.Id, empty_ogs)
                cleared += 1
            except:
                pass
        print("Cleared colour overrides for {{}} elements in '{{}}'".format(
            cleared, cat_name))
""",
            output_description="Count of elements whose overrides were cleared.",
        )
    )
