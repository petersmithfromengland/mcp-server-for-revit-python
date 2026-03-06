# -*- coding: utf-8 -*-
"""
View stems — operations related to Revit views and UI.

Stems that modify the model (set_scale, set_detail_level, create_3d) set
``requires_transaction = True`` so the registry wraps them automatically.
Read-only / UI-only stems (switch_active, list_views, etc.) do not.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_view_stems(registry: StemRegistry) -> None:
    """Register all view-related stems."""

    # ── Switch active view ──────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.switch_active",
            name="Switch Active View",
            category="view",
            description="Switch the active view in Revit by view name.",
            parameters=[
                StemParameter("view_name", "str", "Name of the view to activate"),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View

views = FilteredElementCollector(doc).OfClass(View).ToElements()
target = None
for v in views:
    if getattr(v, 'Name', '') == "{view_name}":
        target = v
        break

if target is None:
    print("View '{view_name}' not found. Available views:")
    for v in views:
        if not v.IsTemplate:
            print("  " + getattr(v, 'Name', ''))
else:
    uidoc.ActiveView = target
    print("Switched to view: {view_name}")
""",
            output_description="Confirmation or list of available views if not found.",
        )
    )

    # ── List views ──────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.list_views",
            name="List All Views",
            category="view",
            description="List all non-template views in the model with their type and scale.",
            parameters=[
                StemParameter(
                    "view_type_filter",
                    "str",
                    "Optional filter: 'floor', 'section', 'elevation', '3d', 'sheet', or 'all'",
                    required=False,
                    default="all",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View

views = FilteredElementCollector(doc).OfClass(View).ToElements()
type_filter = "{view_type_filter}".lower()

for v in sorted(views, key=lambda x: getattr(x, 'Name', '')):
    if v.IsTemplate:
        continue
    vtype = v.ViewType.ToString()

    if type_filter != "all":
        vtype_lower = vtype.lower()
        if type_filter == "floor" and "floor" not in vtype_lower and "plan" not in vtype_lower:
            continue
        elif type_filter == "section" and "section" not in vtype_lower:
            continue
        elif type_filter == "elevation" and "elevation" not in vtype_lower:
            continue
        elif type_filter == "3d" and "3d" not in vtype_lower and "three" not in vtype_lower:
            continue
        elif type_filter == "sheet" and "sheet" not in vtype_lower:
            continue

    scale_str = ""
    try:
        scale = v.Scale
        scale_str = "1:{{}}".format(scale)
    except:
        scale_str = "N/A"

    print("{{}} | Type: {{}} | Scale: {{}} | ID: {{}}".format(
        getattr(v, 'Name', 'N/A'), vtype, scale_str, v.Id.IntegerValue))
""",
            output_description="View name, type, scale, and ID.",
        )
    )

    # ── Get view properties ─────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.get_properties",
            name="Get View Properties",
            category="view",
            description="Get detailed properties of a specific view by name.",
            parameters=[
                StemParameter("view_name", "str", "Name of the view"),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View

views = FilteredElementCollector(doc).OfClass(View).ToElements()
target = None
for v in views:
    if getattr(v, 'Name', '') == "{view_name}":
        target = v
        break

if target is None:
    print("View '{view_name}' not found")
else:
    print("Name: {{}}".format(getattr(target, 'Name', 'N/A')))
    print("ID: {{}}".format(target.Id.IntegerValue))
    print("View Type: {{}}".format(target.ViewType.ToString()))
    print("Is Template: {{}}".format(target.IsTemplate))
    try:
        print("Scale: 1:{{}}".format(target.Scale))
    except:
        pass
    try:
        print("Detail Level: {{}}".format(target.DetailLevel.ToString()))
    except:
        pass
    try:
        dl = target.get_Parameter(DB.BuiltInParameter.VIEW_DISCIPLINE)
        if dl and dl.HasValue:
            print("Discipline: {{}}".format(dl.AsValueString()))
    except:
        pass
    try:
        cb = target.CropBox
        if cb:
            print("Crop Box Min: {{}}, {{}}, {{}}".format(cb.Min.X, cb.Min.Y, cb.Min.Z))
            print("Crop Box Max: {{}}, {{}}, {{}}".format(cb.Max.X, cb.Max.Y, cb.Max.Z))
    except:
        pass
    print("Crop Box Active: {{}}".format(target.CropBoxActive))
    print("Crop Box Visible: {{}}".format(target.CropBoxVisible))
""",
            output_description="Comprehensive view properties.",
        )
    )

    # ── Set view scale ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.set_scale",
            name="Set View Scale",
            category="view",
            description="Set the scale of a view (e.g. 100 for 1:100).",
            parameters=[
                StemParameter("view_name", "str", "Name of the view"),
                StemParameter("scale", "int", "Scale denominator (e.g. 100 for 1:100)"),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View

views = FilteredElementCollector(doc).OfClass(View).ToElements()
target = None
for v in views:
    if getattr(v, 'Name', '') == "{view_name}":
        target = v
        break

if target is None:
    print("View '{view_name}' not found")
else:
    target.Scale = {scale}
    print("View '{view_name}' scale set to 1:{scale}")
""",
            output_description="Confirmation of scale change.",
        )
    )

    # ── Set view detail level ───────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.set_detail_level",
            name="Set View Detail Level",
            category="view",
            description="Set the detail level of a view.",
            parameters=[
                StemParameter("view_name", "str", "Name of the view"),
                StemParameter(
                    "detail_level",
                    "str",
                    "Detail level: 'Coarse', 'Medium', or 'Fine'",
                    choices=["Coarse", "Medium", "Fine"],
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View, ViewDetailLevel

level_map = {{
    "Coarse": ViewDetailLevel.Coarse,
    "Medium": ViewDetailLevel.Medium,
    "Fine": ViewDetailLevel.Fine,
}}

views = FilteredElementCollector(doc).OfClass(View).ToElements()
target = None
for v in views:
    if getattr(v, 'Name', '') == "{view_name}":
        target = v
        break

if target is None:
    print("View '{view_name}' not found")
else:
    detail = level_map.get("{detail_level}")
    if detail is None:
        print("Invalid detail level: {detail_level}")
    else:
        target.DetailLevel = detail
        print("View '{view_name}' detail level set to {detail_level}")
""",
            output_description="Confirmation of detail level change.",
        )
    )

    # ── Elements visible in view ────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.elements_in_view",
            name="Count Elements in View",
            category="view",
            description="Count visible elements grouped by category in the current or a named view.",
            parameters=[
                StemParameter(
                    "view_name",
                    "str",
                    "View name, or 'current' for the active view",
                    required=False,
                    default="current",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View

view_name = "{view_name}"
target = None
if view_name == "current":
    target = doc.ActiveView
else:
    views = FilteredElementCollector(doc).OfClass(View).ToElements()
    for v in views:
        if getattr(v, 'Name', '') == view_name:
            target = v
            break

if target is None:
    print("View '{{}}' not found".format(view_name))
else:
    print("View: {{}}".format(getattr(target, 'Name', 'N/A')))
    elems = FilteredElementCollector(doc, target.Id).WhereElementIsNotElementType().ToElements()
    cats = {{}}
    for e in elems:
        cat_name = e.Category.Name if e.Category else "Uncategorized"
        cats[cat_name] = cats.get(cat_name, 0) + 1
    for cat_name in sorted(cats.keys()):
        print("  {{}}: {{}}".format(cat_name, cats[cat_name]))
    print("\\nTotal elements: {{}}".format(len(list(elems))))
""",
            output_description="Category breakdown of visible elements plus total count.",
        )
    )

    # ── Create 3D view ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.create_3d",
            name="Create 3D View",
            category="view",
            description="Create a new default 3D view with a given name.",
            parameters=[
                StemParameter("view_name", "str", "Name for the new 3D view"),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewFamilyType,
    ViewFamily, View3D
)

# Find a 3D view family type
vft = None
for v in FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements():
    if v.ViewFamily == ViewFamily.ThreeDimensional:
        vft = v
        break

if vft is None:
    print("No 3D view family type found")
else:
    new_view = View3D.CreateIsometric(doc, vft.Id)
    new_view.Name = "{view_name}"
    print("3D view created: '{view_name}' (ID: {{}})".format(new_view.Id.IntegerValue))
""",
            output_description="New 3D view name and ID.",
        )
    )

    # ── Export view as image ────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="view.export_image",
            name="Export View as PNG Image",
            category="view",
            description=(
                "Export a named Revit view to a PNG image. "
                "The result includes a base64-encoded PNG blob "
                "prefixed by metadata lines (view_name, content_type, "
                "file_size_bytes, pixel_size).  Look for the "
                "VIEW_EXPORT_RESULT header in the output."
            ),
            parameters=[
                StemParameter("view_name", "str", "Name of the view to export"),
                StemParameter(
                    "pixel_size",
                    "int",
                    "Width of the exported image in pixels",
                    required=False,
                    default="1024",
                ),
            ],
            code_template="""\
import tempfile
import os
import base64
from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    FilteredElementCollector, View, ImageExportOptions,
    ExportRange, ImageFileType, ImageResolution,
    ZoomFitType, ElementId
)

view_name = "{view_name}"
target = None
all_views = FilteredElementCollector(doc).OfClass(View).ToElements()

for v in all_views:
    if getattr(v, 'Name', '') == view_name:
        target = v
        break

if target is None:
    available = []
    for v in all_views:
        if hasattr(v, 'IsTemplate') and not v.IsTemplate:
            vtype = v.ViewType.ToString()
            if vtype != "Internal" and vtype != "ProjectBrowser":
                available.append(getattr(v, 'Name', ''))
    print("View '{{}}' not found.".format(view_name))
    print("Available views (first 20):")
    for name in sorted(available)[:20]:
        print("  " + name)
elif hasattr(target, 'IsTemplate') and target.IsTemplate:
    print("Error: Cannot export view templates")
elif target.ViewType.ToString() == "Internal":
    print("Error: Cannot export internal views")
else:
    output_folder = os.path.join(tempfile.gettempdir(), "RevitMCPExports")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    file_prefix = os.path.join(output_folder, "export")

    ieo = ImageExportOptions()
    ieo.ExportRange = ExportRange.SetOfViews
    view_ids = List[ElementId]()
    view_ids.Add(target.Id)
    ieo.SetViewsAndSheets(view_ids)
    ieo.FilePath = file_prefix
    ieo.HLRandWFViewsFileType = ImageFileType.PNG
    ieo.ShadowViewsFileType = ImageFileType.PNG
    ieo.ImageResolution = ImageResolution.DPI_150
    ieo.ZoomType = ZoomFitType.FitToPage
    ieo.PixelSize = {pixel_size}

    doc.ExportImage(ieo)

    png_files = [os.path.join(output_folder, f)
                 for f in os.listdir(output_folder) if f.endswith(".png")]
    png_files.sort(key=lambda x: os.path.getctime(x), reverse=True)

    if not png_files:
        print("Error: Export failed - no image file was created")
    else:
        exported = png_files[0]
        with open(exported, "rb") as img:
            raw = img.read()

        encoded = base64.b64encode(raw)
        file_size = len(raw)

        try:
            os.remove(exported)
        except Exception:
            pass

        print("VIEW_EXPORT_RESULT")
        print("view_name: {{}}".format(view_name))
        print("content_type: image/png")
        print("file_size_bytes: {{}}".format(file_size))
        print("pixel_size: {pixel_size}")
        print("image_data_base64:")
        print(encoded)
""",
            output_description=(
                "Metadata lines followed by the raw base64-encoded PNG data. "
                "Output starts with VIEW_EXPORT_RESULT header."
            ),
        )
    )
