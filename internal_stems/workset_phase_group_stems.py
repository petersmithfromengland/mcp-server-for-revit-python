# -*- coding: utf-8 -*-
"""
Workset, phase, and group stems — organizational model queries and operations.

Based on patterns from duHast.Revit.Common.worksets,
duHast.Revit.Common.phases, and duHast.Revit.Common.groups.
"""

from .registry import StemRegistry, Stem, StemParameter


def register_workset_phase_group_stems(registry: StemRegistry) -> None:
    """Register all workset, phase, and group stems."""

    # ── Worksets ────────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.worksets",
            name="Get Worksets",
            category="query",
            description=(
                "List all user worksets in the model with name, ID, "
                "is open, is default, and is visible by default."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredWorksetCollector, WorksetKind

try:
    worksets = (FilteredWorksetCollector(doc)
        .OfKind(WorksetKind.UserWorkset)
        .ToList())

    if not worksets or worksets.Count == 0:
        print("No user worksets found (document may not be workshared).")
    else:
        for ws in sorted(worksets, key=lambda w: w.Name):
            open_str = "Open" if ws.IsOpen else "Closed"
            default_str = " | DEFAULT" if ws.IsDefaultWorkset else ""
            visible_str = " | Visible by default: {{}}".format(ws.IsVisibleByDefault)
            print("ID: {{}} | Name: {{}} | {{}}{{}}{{}}".format(
                ws.Id.IntegerValue, ws.Name, open_str, default_str, visible_str))
        print("\\nTotal: {{}} workset(s)".format(worksets.Count))
except Exception as e:
    print("Error listing worksets: {{}}".format(e))
    print("Document may not be workshared.")
""",
            output_description="List of worksets with status information.",
        )
    )

    # ── Element workset ─────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.element_workset",
            name="Get Element Workset",
            category="query",
            description=("Get the workset name and ID for one or more elements."),
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs",
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import ElementId, BuiltInParameter

ids = [int(x.strip()) for x in "{element_ids}".split(",")]

for eid_int in ids:
    elem = doc.GetElement(ElementId(eid_int))
    if elem is None:
        print("Element {{}}: NOT FOUND".format(eid_int))
        continue

    ws_param = elem.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
    if ws_param is None:
        print("Element {{}}: No workset parameter".format(eid_int))
    else:
        ws_name = ws_param.AsValueString() or "N/A"
        print("Element {{}} | Workset: {{}}".format(eid_int, ws_name))
""",
            output_description="Workset name for each element.",
        )
    )

    # ── Create workset ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.create_workset",
            name="Create Workset",
            category="modify",
            description=("Create a new user workset in a workshared document."),
            parameters=[
                StemParameter(
                    "workset_name",
                    "str",
                    "Name for the new workset",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import Workset, WorksetTable

if not doc.IsWorkshared:
    print("Document is not workshared. Cannot create worksets.")
else:
    ws_table = doc.GetWorksetTable()
    if not WorksetTable.IsWorksetNameUnique(doc, "{workset_name}"):
        print("Workset '{workset_name}' already exists.")
    else:
        new_ws = Workset.Create(doc, "{workset_name}")
        print("Created workset: {{}}".format(new_ws.Name))
        print("Workset ID: {{}}".format(new_ws.Id.IntegerValue))
""",
            output_description="Confirmation with new workset name and ID.",
        )
    )

    # ── Change element workset ──────────────────────────────────────
    registry.register(
        Stem(
            stem_id="modify.change_element_workset",
            name="Change Element Workset",
            category="modify",
            description=("Move one or more elements to a different workset by name."),
            parameters=[
                StemParameter(
                    "element_ids",
                    "str",
                    "Comma-separated element IDs",
                ),
                StemParameter(
                    "workset_name",
                    "str",
                    "Name of the target workset",
                ),
            ],
            requires_transaction=True,
            code_template="""\
from Autodesk.Revit.DB import (
    ElementId, BuiltInParameter, FilteredWorksetCollector, WorksetKind
)

# Find target workset
worksets = FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset).ToList()
target_ws = None
for ws in worksets:
    if ws.Name == "{workset_name}":
        target_ws = ws
        break

if target_ws is None:
    print("Workset '{workset_name}' not found. Available:")
    for ws in worksets:
        print("  " + ws.Name)
else:
    ids = [int(x.strip()) for x in "{element_ids}".split(",")]
    moved = 0
    for eid_int in ids:
        elem = doc.GetElement(ElementId(eid_int))
        if elem is None:
            print("Element not found: {{}}".format(eid_int))
            continue

        ws_param = elem.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
        if ws_param is None or ws_param.IsReadOnly:
            print("Cannot change workset for element {{}}".format(eid_int))
            continue

        ws_param.Set(target_ws.Id.IntegerValue)
        moved += 1
        print("Moved element {{}} to workset '{workset_name}'".format(eid_int))

    print("\\nMoved {{}} element(s)".format(moved))
""",
            output_description="Confirmation for each element moved to target workset.",
        )
    )

    # ── Phases ──────────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.phases",
            name="Get Phases",
            category="query",
            description=(
                "List all phases in the model in chronological order "
                "(oldest to newest) with element counts."
            ),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInParameter, BuiltInCategory
)

phases = doc.Phases
if phases.Size == 0:
    print("No phases found.")
else:
    print("=== PHASES (oldest to newest) ===")
    for i in range(phases.Size):
        phase = phases[i]
        # Count elements created in this phase
        count = 0
        try:
            all_elems = (FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .ToElements())
            for elem in all_elems:
                try:
                    cp = elem.get_Parameter(BuiltInParameter.PHASE_CREATED)
                    if cp and cp.AsElementId().IntegerValue == phase.Id.IntegerValue:
                        count += 1
                except:
                    pass
        except:
            count = -1

        count_str = " | Elements created: {{}}".format(count) if count >= 0 else ""
        print("ID: {{}} | Name: {{}} | Order: {{}}{{}}".format(
            phase.Id.IntegerValue, phase.Name, i + 1, count_str))

    print("\\nTotal: {{}} phase(s)".format(phases.Size))
""",
            output_description="List of phases in order with element counts.",
        )
    )

    # ── Model groups ────────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.groups",
            name="Get Groups",
            category="query",
            description=(
                "List all model groups and detail groups in the model "
                "with type name, instance count, and member element count."
            ),
            parameters=[
                StemParameter(
                    "group_type",
                    "str",
                    "Filter: 'model', 'detail', or 'all'",
                    required=False,
                    default="all",
                    choices=["model", "detail", "all"],
                ),
            ],
            code_template="""\
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory
)

group_type = "{group_type}".lower()

if group_type in ("model", "all"):
    # Model group types
    model_types = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_IOSModelGroups)
        .WhereElementIsElementType()
        .ToElements())

    model_instances = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_IOSModelGroups)
        .WhereElementIsNotElementType()
        .ToElements())

    # Count instances per type
    type_counts = {{}}
    for inst in model_instances:
        tid = inst.GetTypeId().IntegerValue
        type_counts[tid] = type_counts.get(tid, 0) + 1

    print("=== MODEL GROUPS ===")
    for gt in sorted(model_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
        count = type_counts.get(gt.Id.IntegerValue, 0)
        member_str = ""
        try:
            # Get member count from first instance
            for inst in model_instances:
                if inst.GetTypeId().IntegerValue == gt.Id.IntegerValue:
                    member_ids = inst.GetMemberIds()
                    member_str = " | Members: {{}}".format(member_ids.Count)
                    break
        except:
            pass
        print("ID: {{}} | Name: {{}} | Instances: {{}}{{}}".format(
            gt.Id.IntegerValue, gt.Name, count, member_str))
    print("Total types: {{}} | Total instances: {{}}".format(
        len(model_types), len(model_instances)))

if group_type in ("detail", "all"):
    # Detail group types
    detail_types = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_IOSDetailGroups)
        .WhereElementIsElementType()
        .ToElements())

    detail_instances = (FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_IOSDetailGroups)
        .WhereElementIsNotElementType()
        .ToElements())

    type_counts = {{}}
    for inst in detail_instances:
        tid = inst.GetTypeId().IntegerValue
        type_counts[tid] = type_counts.get(tid, 0) + 1

    print("\\n=== DETAIL GROUPS ===")
    for gt in sorted(detail_types, key=lambda x: x.Name if hasattr(x, 'Name') else ''):
        count = type_counts.get(gt.Id.IntegerValue, 0)
        print("ID: {{}} | Name: {{}} | Instances: {{}}".format(
            gt.Id.IntegerValue, gt.Name, count))
    print("Total types: {{}} | Total instances: {{}}".format(
        len(detail_types), len(detail_instances)))
""",
            output_description="Group types with instance counts and member counts.",
        )
    )

    # ── Design options ──────────────────────────────────────────────
    registry.register(
        Stem(
            stem_id="query.design_options",
            name="Get Design Options",
            category="query",
            description=("List all design option sets and their options in the model."),
            parameters=[],
            code_template="""\
from Autodesk.Revit.DB import FilteredElementCollector, DesignOption

options = (FilteredElementCollector(doc)
    .OfClass(DesignOption)
    .ToElements())

if not options or len(list(options)) == 0:
    print("No design options found in this model.")
else:
    sets = {{}}
    for opt in options:
        try:
            set_name_param = opt.get_Parameter(DB.BuiltInParameter.OPTION_SET_NAME)
            set_name = set_name_param.AsString() if set_name_param else "Unknown Set"
        except:
            set_name = "Unknown Set"

        if set_name not in sets:
            sets[set_name] = []

        is_primary = ""
        try:
            if opt.IsPrimary:
                is_primary = " [PRIMARY]"
        except:
            pass

        sets[set_name].append((opt.Id.IntegerValue, opt.Name, is_primary))

    for set_name, opts in sorted(sets.items()):
        print("=== {{}} ===".format(set_name))
        for oid, oname, primary in opts:
            print("  ID: {{}} | {{}}{{}}".format(oid, oname, primary))

    print("\\nTotal: {{}} set(s), {{}} option(s)".format(
        len(sets), sum(len(v) for v in sets.values())))
""",
            output_description="Design option sets and their options.",
        )
    )
