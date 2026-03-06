# -*- coding: utf-8 -*-
"""
Sheet, schedule, filter, and view template stems.

Based on patterns from duHast.Revit.Views (sheets, schedules, filters, templates).
"""

from .registry import StemRegistry, Stem, StemParameter


def register_sheet_schedule_filter_stems(registry: StemRegistry) -> None:
    """Register all sheet, schedule, filter and template stems."""

    # ── Sheets ──────────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.sheets",
            name="Get Sheets",
            category="query",
            description=(
                "List all sheets in the model with sheet number, name, "
                "revision, and viewport count."
            ),
            parameters=[
                StemParameter(
                    "search",
                    "str",
                    "Optional search term to filter sheets by number or name (case-insensitive)",
                    required=False,
                    default="",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, ViewSheet, BuiltInParameter

sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
search = "{search}".lower()

count = 0
for s in sorted(sheets, key=lambda x: x.SheetNumber):
    num = s.SheetNumber
    name = s.Name
    if search and search not in num.lower() and search not in name.lower():
        continue

    rev = ""
    try:
        rp = s.get_Parameter(BuiltInParameter.SHEET_CURRENT_REVISION)
        if rp and rp.AsString():
            rev = " | Rev: {{}}".format(rp.AsString())
    except:
        pass

    vp_count = 0
    try:
        vp_ids = s.GetAllViewports()
        vp_count = vp_ids.Count if vp_ids else 0
    except:
        pass

    print("Sheet: {{}} - {{}} | Viewports: {{}}{{}} | ID: {{}}".format(
        num, name, vp_count, rev, s.Id.IntegerValue))
    count += 1

print("\\nTotal: {{}} sheet(s)".format(count))
""",
            output_description="List of sheets with number, name, revision, and viewport count.",
        )
    )

    # ── Sheet detail (viewports + title block) ──────────────────────
    registry.register(
        Stem(
            stem_id="query.sheet_detail",
            name="Get Sheet Detail",
            category="query",
            description=(
                "Get detailed info about a specific sheet including "
                "all viewports, title block, and viewport positions."
            ),
            parameters=[
                StemParameter(
                    "sheet_number",
                    "str",
                    "Sheet number to inspect",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewSheet, BuiltInParameter,
    BuiltInCategory
)

# Find the sheet
all_sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
sheet = None
for s in all_sheets:
    if s.SheetNumber == "{sheet_number}":
        sheet = s
        break

if sheet is None:
    print("Sheet not found: {sheet_number}")
else:
    print("=== SHEET: {{}} - {{}} ===".format(sheet.SheetNumber, sheet.Name))
    print("ID: {{}}".format(sheet.Id.IntegerValue))

    # Revision
    try:
        rp = sheet.get_Parameter(BuiltInParameter.SHEET_CURRENT_REVISION)
        if rp and rp.AsString():
            print("Current Revision: {{}}".format(rp.AsString()))
    except:
        pass

    # Title block
    try:
        tblocks = (FilteredElementCollector(doc, sheet.Id)
            .OfCategory(BuiltInCategory.OST_TitleBlocks)
            .WhereElementIsNotElementType()
            .ToElements())
        if tblocks:
            for tb in tblocks:
                type_elem = doc.GetElement(tb.GetTypeId())
                type_name = type_elem.Name if type_elem else "?"
                fam_name = ""
                try:
                    fam_name = type_elem.FamilyName + " : "
                except:
                    pass
                print("Title Block: {{}}{{}} (ID: {{}})".format(
                    fam_name, type_name, tb.Id.IntegerValue))
    except:
        pass

    # Viewports
    try:
        vp_ids = sheet.GetAllViewports()
        if vp_ids and vp_ids.Count > 0:
            print("\\n=== VIEWPORTS ({{}} total) ===".format(vp_ids.Count))
            for vp_id in vp_ids:
                vp = doc.GetElement(vp_id)
                if vp:
                    view = doc.GetElement(vp.ViewId)
                    view_name = view.Name if view else "?"
                    view_type = str(view.ViewType) if view else "?"
                    scale = ""
                    try:
                        scale = " | Scale: 1:{{}}".format(view.Scale)
                    except:
                        pass
                    center = ""
                    try:
                        pt = vp.GetBoxCenter()
                        center = " | Center: ({{}}, {{}})".format(
                            round(pt.X, 3), round(pt.Y, 3))
                    except:
                        pass
                    print("  VP ID: {{}} | View: {{}} | Type: {{}}{{}}{{}}".format(
                        vp_id.IntegerValue, view_name, view_type, scale, center))
        else:
            print("\\nNo viewports on this sheet.")
    except:
        pass
""",
            output_description="Detailed sheet info with viewports, title block, and positions.",
        )
    )

    # ── Schedules ───────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.schedules",
            name="Get Schedules",
            category="query",
            description=(
                "List all schedules in the model with name, category, "
                "and whether they are placed on a sheet."
            ),
            parameters=[
                StemParameter(
                    "search",
                    "str",
                    "Optional search term to filter by name (case-insensitive)",
                    required=False,
                    default="",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewSchedule, ScheduleSheetInstance, ElementId
)

schedules = FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()
search = "{search}".lower()

# Build set of schedule IDs placed on sheets
on_sheet_ids = set()
try:
    sheet_instances = (FilteredElementCollector(doc)
        .OfClass(ScheduleSheetInstance)
        .ToElements())
    for si in sheet_instances:
        on_sheet_ids.add(si.ScheduleId.IntegerValue)
except:
    pass

count = 0
for sch in sorted(schedules, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
    # Skip titleblock revision schedules
    try:
        if sch.IsTitleblockRevisionSchedule:
            continue
    except:
        pass

    name = sch.Name if hasattr(sch, 'Name') else "?"
    if search and search not in name.lower():
        continue

    on_sheet = "Yes" if sch.Id.IntegerValue in on_sheet_ids else "No"

    cat_str = ""
    try:
        cat_id = sch.Definition.CategoryId
        if cat_id != ElementId.InvalidElementId:
            cat = DB.Category.GetCategory(doc, cat_id)
            if cat:
                cat_str = " | Category: {{}}".format(cat.Name)
        else:
            cat_str = " | Category: Multi-Category"
    except:
        pass

    print("ID: {{}} | Name: {{}} | On Sheet: {{}}{{}}".format(
        sch.Id.IntegerValue, name, on_sheet, cat_str))
    count += 1

print("\\nTotal: {{}} schedule(s)".format(count))
""",
            output_description="List of schedules with name, category, and sheet placement status.",
        )
    )

    # ── View filters ────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.view_filters",
            name="Get View Filters",
            category="query",
            description=(
                "List all view filters in the model. Optionally show "
                "which views/templates use each filter."
            ),
            parameters=[
                StemParameter(
                    "show_usage",
                    "bool",
                    "If true, also show which views use each filter",
                    required=False,
                    default="false",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, ParameterFilterElement, View, ViewType
)

filters = (FilteredElementCollector(doc)
    .OfClass(ParameterFilterElement)
    .ToElements())

show_usage = "{show_usage}".lower() == "true"

if not filters or len(list(filters)) == 0:
    print("No view filters in this model.")
else:
    # If showing usage, build a map of filter -> views
    filter_views = {{}}
    if show_usage:
        excluded = [ViewType.SystemBrowser, ViewType.ProjectBrowser,
                     ViewType.Undefined, ViewType.Internal, ViewType.DrawingSheet]
        all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
        for v in all_views:
            try:
                view_filters = v.GetFilters()
                if view_filters:
                    for fid in view_filters:
                        fid_int = fid.IntegerValue
                        if fid_int not in filter_views:
                            filter_views[fid_int] = []
                        label = "{}}{{}})".format(
                            v.Name, " (Template" if v.IsTemplate else "")
                        filter_views[fid_int].append(label)
            except:
                pass

    count = 0
    for f in sorted(filters, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
        name = f.Name if hasattr(f, 'Name') else "?"

        usage = ""
        if show_usage:
            views = filter_views.get(f.Id.IntegerValue, [])
            if views:
                usage = " | Used in: {{}}".format(", ".join(views[:5]))
                if len(views) > 5:
                    usage += " (+{{}})".format(len(views) - 5)
            else:
                usage = " | UNUSED"

        print("ID: {{}} | Name: {{}}{{}}".format(
            f.Id.IntegerValue, name, usage))
        count += 1

    print("\\nTotal: {{}} filter(s)".format(count))
""",
            output_description="List of view filters with optional usage information.",
        )
    )

    # ── Unused view filters ─────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.unused_view_filters",
            name="Get Unused View Filters",
            category="query",
            description=(
                "Find all view filters that are not applied to any view "
                "or view template. Useful for cleanup."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, ParameterFilterElement, View
)

filters = (FilteredElementCollector(doc)
    .OfClass(ParameterFilterElement)
    .ToElements())

if not filters or len(list(filters)) == 0:
    print("No view filters in this model.")
else:
    # Build set of all used filter IDs
    used_ids = set()
    all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
    for v in all_views:
        try:
            view_filters = v.GetFilters()
            if view_filters:
                for fid in view_filters:
                    used_ids.add(fid.IntegerValue)
        except:
            pass

    unused = []
    for f in sorted(filters, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
        if f.Id.IntegerValue not in used_ids:
            unused.append(f)

    if unused:
        print("=== UNUSED VIEW FILTERS ===")
        for f in unused:
            print("ID: {{}} | Name: {{}}".format(f.Id.IntegerValue, f.Name))
        print("\\nTotal: {{}} unused filter(s) out of {{}}".format(
            len(unused), len(list(filters))))
    else:
        print("All {{}} filter(s) are in use.".format(len(list(filters))))
""",
            output_description="List of unused view filters (not applied to any view or template).",
        )
    )

    # ── View templates ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.view_templates",
            name="Get View Templates",
            category="query",
            description=(
                "List all view templates in the model with their type, "
                "filter count, and usage count."
            ),
            parameters=[
                StemParameter(
                    "search",
                    "str",
                    "Optional search term to filter by name (case-insensitive)",
                    required=False,
                    default="",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View, ViewType, ElementId

all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
search = "{search}".lower()

# Split into templates and non-templates
templates = []
non_templates = []
for v in all_views:
    if v.IsTemplate:
        templates.append(v)
    else:
        non_templates.append(v)

# Count usage of each template
usage_count = {{}}
for v in non_templates:
    try:
        tid = v.ViewTemplateId
        if tid != ElementId.InvalidElementId:
            tid_int = tid.IntegerValue
            usage_count[tid_int] = usage_count.get(tid_int, 0) + 1
    except:
        pass

if not templates:
    print("No view templates in this model.")
else:
    count = 0
    for t in sorted(templates, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
        name = t.Name if hasattr(t, 'Name') else "?"
        if search and search not in name.lower():
            continue

        vtype = str(t.ViewType) if hasattr(t, 'ViewType') else "?"
        used = usage_count.get(t.Id.IntegerValue, 0)

        filter_count = 0
        try:
            fids = t.GetFilters()
            filter_count = fids.Count if fids else 0
        except:
            pass

        print("ID: {{}} | Name: {{}} | Type: {{}} | Filters: {{}} | Used by: {{}} view(s)".format(
            t.Id.IntegerValue, name, vtype, filter_count, used))
        count += 1

    print("\\nTotal: {{}} template(s)".format(count))
""",
            output_description="List of view templates with type, filter count, and usage.",
        )
    )

    # ── Unused view templates ───────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.unused_view_templates",
            name="Get Unused View Templates",
            category="query",
            description=(
                "Find all view templates not assigned to any view and "
                "not used as defaults by view types. Useful for cleanup."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, View, ElementId

all_views = FilteredElementCollector(doc).OfClass(View).ToElements()

templates = []
non_templates = []
for v in all_views:
    if v.IsTemplate:
        templates.append(v)
    else:
        non_templates.append(v)

# Used by views
used_ids = set()
for v in non_templates:
    try:
        tid = v.ViewTemplateId
        if tid != ElementId.InvalidElementId:
            used_ids.add(tid.IntegerValue)
    except:
        pass

# Used as defaults by view family types
try:
    vf_types = FilteredElementCollector(doc).OfClass(DB.ViewFamilyType).ToElements()
    for vft in vf_types:
        try:
            def_tid = vft.DefaultTemplateId
            if def_tid != ElementId.InvalidElementId:
                used_ids.add(def_tid.IntegerValue)
        except:
            pass
except:
    pass

unused = [t for t in templates if t.Id.IntegerValue not in used_ids]

if unused:
    print("=== UNUSED VIEW TEMPLATES ===")
    for t in sorted(unused, key=lambda x: x.Name):
        print("ID: {{}} | Name: {{}} | Type: {{}}".format(
            t.Id.IntegerValue, t.Name, str(t.ViewType)))
    print("\\nTotal: {{}} unused template(s) out of {{}}".format(
        len(unused), len(templates)))
else:
    print("All {{}} template(s) are in use.".format(len(templates)))
""",
            output_description="List of unused view templates (not assigned to any view).",
        )
    )

    # ── Views not on sheet ──────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.views_not_on_sheet",
            name="Get Views Not On Sheet",
            category="query",
            description=(
                "Find all views that are not placed on any sheet. "
                "Useful for model cleanup and documentation review."
            ),
            parameters=[
                StemParameter(
                    "view_type",
                    "str",
                    "Optional view type filter: FloorPlan, CeilingPlan, Elevation, Section, ThreeD, or empty for all",
                    required=False,
                    default="",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, View, ViewSheet, ViewType, ElementId
)

# Get all views on sheets
sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
on_sheet_ids = set()
for sheet in sheets:
    try:
        vp_ids = sheet.GetAllViewports()
        if vp_ids:
            for vp_id in vp_ids:
                vp = doc.GetElement(vp_id)
                if vp:
                    on_sheet_ids.add(vp.ViewId.IntegerValue)
    except:
        pass

# Map string to ViewType
vtype_filter = "{view_type}"
vtype_map = {{
    "FloorPlan": ViewType.FloorPlan,
    "CeilingPlan": ViewType.CeilingPlan,
    "Elevation": ViewType.Elevation,
    "Section": ViewType.Section,
    "ThreeD": ViewType.ThreeD,
    "Detail": ViewType.Detail,
    "Legend": ViewType.Legend,
    "DraftingView": ViewType.DraftingView,
}}

excluded = [ViewType.SystemBrowser, ViewType.ProjectBrowser,
             ViewType.Undefined, ViewType.Internal, ViewType.DrawingSheet,
             ViewType.Schedule]

all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
results = []
for v in all_views:
    if v.IsTemplate:
        continue
    if v.ViewType in excluded:
        continue
    if vtype_filter and vtype_filter in vtype_map:
        if v.ViewType != vtype_map[vtype_filter]:
            continue
    if v.Id.IntegerValue not in on_sheet_ids:
        results.append(v)

if results:
    print("=== VIEWS NOT ON SHEET ===")
    for v in sorted(results, key=lambda x: (str(x.ViewType), x.Name)):
        tpl = ""
        try:
            if v.ViewTemplateId != ElementId.InvalidElementId:
                t = doc.GetElement(v.ViewTemplateId)
                tpl = " | Template: {{}}".format(t.Name) if t else ""
        except:
            pass
        print("ID: {{}} | {{}} | Type: {{}}{{}}".format(
            v.Id.IntegerValue, v.Name, str(v.ViewType), tpl))
    print("\\nTotal: {{}} view(s) not on any sheet".format(len(results)))
else:
    print("All views are placed on sheets.")
""",
            output_description="List of views not placed on any sheet.",
        )
    )

    # ── Apply filter to view ────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.apply_filter_to_view",
            name="Apply Filter to View",
            category="modify",
            description=(
                "Apply an existing view filter to a view. "
                "The filter must already exist in the model."
            ),
            parameters=[
                StemParameter(
                    "view_id",
                    "int",
                    "ID of the view to apply the filter to",
                ),
                StemParameter(
                    "filter_id",
                    "int",
                    "ID of the ParameterFilterElement to apply",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ElementId

view = doc.GetElement(ElementId({view_id}))
filt = doc.GetElement(ElementId({filter_id}))

if view is None:
    print("View not found: {view_id}")
elif filt is None:
    print("Filter not found: {filter_id}")
else:
    # Check if already applied
    existing = view.GetFilters()
    already = False
    if existing:
        for eid in existing:
            if eid.IntegerValue == {filter_id}:
                already = True
                break

    if already:
        print("Filter '{{}}' is already applied to view '{{}}'.".format(
            filt.Name, view.Name))
    else:
        view.AddFilter(ElementId({filter_id}))
        print("Applied filter '{{}}' to view '{{}}'.".format(
            filt.Name, view.Name))
""",
            output_description="Confirmation that the filter was applied to the view.",
        )
    )

    # ── Create sheet ────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.create_sheet",
            name="Create Sheet",
            category="modify",
            description=(
                "Create a new sheet using an existing title block type. "
                "Pass ElementId.InvalidElementId for no title block."
            ),
            parameters=[
                StemParameter(
                    "titleblock_type_id",
                    "int",
                    "ID of the title block type to use (-1 for none)",
                ),
                StemParameter(
                    "sheet_number",
                    "str",
                    "Sheet number to assign",
                ),
                StemParameter(
                    "sheet_name",
                    "str",
                    "Sheet name to assign",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import ViewSheet, ElementId

tb_id = {titleblock_type_id}
if tb_id == -1:
    tb_eid = ElementId.InvalidElementId
else:
    tb_eid = ElementId(tb_id)

new_sheet = ViewSheet.Create(doc, tb_eid)
new_sheet.SheetNumber = "{sheet_number}"
new_sheet.Name = "{sheet_name}"

print("Created sheet: {{}} - {{}} (ID: {{}})".format(
    new_sheet.SheetNumber, new_sheet.Name, new_sheet.Id.IntegerValue))
""",
            output_description="Confirmation of created sheet with ID.",
        )
    )
