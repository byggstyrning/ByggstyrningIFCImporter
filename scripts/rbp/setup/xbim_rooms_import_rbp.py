# -*- coding: utf-8 -*-
"""
RBP task script -- Byggstyrning xBIM rooms IFC import (no Graphisoft).

BatchRvt opens a seed .RVT; this script loads ByggstyrningRoomImporter via clr and calls
RoomImportRunner.Run(uiapp), which reads BYGG_* env vars and creates native
Revit rooms from IfcSpace data in the IFC.

Environment (set by Run-ByggPipelineSetup.ps1 / Invoke-RBPXbimRoomsImport):
    BYGG_IFC_PATH, BYGG_IFC_OUTPUT_PATH, BYGG_IFC_RESULT_PATH, BYGG_IFC_LOG_PATH
    BYGG_XBIM_ROOMS_DLL -- absolute path to ByggstyrningRoomImporter.dll (folder must
        contain xBIM dependency DLLs from the same build output)
    BYGG_RBP_SEED_RVT -- absolute path to the seed .rvt (BatchRvt file list);
        RoomImportRunner uses this to pick the open Document when ActiveUIDocument is null

Launcher: Run-ByggPipelineSetup.ps1 (-RoomsImporter Xbim, or -ImportRoomsIfcOnly with Xbim).
"""

from __future__ import print_function

import json
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import revit_script_util
from revit_script_util import Output

_dll = os.environ.get("BYGG_XBIM_ROOMS_DLL", "").strip()
if not _dll or not os.path.isfile(_dll):
    _msg = "BYGG_XBIM_ROOMS_DLL must point to ByggstyrningRoomImporter.dll (missing or not found)."
    _fail = {"step": "xbim_rooms_import", "error": _msg}
    print("RW_RESULT:" + json.dumps(_fail, ensure_ascii=True))
    sys.exit(1)

clr.AddReferenceToFileAndPath(_dll)
from Byggstyrning.RoomImporter import RoomImportRunner  # noqa: E402

uiapp = revit_script_util.GetUIApplication()
revit_file_path = revit_script_util.GetRevitFilePath() or ""

_sidecar_env = os.environ.get("RBP_SIDECAR_PATH", "").strip()
_model_basename = os.path.splitext(os.path.basename(revit_file_path))[0]
_model_dir = os.path.dirname(revit_file_path)
_sidecar_default = os.path.join(_model_dir, _model_basename + ".rbp_xbim_rooms.json")
_extra_sidecars = [p for p in [_sidecar_env, _sidecar_default] if p]

_result_path = os.environ.get("BYGG_IFC_RESULT_PATH", "").strip()


def _read_rooms_result():
    if not _result_path or not os.path.isfile(_result_path):
        return None
    try:
        with open(_result_path, "r") as fh:
            return json.load(fh)
    except Exception:
        return None


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


Output()
Output("=== Byggstyrning xBIM rooms import (RBP) ===")
Output("Seed model: {}".format(revit_file_path))

rw = {
    "step": "xbim_rooms_import",
    "revit_result": None,
    "rooms_import_result": None,
    "error": None,
}

try:
    r = RoomImportRunner.Run(uiapp)
    rw["revit_result"] = int(r)
    if int(r) != 0:
        rw["error"] = "RoomImportRunner.Run returned {}".format(rw["revit_result"])
    rw["rooms_import_result"] = _read_rooms_result()

except Exception as exc:
    rw["error"] = str(exc)
    Output("FATAL: {}".format(traceback.format_exc()))
finally:
    _write_sidecar(rw)

Output("=== Byggstyrning xBIM rooms import complete ===")
