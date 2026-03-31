from pyrevit import forms
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB import ModelPathUtils, RevitLinkType, RevitLinkOptions, RevitLinkInstance

def get_structural_elements(doc):
    """Get all structural elements from the document"""
    collector = FilteredElementCollector(doc)\
        .WhereElementIsNotElementType()
    
    structural_elements = []
    for elem in collector:
        param = elem.LookupParameter("BIP.Structural Building Part")
        if param and param.AsInteger() == 1:
            structural_elements.append(elem)
    
    return structural_elements

def get_ifc_openings(doc):
    """Get all IFC opening elements from the document"""
    collector = FilteredElementCollector(doc)\
        .WhereElementIsNotElementType()
    
    openings = []
    for elem in collector:
        param = elem.LookupParameter("Export to IFC As")
        if param and param.AsString() == "IfcOpeningElement":
            openings.append(elem)
    
    return openings

def move_elements_to_workset(doc, elements, workset_id):
    """Move elements to specified workset"""
    t = Transaction(doc, "Move to Workset")
    t.Start()
    try:
        for elem in elements:
            elem.WorksetId = workset_id
        t.Commit()
        return True
    except Exception as e:
        t.RollBack()
        forms.alert("Failed to move elements: {}".format(str(e)))
        return False

def link_ifc(ifc_path):
    t = Transaction(doc, "Link IFC")
    t.Start()
    try:
        link_options = RevitLinkOptions(False)
        model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(ifc_path)
        link_type = RevitLinkType.Create(doc, model_path, link_options)
        link_instance = RevitLinkInstance.Create(doc, link_type.ElementId)
        t.Commit()
        return True
    except Exception as e:
        t.RollBack()
        forms.alert("Failed to link IFC: {}".format(str(e)))
        return False 