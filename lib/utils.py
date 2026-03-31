import json
import os
from Autodesk.Revit.DB import *


def _get_forms():
    """Return pyrevit.forms if available (pyRevit host), else None (RBP host)."""
    try:
        from pyrevit import forms as _f
        return _f
    except ImportError:
        return None


def load_settings():
    """Load settings from settings.json.

    - pyRevit: lib/utils.py -> parent repo folder has settings.json
    - BatchRvt: utils.py is synced next to settings.json in the same job folder
    """
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, 'settings.json'),
        os.path.join(base, '..', 'settings.json'),
    ]
    for settings_path in candidates:
        settings_path = os.path.normpath(settings_path)
        if os.path.isfile(settings_path):
            with open(settings_path, 'r') as f:
                return json.load(f)
    raise IOError(
        "settings.json not found; tried: {}".format(", ".join(candidates))
    )

def get_default_path(key):
    """Get default path from settings"""
    settings = load_settings()
    return settings['default_paths'].get(key)

def pick_ifc_file(title="Select IFC File"):
    """Prompt user to select an IFC file (pyRevit only)."""
    forms = _get_forms()
    if forms is None:
        raise RuntimeError("pick_ifc_file requires a pyRevit host")
    return forms.pick_file(file_ext='ifc', title=title)

def pick_config_file():
    """Prompt user to select Config file (pyRevit only)."""
    forms = _get_forms()
    if forms is None:
        raise RuntimeError("pick_config_file requires a pyRevit host")
    return forms.pick_file(file_ext='rvt', title="Select Config File")

def get_3d_view(doc):
    """Get or create a 3D view"""
    collector = FilteredElementCollector(doc).OfClass(View3D)
    for view in collector:
        if not view.IsTemplate:
            return view
    return None

def get_first_floor_plan(doc):
    """Get First Floor plan view"""
    collector = FilteredElementCollector(doc).OfClass(ViewPlan)
    for view in collector:
        if "First Floor" in view.Name:
            return view
    return None

def rotate_view(doc, view, angle, axis_line=None):
    """Rotate view by angle around axis line."""
    t = Transaction(doc, "Rotate View")
    t.Start()
    try:
        if axis_line:
            pass  # TODO: Implement rotation around line
        else:
            view.Rotate(angle)
        t.Commit()
        return True
    except Exception as e:
        t.RollBack()
        forms = _get_forms()
        if forms:
            forms.alert("Failed to rotate view: {}".format(str(e)))
        else:
            print("[ERROR] Failed to rotate view: {}".format(str(e)))
        return False 