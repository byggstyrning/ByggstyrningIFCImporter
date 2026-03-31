# -*- coding: utf-8 -*-
"""
RBP task script -- Byggstyrning rooms merge.

BatchRvt has opened the MAIN model (0001_00.RVT).  This script opens the
ROOMS model (0003_00.RVT) via app.OpenDocumentFile, rotates it to match true
north, then copies rooms + room separation lines into the main model with
Transform.Identity,
closes the rooms model, and saves the main model.

Environment variables (set by Run-ByggPipelineSetup.ps1):
    ROOMS_MODEL_PATH        -- absolute path to the rooms .RVT file
    BYGG_MERGE_SAVEAS_PATH -- optional; if Document.Save fails (or no PathName),
                               merge_rooms_core retries SaveAs to this path (overwrite).
                               Launcher sets this to the main model path when running the full pipeline.
    RBP_SIDECAR_PATH        -- optional explicit sidecar path

Launcher: Run-ByggPipelineSetup.ps1 (step 2 of 2).
"""

from __future__ import print_function

import json
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")

import revit_script_util
from revit_script_util import Output

# ---------------------------------------------------------------------------
# Repository root
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

import merge_rooms_core  # noqa: E402
import utils             # noqa: E402

# ---------------------------------------------------------------------------
# RBP boilerplate
# ---------------------------------------------------------------------------
doc = revit_script_util.GetScriptDocument()
uiapp = revit_script_util.GetUIApplication()
app = uiapp.Application
revit_file_path = revit_script_util.GetRevitFilePath() or ""

rooms_model_path = os.environ.get("ROOMS_MODEL_PATH", "").strip()

_sidecar_env = os.environ.get("RBP_SIDECAR_PATH", "").strip()
_model_basename = os.path.splitext(os.path.basename(revit_file_path))[0]
_model_dir = os.path.dirname(revit_file_path)
_sidecar_default = os.path.join(_model_dir, _model_basename + ".rbp_rooms_result.json")
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
Output("=== Byggstyrning rooms merge (RBP) ===")
Output("Main model: {}".format(revit_file_path))
Output("Rooms model: {}".format(rooms_model_path))

rw = {
    "step": "merge_rooms",
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
}

try:
    if not rooms_model_path:
        raise RuntimeError("ROOMS_MODEL_PATH environment variable is not set.")

    settings = utils.load_settings()
    result = merge_rooms_core.merge_rooms_from_model(
        doc, rooms_model_path, app, settings
    )
    rw.update(result)

    Output(
        "Copy to main: rooms_copied={}, room_separation_lines_copied={}, "
        "room_boundary_lines_copied={}.".format(
            rw.get("rooms_copied", 0),
            rw.get("lines_copied", 0),
            rw.get("room_boundary_lines_copied", 0),
        ))

except Exception as exc:
    rw["error"] = str(exc)
    Output("FATAL: {}".format(traceback.format_exc()))
finally:
    _write_sidecar(rw)

Output("=== Byggstyrning rooms merge complete ===")
