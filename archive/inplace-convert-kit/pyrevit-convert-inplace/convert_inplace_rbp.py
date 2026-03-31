# -*- coding: utf-8 -*-
"""
RBP task script -- Convert all in-place Generic Models to loadable families.

Archived (2026-03): Legacy IFC content no longer uses in-place families; Run-ByggPipelineSetup.ps1
does not invoke this task. Kept next to script.py for reference. To run again, copy this file
to scripts/rbp/convert_inplace/ and wire the launcher (or run BatchRvt manually).

BatchRvt has opened the main model.  This script calls
inplace_to_loadable_floor.batch_convert_all_inplace with an Output()-based
progress callback instead of pyrevit's ProgressBar.
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
_revit_lib = os.path.join(_lib_dir, "revit")
for _p in (_revit_lib, _lib_dir, _ext_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import inplace_to_loadable_floor  # noqa: E402

# ---------------------------------------------------------------------------
# RBP boilerplate
# ---------------------------------------------------------------------------
doc = revit_script_util.GetScriptDocument()
uiapp = revit_script_util.GetUIApplication()
app = uiapp.Application
revit_file_path = revit_script_util.GetRevitFilePath() or ""

_sidecar_env = os.environ.get("RBP_SIDECAR_PATH", "").strip()
_model_basename = os.path.splitext(os.path.basename(revit_file_path))[0]
_model_dir = os.path.dirname(revit_file_path)
_sidecar_default = os.path.join(_model_dir, _model_basename + ".rbp_convert_result.json")
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
# Progress callback for RBP (uses Output() instead of ProgressBar)
# ---------------------------------------------------------------------------
_progress_state = {"last_pct": -1}


def _rbp_progress(current, total):
    if total > 0:
        pct = int(100.0 * current / total)
        if pct != _progress_state["last_pct"] and pct % 10 == 0:
            Output("Progress: {}/{} ({}%)".format(current + 1, total, pct))
            _progress_state["last_pct"] = pct


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Output()
Output("=== Byggstyrning convert in-place (RBP) ===")
Output("Model: {}".format(revit_file_path))

rw = {
    "step": "convert_inplace",
    "converted": 0,
    "skipped": 0,
    "errors": 0,
    "model_saved": False,
    "error": None,
}

try:
    stats = inplace_to_loadable_floor.batch_convert_all_inplace(
        doc, app, _script_dir,
        progress_callback=_rbp_progress,
    )
    # batch_convert_all_inplace returns a dict or None
    if isinstance(stats, dict):
        rw["converted"] = stats.get("converted", 0)
        rw["skipped"] = stats.get("skipped", 0)
        rw["errors"] = stats.get("errors", 0)
    Output("Conversion complete.")

    try:
        doc.Save()
        rw["model_saved"] = True
        Output("Model saved.")
    except Exception as save_exc:
        Output("WARN: save failed: {}".format(save_exc))

except Exception as exc:
    rw["error"] = str(exc)
    Output("FATAL: {}".format(traceback.format_exc()))
finally:
    _write_sidecar(rw)

Output("=== Byggstyrning convert in-place complete ===")
