# -*- coding: utf-8 -*-
"""
RBP task script -- Byggstyrning model setup.

BatchRvt has already opened the model (no --detach for this step so changes
are saved in place).  This script uses revit_script_util to access the
document, runs all setup steps via bygg_setup_core, writes the result to a
JSON sidecar, and prints the RW_RESULT line.

Launcher: Run-ByggPipelineSetup.ps1 (step 1 of 2).
"""

from __future__ import print_function

import json
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import SaveAsOptions, WorksharingSaveAsOptions

import revit_script_util
from revit_script_util import Output

# ---------------------------------------------------------------------------
# Repository root (scripts/rbp/... depth varies — walk to lib/ + settings.json)
# ---------------------------------------------------------------------------
try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.getcwd()

_d = _script_dir
_repo = None
for _ in range(24):
    if os.path.isfile(os.path.join(_d, "lib", "rbp_paths.py")):
        _repo = _d
        break
    _parent = os.path.dirname(_d)
    if _parent == _d:
        break
    _d = _parent
if not _repo:
    raise IOError("Could not find repository root (missing lib/rbp_paths.py).")
sys.path.insert(0, os.path.join(_repo, "lib"))
sys.path.insert(0, _repo)
from rbp_paths import repo_root_from_script  # noqa: E402

_ext_dir = repo_root_from_script(__file__)
_lib_dir = os.path.join(_ext_dir, "lib")
for _p in (_lib_dir, _ext_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Imports from shared lib (no pyrevit)
# ---------------------------------------------------------------------------
import bygg_setup_core  # noqa: E402
import utils           # noqa: E402

# ---------------------------------------------------------------------------
# RBP boilerplate
# ---------------------------------------------------------------------------
doc = revit_script_util.GetScriptDocument()
revit_file_path = revit_script_util.GetRevitFilePath() or ""

_sidecar_env = os.environ.get("RBP_SIDECAR_PATH", "").strip()
_model_basename = os.path.splitext(os.path.basename(revit_file_path))[0]
_model_dir = os.path.dirname(revit_file_path)
_sidecar_default = os.path.join(_model_dir, _model_basename + ".rbp_setup_result.json")

_extra_sidecars = [p for p in [_sidecar_env, _sidecar_default] if p]


def _write_sidecar(data):
    payload = json.dumps(data, ensure_ascii=True)
    for path in _extra_sidecars:
        try:
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with open(path, "w") as fh:
                fh.write(payload)
        except Exception as _e:
            Output("WARN: could not write sidecar {}: {}".format(path, _e))
    print("RW_RESULT:" + payload)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Output()
Output("=== Byggstyrning setup (RBP) ===")
Output("Model: {}".format(revit_file_path))

rw = {
    "step": "setup",
    "openings_deleted": 0,
    "worksharing_enabled": False,
    "struct_ws_created": False,
    "structural_moved": 0,
    "elements_rotated": 0,
    "true_north_set": False,
    "project_north_set": False,
    "config_linked": False,
    "model_saved": False,
    "setup_temp_saved_path": None,
    "save_error": None,
    "error": None,
}

try:
    settings = utils.load_settings()
    result = bygg_setup_core.run_full_setup(doc, settings)
    rw.update(result)

    Output(
        "NOTE: Worksharing here is a local workshared file (EnableWorksharing). "
        "It is NOT a Revit Server / BIM 360 Central model unless you Save As Central separately."
    )

    try:
        doc.Save()
        rw["model_saved"] = True
        Output("Model saved.")
    except Exception as save_exc:
        rw["save_error"] = str(save_exc)
        Output("WARN: save failed: {}".format(save_exc))
        try:
            rw["doc_pathname"] = str(doc.PathName or "")
            rw["doc_is_readonly"] = bool(doc.IsReadOnly)
        except Exception:
            pass
        # Same pattern as merge_rooms: OS lock on main path — SaveAs to temp; launcher copies over main.
        setup_fb = os.environ.get("BYGG_SETUP_SAVEAS_FALLBACK", "").strip()
        if setup_fb and not rw["model_saved"]:
            try:
                opt = SaveAsOptions()
                opt.OverwriteExistingFile = True
                # After EnableWorksharing, SaveAs to a new path requires this flag (not ACC-only).
                try:
                    if doc.IsWorkshared:
                        ws_opt = WorksharingSaveAsOptions()
                        ws_opt.SaveAsCentral = True
                        opt.SetWorksharingOptions(ws_opt)
                except Exception as _ws_exc:
                    Output("WARN: WorksharingSaveAsOptions: {}".format(_ws_exc))
                doc.SaveAs(setup_fb, opt)
                rw["model_saved"] = True
                rw["setup_temp_saved_path"] = setup_fb
                rw["save_error"] = None
                Output("Model SaveAs to temp fallback: {}".format(setup_fb))
            except Exception as fb_exc:
                rw["save_error"] = "{} | TempSaveAs: {}".format(rw["save_error"], fb_exc)
                Output("WARN: temp SaveAs failed: {}".format(fb_exc))

except Exception as exc:
    rw["error"] = str(exc)
    Output("FATAL: {}".format(traceback.format_exc()))
finally:
    _write_sidecar(rw)

Output("=== Byggstyrning setup complete ===")
