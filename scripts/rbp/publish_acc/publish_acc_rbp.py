# -*- coding: utf-8 -*-
"""
RBP task script -- Publish workshared local model to ACC (Autodesk Docs / BIM 360).

Calls Document.SaveAsCloudModel(accountId, projectId, folderId, modelName).
Requires the user to be signed in to Autodesk in Revit.

Revit API: a *workshared* local document becomes a *workshared cloud model*; a non-workshared
document becomes a non-workshared cloud model. This script ensures worksharing (same logic as
setup_model_rbp / bygg_setup_core.setup_worksets) when the document is still non-workshared,
then saves before SaveAsCloudModel.

Launcher: Run-ByggPipelineSetup.ps1 (optional Phase 3 when -PublishAcc).

Environment (set by launcher):
  BYGG_ACC_ACCOUNT_GUID  -- hub account Guid string (b. prefix stripped in PS)
  BYGG_ACC_PROJECT_GUID -- project Guid string
  BYGG_ACC_FOLDER_ID     -- Data Management folder id string
  BYGG_CLOUD_MODEL_NAME -- target .rvt file name in cloud (e.g. base.ifc_2026-03-28.rvt)
  BYGG_REPO_ROOT       -- extension root (set by Run-ByggPipelineSetup.ps1; required when task script runs from synced flat folder)
"""

from __future__ import print_function

import json
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")

from System import Guid

import revit_script_util
from revit_script_util import Output

doc = revit_script_util.GetScriptDocument()
revit_file_path = revit_script_util.GetRevitFilePath() or ""

_sidecar_env = os.environ.get("RBP_SIDECAR_PATH", "").strip()
_model_basename = os.path.splitext(os.path.basename(revit_file_path))[0]
_model_dir = os.path.dirname(revit_file_path)
_sidecar_default = os.path.join(_model_dir, _model_basename + ".rbp_publish_acc_result.json")
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


def _parse_guid(s):
    if not s or not str(s).strip():
        return None
    return Guid.Parse(str(s).strip())


def _repo_root():
    """Extension root (contains lib/rbp_paths.py). Launcher sets BYGG_REPO_ROOT when scripts are synced flat."""
    env_root = os.environ.get("BYGG_REPO_ROOT", "").strip()
    if env_root and os.path.isfile(os.path.join(env_root, "lib", "rbp_paths.py")):
        return env_root
    try:
        _script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        _script_dir = os.getcwd()
    _d = _script_dir
    for _ in range(24):
        if os.path.isfile(os.path.join(_d, "lib", "rbp_paths.py")):
            return _d
        _parent = os.path.dirname(_d)
        if _parent == _d:
            break
        _d = _parent
    return None


def _ensure_workshared_for_cloud_publish(doc):
    """If doc is not workshared, enable worksharing (Revit requires this for workshared cloud)."""
    try:
        before = bool(doc.IsWorkshared)
    except Exception:
        before = False
    if before:
        return False
    root = _repo_root()
    if not root:
        raise RuntimeError("Could not find repo root (lib/rbp_paths.py).")
    lib = os.path.join(root, "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    if root not in sys.path:
        sys.path.insert(0, root)
    import utils  # noqa: E402
    import bygg_setup_core  # noqa: E402

    Output(
        "Model is not workshared; enabling worksharing before SaveAsCloudModel "
        "(non-workshared local files become non-workshared cloud models)."
    )
    settings = utils.load_settings()
    bygg_setup_core.setup_worksets(doc, settings)
    if not doc.IsWorkshared:
        raise RuntimeError(
            "Worksharing could not be enabled; aborting publish to avoid a non-workshared cloud model."
        )
    try:
        doc.Save()
        Output("Saved local model after enabling worksharing.")
    except Exception as exc:
        Output("WARN: Save after EnableWorksharing: {}".format(exc))
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Output()
Output("=== Byggstyrning Publish to ACC (RBP) ===")
Output("Model: {}".format(revit_file_path))

rw = {
    "step": "publish_acc",
    "cloud_publish_succeeded": False,
    "model_name": None,
    "account_id": None,
    "project_id": None,
    "error": None,
    "doc_is_workshared_before_ensure": None,
    "worksharing_ensured_in_publish": None,
    "doc_is_workshared_at_publish": None,
}

try:
    acc_s = os.environ.get("BYGG_ACC_ACCOUNT_GUID", "").strip()
    prj_s = os.environ.get("BYGG_ACC_PROJECT_GUID", "").strip()
    fld_s = os.environ.get("BYGG_ACC_FOLDER_ID", "").strip()
    name_s = os.environ.get("BYGG_CLOUD_MODEL_NAME", "").strip()

    rw["model_name"] = name_s or None
    rw["account_id"] = acc_s or None
    rw["project_id"] = prj_s or None

    if not acc_s or not prj_s or not fld_s or not name_s:
        raise ValueError(
            "Missing env: BYGG_ACC_ACCOUNT_GUID, BYGG_ACC_PROJECT_GUID, "
            "BYGG_ACC_FOLDER_ID, BYGG_CLOUD_MODEL_NAME"
        )

    acc_g = _parse_guid(acc_s)
    prj_g = _parse_guid(prj_s)
    if acc_g is None or prj_g is None:
        raise ValueError("Invalid account or project GUID")

    try:
        rw["doc_is_workshared_before_ensure"] = bool(doc.IsWorkshared)
    except Exception:
        rw["doc_is_workshared_before_ensure"] = None

    rw["worksharing_ensured_in_publish"] = _ensure_workshared_for_cloud_publish(doc)

    try:
        rw["doc_is_workshared_at_publish"] = bool(doc.IsWorkshared)
    except Exception:
        rw["doc_is_workshared_at_publish"] = None

    if not rw["doc_is_workshared_at_publish"]:
        raise RuntimeError(
            "Document is not workshared; cannot create a workshared cloud model (see Revit API SaveAsCloudModel remarks)."
        )

    Output(
        "SaveAsCloudModel: modelName={} folderId(len)={}".format(
            name_s, len(fld_s)
        )
    )

    doc.SaveAsCloudModel(acc_g, prj_g, fld_s, name_s)
    rw["cloud_publish_succeeded"] = True
    try:
        rw["doc_pathname_after"] = str(doc.PathName or "")
    except Exception:
        rw["doc_pathname_after"] = None
    Output("SaveAsCloudModel completed.")
except Exception as exc:
    rw["error"] = str(exc)
    Output("FATAL: {}".format(traceback.format_exc()))
finally:
    _write_sidecar(rw)

Output("=== Byggstyrning Publish to ACC complete ===")
