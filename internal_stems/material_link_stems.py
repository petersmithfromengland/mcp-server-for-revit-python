# -*- coding: utf-8 -*-
"""
Material and link stems — material queries and linked model operations.

Based on patterns from duHast.Revit.Materials and duHast.Revit.Links.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_material_link_stems(registry: StemRegistry) -> None:
    """Register all material and link stems."""

    # ── Materials ───────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.materials",
            name="Get Materials",
            category="query",
            description=(
                "List all materials in the model with name, class, "
                "color (RGB), and transparency."
            ),
            parameters=[
                StemParameter(
                    "search",
                    "str",
                    "Optional search term to filter materials by name (case-insensitive)",
                    required=False,
                    default="",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, Material

materials = FilteredElementCollector(doc).OfClass(Material).ToElements()
search = "{search}".lower()

count = 0
for m in sorted(materials, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    name = m.Name if hasattr(m, 'Name') else "?"
    if search and search not in name.lower():
        continue

    color_str = ""
    try:
        c = m.Color
        if c and c.IsValid:
            color_str = " | RGB: ({{}}, {{}}, {{}})".format(c.Red, c.Green, c.Blue)
    except:
        pass

    transp_str = ""
    try:
        transp_str = " | Transparency: {{}}%".format(m.Transparency)
    except:
        pass

    mat_class = ""
    try:
        mc = m.MaterialClass
        if mc:
            mat_class = " | Class: {{}}".format(mc)
    except:
        pass

    mat_cat = ""
    try:
        cat = m.MaterialCategory
        if cat:
            mat_cat = " | Category: {{}}".format(cat)
    except:
        pass

    print("ID: {{}} | Name: {{}}{{}}{{}}{{}}{{}}".format(
        m.Id.IntegerValue, name, mat_class, mat_cat, color_str, transp_str))
    count += 1

print("\\nTotal: {{}} material(s)".format(count))
""",
            output_description="List of materials with color, class, and transparency.",
        )
    )

    # ── Material of element ─────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.element_material",
            name="Get Element Materials",
            category="query",
            description=(
                "Get all materials used by an element, including "
                "paint materials and compound structure layer materials."
            ),
            parameters=[
                StemParameter(
                    "element_id",
                    "int",
                    "Element ID to inspect",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import ElementId

elem = doc.GetElement(ElementId({element_id}))
if elem is None:
    print("Element not found: {element_id}")
else:
    cat_name = elem.Category.Name if elem.Category else "?"
    print("Element ID: {element_id} | Category: {{}}".format(cat_name))

    # Get material IDs from the element
    mat_ids = elem.GetMaterialIds(False)  # False = not paint
    paint_ids = elem.GetMaterialIds(True)  # True = paint only

    if mat_ids and mat_ids.Count > 0:
        print("\\n=== ELEMENT MATERIALS ===")
        for mid in mat_ids:
            mat = doc.GetElement(mid)
            if mat:
                area_str = ""
                try:
                    area = elem.GetMaterialArea(mid, False)
                    if area > 0:
                        area_str = " | Area: {{}} sq ft".format(round(area, 2))
                except:
                    pass

                vol_str = ""
                try:
                    vol = elem.GetMaterialVolume(mid)
                    if vol > 0:
                        vol_str = " | Volume: {{}} cu ft".format(round(vol, 4))
                except:
                    pass

                print("  ID: {{}} | Name: {{}}{{}}{{}}".format(
                    mid.IntegerValue, mat.Name, area_str, vol_str))
    else:
        print("\\nNo materials directly assigned to this element.")

    if paint_ids and paint_ids.Count > 0:
        print("\\n=== PAINT MATERIALS ===")
        for mid in paint_ids:
            mat = doc.GetElement(mid)
            if mat:
                print("  ID: {{}} | Name: {{}}".format(mid.IntegerValue, mat.Name))
""",
            output_description="Materials used by the element with area and volume.",
        )
    )

    # ── Revit links ─────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.revit_links",
            name="Get Revit Links",
            category="query",
            description=(
                "List all Revit links (RVT) in the model with their "
                "status, file path, and instance count."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, RevitLinkType, RevitLinkInstance
)

# Link types
link_types = FilteredElementCollector(doc).OfClass(RevitLinkType).ToElements()

# Link instances
link_instances = FilteredElementCollector(doc).OfClass(RevitLinkInstance).ToElements()

# Count instances per type
type_counts = {{}}
for inst in link_instances:
    tid = inst.GetTypeId().IntegerValue
    type_counts[tid] = type_counts.get(tid, 0) + 1

if not link_types or len(list(link_types)) == 0:
    print("No Revit links in this model.")
else:
    print("=== REVIT LINKS ===")
    for lt in sorted(link_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
        name = lt.Name if hasattr(lt, 'Name') else "?"
        instances = type_counts.get(lt.Id.IntegerValue, 0)

        path_str = ""
        try:
            ref = lt.GetExternalFileReference()
            if ref:
                path = ref.GetAbsolutePath()
                if path:
                    path_str = " | Path: {{}}".format(path.ToString() if hasattr(path, 'ToString') else str(path))
        except:
            pass

        status_str = ""
        try:
            ref = lt.GetExternalFileReference()
            if ref:
                status = ref.GetLinkedFileStatus()
                status_str = " | Status: {{}}".format(str(status))
        except:
            pass

        print("Type ID: {{}} | Name: {{}} | Instances: {{}}{{}}{{}}".format(
            lt.Id.IntegerValue, name, instances, status_str, path_str))

    print("\\nTotal: {{}} link type(s), {{}} instance(s)".format(
        len(list(link_types)), len(list(link_instances))))

# CAD links
print("\\n=== CAD LINKS ===")
try:
    cad_links = (FilteredElementCollector(doc)
        .OfClass(DB.ImportInstance)
        .ToElements())

    if cad_links and len(list(cad_links)) > 0:
        for cl in cad_links:
            linked = "Linked" if cl.IsLinked else "Imported"
            view_str = ""
            try:
                if cl.ViewSpecific:
                    owner_view = doc.GetElement(cl.OwnerViewId)
                    if owner_view:
                        view_str = " | View: {{}}".format(owner_view.Name)
            except:
                pass
            print("ID: {{}} | {{}} | {{}}{{}}".format(
                cl.Id.IntegerValue, cl.Name if hasattr(cl, 'Name') else "?",
                linked, view_str))
        print("Total: {{}}".format(len(list(cad_links))))
    else:
        print("No CAD links found.")
except:
    print("No CAD links found.")
""",
            output_description="Revit and CAD links with status and instance counts.",
        )
    )

    # ── Image links ─────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.image_links",
            name="Get Image Links",
            category="query",
            description=("List all image types (linked and imported) in the model."),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory

# Image types
image_types = (FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_RasterImages)
    .WhereElementIsElementType()
    .ToElements())

if not image_types or len(list(image_types)) == 0:
    print("No image types found in this model.")
else:
    print("=== IMAGE TYPES ===")
    for it in sorted(image_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
        name = it.Name if hasattr(it, 'Name') else "?"
        path_str = ""
        try:
            path_param = it.get_Parameter(DB.BuiltInParameter.RASTER_SYMBOL_FILENAME)
            if path_param:
                path_str = " | Path: {{}}".format(path_param.AsString())
        except:
            pass

        print("ID: {{}} | Name: {{}}{{}}".format(
            it.Id.IntegerValue, name, path_str))

    print("\\nTotal: {{}} image type(s)".format(len(list(image_types))))
""",
            output_description="List of image types with file paths.",
        )
    )
