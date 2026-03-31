# -*- coding: utf-8 -*-
"""
Shared rooms-merge logic for the Byggstyrning IFC-to-Revit pipeline (RBP).

Opens the rooms source RVT, rotates the rooms document (same true north angle
as main setup), then copies rooms, separation lines, and room boundary sketch
lines (``NewRoomBoundaryLines``) into the target model with
ElementTransformUtils.CopyElements (identity transform when coordinates already
align). Requires native Room/MEP Space elements (or separation/boundary lines)
in the rooms file.

No pyrevit imports at module level.
"""

from __future__ import print_function

import os

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    CopyPasteOptions,
    ElementId,
    ElementTransformUtils,
    FilteredElementCollector,
    ModelPathUtils,
    OpenOptions,
    SaveAsOptions,
    WorksharingSaveAsOptions,
    Transform,
    Transaction,
    TransactWithCentralOptions,
    ViewPlan,
    WorksharingUtils,
    XYZ,
)
from System.Collections.Generic import List


# ---------------------------------------------------------------------------
# Simple stdout logger
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


def collect_all_rooms_and_lines(doc):
    """Return room/space IDs, room separation line IDs, room boundary sketch line IDs.

    IFC-imported IfcSpace often lands as MEP Space, not architectural Room.
    Room boundary lines come from ``NewRoomBoundaryLines`` (``OST_RoomBoundaryLines``).
    """
    import bygg_setup_core  # noqa: E402

    room_ids = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Rooms)
        .WhereElementIsNotElementType()
        .ToElementIds()
    )
    space_ids = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_MEPSpaces)
        .WhereElementIsNotElementType()
        .ToElementIds()
    )
    line_ids = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_RoomSeparationLines)
        .WhereElementIsNotElementType()
        .ToElementIds()
    )
    boundary_ids = bygg_setup_core.collect_room_boundary_line_ids(doc)
    combined = room_ids + space_ids
    return combined, line_ids, boundary_ids


# ---------------------------------------------------------------------------
# Cross-document copy (RBP)
# ---------------------------------------------------------------------------

def copy_rooms_between_docs(source_doc, target_doc, settings, log=None):
    """Copy rooms, separation lines, and room boundary sketch lines (``NewRoomBoundaryLines``).

    Elements are copied with Transform.Identity -- they must already be in
    correct project coordinates (i.e. the source model has been opened
    without detach and has the same shared coordinate system).

    Returns:
        dict with 'rooms_copied', 'lines_copied', 'room_boundary_lines_copied', 'error'.
    """
    if log is None:
        log = _default_log()

    result = {
        "rooms_copied": 0,
        "lines_copied": 0,
        "room_boundary_lines_copied": 0,
        "error": None,
    }

    spatial_ids, line_ids, boundary_ids = collect_all_rooms_and_lines(source_doc)
    all_source_ids = List[ElementId](spatial_ids + line_ids + boundary_ids)

    if all_source_ids.Count == 0:
        log.warning(
            "No rooms, MEP spaces, separation lines, or room boundary lines in source."
        )
        result["error"] = "No rooms or spaces found in source"
        return result

    log.info(
        "Copying {} room/space + {} separation lines + {} room boundary lines from source.".format(
            len(spatial_ids), len(line_ids), len(boundary_ids)
        )
    )

    opts = CopyPasteOptions()

    t = Transaction(target_doc, "Copy rooms from rooms IFC model")
    t.Start()
    try:
        copied = ElementTransformUtils.CopyElements(
            source_doc,
            all_source_ids,
            target_doc,
            Transform.Identity,
            opts,
        )
        t.Commit()
        copied_list = list(copied)
        result["rooms_copied"] = len(spatial_ids)
        result["lines_copied"] = len(line_ids)
        result["room_boundary_lines_copied"] = len(boundary_ids)
        log.info("Copy complete: {} new elements.".format(len(copied_list)))
    except Exception as exc:
        t.RollBack()
        result["error"] = str(exc)
        log.error("CopyElements failed: {}".format(exc))

    return result


def _persist_target_doc(target_doc, log, result):
    """Save main document; set result keys target_saved, save_error, diagnostics."""
    result["save_error"] = None
    result["save_used_fallback"] = False
    try:
        pn = target_doc.PathName
        result["target_path_name"] = str(pn) if pn else ""
    except Exception:
        result["target_path_name"] = ""
    try:
        result["target_doc_readonly"] = target_doc.IsReadOnly
    except Exception:
        result["target_doc_readonly"] = None
    try:
        result["target_doc_workshared"] = target_doc.IsWorkshared
    except Exception:
        result["target_doc_workshared"] = None

    log.info(
        "Target doc before persist: path='{}', IsReadOnly={}, IsWorkshared={}".format(
            result.get("target_path_name"),
            result.get("target_doc_readonly"),
            result.get("target_doc_workshared"),
        )
    )

    merge_saveas = os.environ.get("BYGG_MERGE_SAVEAS_PATH", "").strip()

    def _saveas_opts():
        opt = SaveAsOptions()
        opt.OverwriteExistingFile = True
        try:
            if target_doc.IsWorkshared:
                ws_opt = WorksharingSaveAsOptions()
                ws_opt.SaveAsCentral = True
                opt.SetWorksharingOptions(ws_opt)
        except Exception:
            pass
        return opt

    def _try_saveas(path):
        target_doc.SaveAs(path, _saveas_opts())
        result["target_saved"] = True
        result["save_used_fallback"] = True
        result["save_error"] = None
        log.info("Target model SaveAs succeeded: {}".format(path))

    # No saved path yet (in-memory only) — SaveAs if env provides explicit path
    if not result.get("target_path_name") and merge_saveas:
        try:
            _try_saveas(merge_saveas)
            return
        except Exception as exc:
            result["save_error"] = str(exc)
            log.warning("SaveAs failed (no PathName): {}".format(exc))
            # Fall through: temp-file fallback may still work
    elif result.get("target_path_name"):
        try:
            target_doc.Save()
            result["target_saved"] = True
            log.info("Target model saved.")
        except Exception as save_exc:
            result["save_error"] = str(save_exc)
            log.warning("Could not save target: {}".format(save_exc))
            if merge_saveas:
                try:
                    _try_saveas(merge_saveas)
                except Exception as saveas_exc:
                    result["save_error"] = "{} | SaveAs: {}".format(save_exc, saveas_exc)
                    log.warning("SaveAs also failed: {}".format(saveas_exc))

    # Last resort: SaveAs to a unique temp path (avoids OS/Revit lock on the main path).
    merge_fb = os.environ.get("BYGG_MERGE_SAVEAS_FALLBACK", "").strip()
    if not result.get("target_saved") and merge_fb:
        try:
            target_doc.SaveAs(merge_fb, _saveas_opts())
            result["target_saved"] = True
            result["save_error"] = None
            result["merge_temp_saved_path"] = merge_fb
            result["save_used_fallback"] = True
            log.info("Target model SaveAs to temp fallback: {}".format(merge_fb))
        except Exception as exc:
            if result.get("save_error"):
                result["save_error"] = "{} | TempSaveAs: {}".format(
                    result["save_error"], exc
                )
            else:
                result["save_error"] = str(exc)
            log.warning("Temp SaveAs fallback failed: {}".format(exc))


def merge_rooms_from_model(target_doc, rooms_model_path, app, settings, log=None):
    """Full pipeline: open rooms RVT, copy rooms to target, close source, save target.

    This is the RBP entry point.

    Args:
        target_doc: main Revit Document (already open via BatchRvt)
        rooms_model_path: str -- absolute path to the rooms .RVT file
        app: Autodesk.Revit.ApplicationServices.Application
        settings: dict from settings.json
        log: logger

    Returns:
        dict suitable for JSON serialisation / RW_RESULT.
    """
    if log is None:
        log = _default_log()

    result = {
        "rooms_model_opened": False,
        "rooms_copied": 0,
        "lines_copied": 0,
        "room_boundary_lines_copied": 0,
        "target_saved": False,
        "merge_temp_saved_path": None,
        "save_error": None,
        "save_used_fallback": False,
        "target_path_name": "",
        "target_doc_readonly": None,
        "target_doc_workshared": None,
        "error": None,
        "rooms_model_elements_rotated": None,
    }

    if not rooms_model_path or not os.path.exists(rooms_model_path):
        result["error"] = "Rooms model not found: {}".format(rooms_model_path)
        log.error(result["error"])
        return result

    source_doc = None
    try:
        log.info("Opening rooms model: {}".format(rooms_model_path))
        open_opts = OpenOptions()
        open_opts.DetachFromCentralOption = (
            # Import from Autodesk.Revit.DB
            __import__(
                "Autodesk.Revit.DB",
                fromlist=["DetachFromCentralOption"]
            ).DetachFromCentralOption.DoNotDetach
        )
        rooms_model = ModelPathUtils.ConvertUserVisiblePathToModelPath(
            rooms_model_path
        )
        source_doc = app.OpenDocumentFile(rooms_model, open_opts)
        result["rooms_model_opened"] = True

        spatial_ids, line_ids, boundary_ids = collect_all_rooms_and_lines(source_doc)
        has_native = len(spatial_ids) + len(line_ids) + len(boundary_ids) > 0

        if not has_native:
            result["error"] = "No rooms or spaces found in source"
        else:
            # Same true-north angle as main setup (geometry + Room/Space/separation lines).
            import bygg_setup_core  # noqa: E402

            nrot = bygg_setup_core.rotate_elements_from_origin(
                source_doc, settings, log
            )
            result["rooms_model_elements_rotated"] = nrot
            log.info(
                "Rooms model: rotated {} elements (includes rooms/spaces/lines).".format(
                    nrot
                )
            )

        if result["error"] is None:
            copy_result = copy_rooms_between_docs(
                source_doc, target_doc, settings, log
            )
            result["rooms_copied"] = copy_result["rooms_copied"]
            result["lines_copied"] = copy_result["lines_copied"]
            result["room_boundary_lines_copied"] = copy_result.get(
                "room_boundary_lines_copied", 0
            )
            if copy_result["error"]:
                result["error"] = copy_result["error"]

    except Exception as exc:
        result["error"] = str(exc)
        log.error("merge_rooms_from_model failed: {}".format(exc))
    finally:
        if source_doc is not None:
            try:
                source_doc.Close(False)
                log.info("Rooms model closed.")
            except Exception as close_exc:
                log.warning("Could not close rooms model: {}".format(close_exc))

    # Save target model so next RBP run sees updated state
    if result["error"] is None:
        _persist_target_doc(target_doc, log, result)

    return result
