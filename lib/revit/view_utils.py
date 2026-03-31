from pyrevit import forms
from Autodesk.Revit.DB import *

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
    """Rotate view by angle around axis line"""
    t = Transaction(doc, "Rotate View")
    t.Start()
    try:
        if axis_line:
            # Rotate around picked line
            pass  # TODO: Implement rotation around line
        else:
            # Rotate around view center
            view.Rotate(angle)
        t.Commit()
        return True
    except Exception as e:
        t.RollBack()
        forms.alert("Failed to rotate view: {}".format(str(e)))
        return False 