# -*- coding: utf-8 -*-
"""
Shared setup logic for the Byggstyrning IFC-to-Revit pipeline.

No pyrevit imports at module level -- safe to import from both pyRevit GUI
scripts and Revit Batch Processor (RBP) task scripts.
"""

from __future__ import print_function

import math
import os

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementTransformUtils,
    ElementId,
    FilteredElementCollector,
    FilteredWorksetCollector,
    Line,
    ModelPathUtils,
    ProjectPosition,
    RevitLinkInstance,
    RevitLinkOptions,
    RevitLinkType,
    Transaction,
    ViewPlan,
    Workset,
    WorksetKind,
    XYZ,
)
from System.Collections.Generic import List


# ---------------------------------------------------------------------------
# Simple logger compatible with both hosts
# ---------------------------------------------------------------------------

class _StdoutLogger(object):
    def info(self, msg):
        print("[INFO] " + str(msg))

    def warning(self, msg):
        print("[WARN] " + str(msg))

    def error(self, msg):
        print("[ERROR] " + str(msg))

    def debug(self, msg):
        print("[DEBUG] " + str(msg))


def _default_log():
    return _StdoutLogger()


# ---------------------------------------------------------------------------
# View helpers (no uidoc)
# ---------------------------------------------------------------------------

def get_first_floor_plan(doc):
    """Return the first ViewPlan whose name contains 'first floor' (case-insensitive)."""
    for view in FilteredElementCollector(doc).OfClass(ViewPlan):
        if "first floor" in view.Name.lower():
            return view
    return None


# ---------------------------------------------------------------------------
# Step 1: Purge IFC openings
# ---------------------------------------------------------------------------

def purge_ifc_openings(doc, log=None):
    """Delete all elements where 'Export to IFC As' == 'IfcOpeningElement'.

    Returns:
        int: number of elements deleted.
    """
    if log is None:
        log = _default_log()

    openings = []
    for elem in FilteredElementCollector(doc).WhereElementIsNotElementType():
        param = elem.LookupParameter("Export to IFC As")
        if param and param.AsString() == "IfcOpeningElement":
            openings.append(elem.Id)

    if not openings:
        log.info("No IFC opening elements found.")
        return 0

    t = Transaction(doc, "Purge IFC Openings")
    t.Start()
    try:
        for eid in openings:
            doc.Delete(eid)
        t.Commit()
        log.info("Deleted {} IFC opening elements.".format(len(openings)))
        return len(openings)
    except Exception as exc:
        t.RollBack()
        log.error("Failed to delete IFC openings: {}".format(exc))
        return 0


# ---------------------------------------------------------------------------
# Step 2: Enable worksharing and create worksets
# ---------------------------------------------------------------------------

def setup_worksets(doc, settings, log=None):
    """Enable worksharing (if needed) and create architectural / structural worksets.

    Args:
        doc: Revit Document
        settings: dict loaded from settings.json
        log: logger

    Returns:
        tuple(WorksetId or None, str): (structural_workset_id, structural_workset_name)
    """
    if log is None:
        log = _default_log()

    arch_name = settings["workset_names"]["architectural"]
    struct_name = settings["workset_names"]["structural"]

    struct_ws_id = None

    try:
        if not doc.IsWorkshared:
            log.info("Enabling worksharing with Workset1 -> '{}'.".format(arch_name))
            doc.EnableWorksharing("Shared Levels and Grids", arch_name)

        # Check whether structural workset already exists
        for ws in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset):
            if ws.Name == struct_name:
                struct_ws_id = ws.Id
                log.info("Structural workset '{}' already exists.".format(struct_name))
                break

        if struct_ws_id is None:
            t = Transaction(doc, "Create Structural Workset")
            t.Start()
            try:
                struct_ws = Workset.Create(doc, struct_name)
                struct_ws_id = struct_ws.Id
                t.Commit()
                log.info("Created workset '{}'.".format(struct_name))
            except Exception as exc:
                t.RollBack()
                raise exc

    except Exception as exc:
        log.error("Workset setup failed: {}".format(exc))
        return None, struct_name

    return struct_ws_id, struct_name


# ---------------------------------------------------------------------------
# Step 3: Move structural elements to structural workset
# ---------------------------------------------------------------------------

def move_structural_elements(doc, struct_ws_id, log=None):
    """Move elements with 'BIP.Structural building part' = 1/'yes' to the structural workset.

    Returns:
        int: number of elements moved.
    """
    if log is None:
        log = _default_log()

    if struct_ws_id is None:
        log.warning("No structural workset ID -- skipping move.")
        return 0

    structural = []
    for elem in FilteredElementCollector(doc).WhereElementIsNotElementType():
        param_bip = elem.LookupParameter("BIP.Structural building part")
        if param_bip:
            if hasattr(param_bip, "AsInteger") and param_bip.AsInteger() == 1:
                structural.append(elem)
                continue
            if (hasattr(param_bip, "AsString") and param_bip.AsString()
                    and param_bip.AsString().strip().lower() == "yes"):
                structural.append(elem)
                continue

        # Fall back to type parameter
        if hasattr(elem, "GetTypeId"):
            type_elem = doc.GetElement(elem.GetTypeId())
            if type_elem:
                tp = type_elem.LookupParameter("BIP.Structural building part")
                if tp and tp.AsString() and tp.AsString().strip().lower() == "yes":
                    structural.append(elem)

    if not structural:
        log.info("No structural elements found.")
        return 0

    t = Transaction(doc, "Move Structural Elements to Workset")
    t.Start()
    try:
        count = 0
        for elem in structural:
            param = elem.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
            if param and not param.IsReadOnly:
                param.Set(struct_ws_id.IntegerValue)
                count += 1
        t.Commit()
        log.info("Moved {} structural elements.".format(count))
        return count
    except Exception as exc:
        t.RollBack()
        log.error("Failed to move structural elements: {}".format(exc))
        return 0


# ---------------------------------------------------------------------------
# Step 4: Rotate model elements from internal origin
# ---------------------------------------------------------------------------

_ROTATABLE_TYPES = frozenset([
    "DirectShape", "FamilyInstance", "DetailLine", "DetailArc",
    "TextNote", "AnnotationSymbol", "ReferencePlane",
    # Spatial (rooms IFC / xBIM rooms model — same angle as model geometry)
    "Room", "Space", "RoomSeparationLine",
])

# Rotated even when Location is unset (e.g. unplaced room); still participates in RotateElements.
_SPATIAL_ROTATABLE_TYPES = frozenset(["Room", "Space", "RoomSeparationLine"])


def collect_room_boundary_line_ids(doc):
    """Sketch lines from Document.Create.NewRoomBoundaryLines (category OST_RoomBoundaryLines)."""
    rbc = getattr(BuiltInCategory, "OST_RoomBoundaryLines", None)
    if rbc is None:
        return []
    try:
        return list(
            FilteredElementCollector(doc)
            .OfCategory(rbc)
            .WhereElementIsNotElementType()
            .ToElementIds()
        )
    except Exception:
        return []


def collect_room_separation_line_ids(doc):
    """Room separation lines (category OST_RoomSeparationLines).

    Do not rely on ``type(elem).__name__ == 'RoomSeparationLine'`` in IronPython —
    Revit often exposes these as ``CurveElement`` / ``ModelCurve``, so the name-based
    filter never matched and separation lines were skipped by setup/merge rotation.
    """
    try:
        return list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_RoomSeparationLines)
            .WhereElementIsNotElementType()
            .ToElementIds()
        )
    except Exception:
        return []


def rotate_elements_from_origin(doc, settings, log=None):
    """Rotate all rotatable model elements around the internal origin (Z axis).

    Angle is taken from settings['default_paths']['default_true_north_angle'] (degrees).

    Includes architectural Room, MEP Space, room separation lines, and **room boundary**
    sketch lines (``NewRoomBoundaryLines`` / ``OST_RoomBoundaryLines``) so the rooms
    model stays aligned with geometry when merge copies rooms into the main model.

    Returns:
        int: number of elements rotated (0 if none found or error).
    """
    if log is None:
        log = _default_log()

    angle_deg = settings["default_paths"]["default_true_north_angle"]
    angle_rad = math.radians(angle_deg)

    rotatable = []
    seen = set()
    for elem in FilteredElementCollector(doc).WhereElementIsNotElementType():
        tn = type(elem).__name__
        if tn not in _ROTATABLE_TYPES:
            continue
        if tn in _SPATIAL_ROTATABLE_TYPES:
            eid = elem.Id
            if eid.IntegerValue not in seen:
                seen.add(eid.IntegerValue)
                rotatable.append(eid)
        elif hasattr(elem, "Location") and elem.Location:
            eid = elem.Id
            if eid.IntegerValue not in seen:
                seen.add(eid.IntegerValue)
                rotatable.append(eid)

    for eid in collect_room_separation_line_ids(doc):
        if eid.IntegerValue not in seen:
            seen.add(eid.IntegerValue)
            rotatable.append(eid)

    for eid in collect_room_boundary_line_ids(doc):
        if eid.IntegerValue not in seen:
            seen.add(eid.IntegerValue)
            rotatable.append(eid)

    if not rotatable:
        log.warning("No rotatable elements found.")
        return 0

    origin = XYZ(0, 0, 0)
    axis = Line.CreateBound(origin, XYZ(0, 0, 1))

    net_ids = List[ElementId](rotatable)

    t = Transaction(doc, "Rotate Elements from Origin")
    t.Start()
    try:
        ElementTransformUtils.RotateElements(doc, net_ids, axis, angle_rad)
        t.Commit()
        log.info("Rotated {} elements by {:.4f} deg.".format(len(rotatable), angle_deg))
        return len(rotatable)
    except Exception as exc:
        t.RollBack()
        log.error("Failed to rotate elements: {}".format(exc))
        return 0


# ---------------------------------------------------------------------------
# Step 5a: Set True North (ProjectPosition angle = 0)
# ---------------------------------------------------------------------------

def set_true_north(doc, log=None):
    """Set the project's True North angle to 0 and set First Floor plan to True North orientation.

    Returns:
        bool
    """
    if log is None:
        log = _default_log()

    first_floor = get_first_floor_plan(doc)
    if not first_floor:
        log.warning("First Floor plan not found; skipping True North setup.")
        return False

    t = Transaction(doc, "Set True North")
    t.Start()
    try:
        param = first_floor.get_Parameter(BuiltInParameter.PLAN_VIEW_NORTH)
        if param:
            param.Set(1)  # 1 = True North

        project_location = doc.ActiveProjectLocation
        origin = XYZ(0, 0, 0)
        cur = project_location.GetProjectPosition(origin)
        new_pos = ProjectPosition(cur.EastWest, cur.NorthSouth, cur.Elevation, 0.0)
        project_location.SetProjectPosition(origin, new_pos)

        t.Commit()
        log.info("True North set to 0 degrees.")
        return True
    except Exception as exc:
        t.RollBack()
        log.error("Failed to set True North: {}".format(exc))
        return False


# ---------------------------------------------------------------------------
# Step 5b: Set view to Project North
# ---------------------------------------------------------------------------

def set_view_to_project_north(doc, log=None):
    """Set First Floor plan view orientation to Project North.

    Returns:
        bool
    """
    if log is None:
        log = _default_log()

    first_floor = get_first_floor_plan(doc)
    if not first_floor:
        log.warning("First Floor plan not found; skipping Project North setup.")
        return False

    t = Transaction(doc, "Set View to Project North")
    t.Start()
    try:
        param = first_floor.get_Parameter(BuiltInParameter.PLAN_VIEW_NORTH)
        if param:
            param.Set(0)  # 0 = Project North
        t.Commit()
        log.info("First Floor view set to Project North.")
        return True
    except Exception as exc:
        t.RollBack()
        log.error("Failed to set Project North: {}".format(exc))
        return False


# ---------------------------------------------------------------------------
# Step 6: Link Config RVT and acquire coordinates
# ---------------------------------------------------------------------------

def link_config_and_acquire_coords(doc, settings, log=None):
    """Link the coordination config template RVT (from settings) and acquire coordinates.

    Returns:
        bool
    """
    if log is None:
        log = _default_log()

    config_dir = settings["default_paths"]["config_path"]
    template_name = settings["default_paths"].get(
        "config_template_filename", "Coordination Revit Template file.rvt"
    )
    config_path = os.path.join(config_dir, template_name)

    if not os.path.exists(config_path):
        log.error("Config file not found: {}".format(config_path))
        return False

    t = Transaction(doc, "Link Config and Acquire Coordinates")
    t.Start()
    try:
        link_opts = RevitLinkOptions(False)
        model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(config_path)
        link_type = RevitLinkType.Create(doc, model_path, link_opts)
        link_instance = RevitLinkInstance.Create(doc, link_type.ElementId)
        doc.AcquireCoordinates(link_instance.Id)
        t.Commit()
        log.info("Config linked and coordinates acquired.")
        return True
    except Exception as exc:
        t.RollBack()
        log.error("Failed to link config: {}".format(exc))
        return False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_full_setup(doc, settings, log=None):
    """Run all setup steps in order.

    Args:
        doc: Revit Document
        settings: dict (from settings.json)
        log: logger

    Returns:
        dict with step results, suitable for JSON serialisation.
    """
    if log is None:
        log = _default_log()

    result = {
        "openings_deleted": 0,
        "worksharing_enabled": False,
        "struct_ws_created": False,
        "structural_moved": 0,
        "elements_rotated": 0,
        "true_north_set": False,
        "project_north_set": False,
        "config_linked": False,
        "error": None,
    }

    try:
        log.info("=== Step 1: Purge IFC openings ===")
        result["openings_deleted"] = purge_ifc_openings(doc, log)

        log.info("=== Step 2: Setup worksets ===")
        struct_ws_id, struct_ws_name = setup_worksets(doc, settings, log)
        result["worksharing_enabled"] = doc.IsWorkshared
        result["struct_ws_created"] = struct_ws_id is not None

        log.info("=== Step 3: Move structural elements ===")
        result["structural_moved"] = move_structural_elements(doc, struct_ws_id, log)

        log.info("=== Step 4: Rotate elements from origin ===")
        result["elements_rotated"] = rotate_elements_from_origin(doc, settings, log)

        log.info("=== Step 5a: Set True North ===")
        result["true_north_set"] = set_true_north(doc, log)

        log.info("=== Step 5b: Set view to Project North ===")
        result["project_north_set"] = set_view_to_project_north(doc, log)

        log.info("=== Step 6: Link config and acquire coords ===")
        result["config_linked"] = link_config_and_acquire_coords(doc, settings, log)

        log.info("=== Setup complete ===")

    except Exception as exc:
        result["error"] = str(exc)
        log.error("Unhandled error in run_full_setup: {}".format(exc))

    return result
