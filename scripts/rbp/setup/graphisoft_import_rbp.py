# -*- coding: utf-8 -*-
"""
RBP task script -- Byggstyrning Graphisoft-style IFC import (main model).

BatchRvt opens a small seed .RVT so Revit starts with a valid document.
This script loads ByggstyrningIFCImporter via clr, calls ImportRunner.Run(uiapp),
which reads BYGG_IFC_* env vars and performs OpenIFCDocument + CorrectIFCImport.

Environment (set by Run-ByggPipelineSetup.ps1 / Invoke-RBPGraphisoftImport or manually):

  Required:
    BYGG_IFC_PATH           -- input .ifc
    BYGG_IFC_OUTPUT_PATH        -- output .rvt
    BYGG_IFC_IMPORTER_DLL   -- absolute path to ByggstyrningIFCImporter.dll

  Optional -- paths / Graphisoft:
    BYGG_IFC_RESULT_PATH        -- JSON written by importer (extended metrics)
    BYGG_IFC_LOG_PATH           -- append-only log
    BYGG_GRAPHISOFT_DIR     -- folder containing RevitConnectionManaged.dll
    BYGG_REVIT_YEAR         -- e.g. 2025 for default install/registry paths
    BYGG_GRAPHISOFT_REGISTRY_KEY -- full HKCU subkey for Graphisoft settings

  Optional -- Revit IFC open:
    BYGG_IFC_AUTO_JOIN          -- 1/true -> IFCImportOptions.AutoJoin
    BYGG_IFC_CORRECT_OFF_AXIS   -- 1/true -> AutocorrectOffAxisLines
    BYGG_IFC_IMPORT_ALL_PARAMS  -- 1/true -> pass IFC params to CorrectIFCImport (default on)

  Optional -- CorrectIFCImport (override HKCU when set):
    BYGG_IFC_REMOVE_DOOR_WINDOW_2D   -- 1/true -> remove 2D door/window
    BYGG_IFC_TRUE_NORTH_FROM_GEOM    -- 1/true -> true north from geometry

  Optional -- diagnostics:
    BYGG_IFC_VERBOSE            -- 1/true -> log Graphisoft import/export step IDs

  RBP:
    RBP_SIDECAR_PATH         -- optional JSON sidecar for the launcher

Launcher: Run-ByggPipelineSetup.ps1 (Phase 1a).
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

# ---------------------------------------------------------------------------
# ByggstyrningIFCImporter (same assembly as ribbon command)
# ---------------------------------------------------------------------------
_dll = os.environ.get("BYGG_IFC_IMPORTER_DLL", "").strip()
if not _dll or not os.path.isfile(_dll):
    _msg = "BYGG_IFC_IMPORTER_DLL must point to ByggstyrningIFCImporter.dll (missing or not found)."
    _fail = {"step": "graphisoft_import", "error": _msg}
    print("RW_RESULT:" + json.dumps(_fail, ensure_ascii=True))
    sys.exit(1)

clr.AddReferenceToFileAndPath(_dll)
from Byggstyrning.IFCImporter import ImportRunner  # noqa: E402

# ---------------------------------------------------------------------------
# RBP boilerplate
# ---------------------------------------------------------------------------
uiapp = revit_script_util.GetUIApplication()
revit_file_path = revit_script_util.GetRevitFilePath() or ""

_sidecar_env = os.environ.get("RBP_SIDECAR_PATH", "").strip()
_model_basename = os.path.splitext(os.path.basename(revit_file_path))[0]
_model_dir = os.path.dirname(revit_file_path)
_sidecar_default = os.path.join(_model_dir, _model_basename + ".rbp_graphisoft_import.json")
_extra_sidecars = [p for p in [_sidecar_env, _sidecar_default] if p]

_result_path = os.environ.get("BYGG_IFC_RESULT_PATH", "").strip()


def _read_ifc_import_result():
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Output()
Output("=== Byggstyrning Graphisoft import (RBP) ===")
Output("Seed model: {}".format(revit_file_path))

rw = {
    "step": "graphisoft_import",
    "revit_result": None,
    "ifc_import_result": None,
    "error": None,
}

try:
    r = ImportRunner.Run(uiapp)
    rw["revit_result"] = int(r)
    if int(r) != 0:
        rw["error"] = "ImportRunner.Run returned {}".format(rw["revit_result"])
    rw["ifc_import_result"] = _read_ifc_import_result()

except Exception as exc:
    rw["error"] = str(exc)
    Output("FATAL: {}".format(traceback.format_exc()))
finally:
    _write_sidecar(rw)

Output("=== Byggstyrning Graphisoft import complete ===")
