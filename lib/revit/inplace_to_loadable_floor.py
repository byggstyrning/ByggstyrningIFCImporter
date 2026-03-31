# -*- coding: utf-8 -*-
"""Build a loadable family from in-place instance geometry, routed by IFC Predefined Type."""

import os
import re
import shutil
import tempfile
import uuid

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Category,
    DirectShape,
    ElementId,
    Extrusion,
    Family,
    FamilyInstance,
    FilteredElementCollector,
    GeometryInstance,
    Level,
    Options,
    SaveAsOptions,
    Solid,
    SolidUtils,
    StorageType,
    SubTransaction,
    Transform,
    Transaction,
    ViewDetailLevel,
    XYZ,
)

from Autodesk.Revit.DB.Structure import StructuralType

import param_cache_floor

PREDEFINED_TYPE_MAP = {
    "FLOORING":    ("Floor Family Template.rfa",   BuiltInCategory.OST_Floors),
    "NOTDEFINED":  ("Floor Family Template.rfa",   BuiltInCategory.OST_Floors),
    "ROOFING":     ("Roofs Family Template.rfa",   BuiltInCategory.OST_Roofs),
    "CEILING":     ("Ceiling Family Template.rfa", BuiltInCategory.OST_Ceilings),
}

_LEGACY_TEMPLATE_NAMES = ("Floor Family Template.rfa", "empty.rfa")


def _build_family_name(doc, inst, target_category):
    """Readable family / RFA base name: <Revit Category> - <Name (Attribute)> - <IfcGUID>."""
    try:
        cat = Category.GetCategory(doc, target_category)
        cat_name = cat.Name if cat else "Unknown"
    except Exception:
        cat_name = "Unknown"
    name_attr = ""
    try:
        p = inst.LookupParameter("Name (Attribute)")
        if p and p.HasValue:
            name_attr = (p.AsString() or "").strip()
    except Exception:
        pass
    guid = param_cache_floor.get_ifc_guid(inst) or ""
    raw = "{0} - {1} - {2}".format(cat_name, name_attr, guid)
    safe = re.sub(r'[<>:"/\\|?*]', "_", raw).strip()
    if not safe:
        safe = "Unnamed"
    if len(safe) > 180:
        safe = safe[:180]
    return safe


def _unique_rfa_work_path(doc, inst, target_category):
    """Temp .rfa path using _build_family_name; adds suffix if file already exists."""
    base = _build_family_name(doc, inst, target_category)
    fname = base + ".rfa"
    path = os.path.join(tempfile.gettempdir(), fname)
    if os.path.exists(path):
        path = os.path.join(
            tempfile.gettempdir(),
            base + "_" + uuid.uuid4().hex[:8] + ".rfa",
        )
    return path


def _find_template(script_path, template_name):
    """Locate a template .rfa in the extension root or parent folder."""
    ext = param_cache_floor._extension_dir_from_script(script_path)
    p = os.path.join(ext, template_name)
    if os.path.isfile(p):
        return p
    alt = os.path.join(os.path.dirname(ext), template_name)
    if os.path.isfile(alt):
        return alt
    return None


def get_empty_rfa_path(script_path):
    """Legacy helper -- returns the first available Floor template."""
    for name in _LEGACY_TEMPLATE_NAMES:
        p = _find_template(script_path, name)
        if p:
            return p
    return None


def get_ifc_predefined_type(doc, inst):
    """Read 'Type IFC Predefined Type' from the element's type or instance."""
    names = ("Type IFC Predefined Type", "IfcExportType")
    tid = inst.GetTypeId()
    if tid and tid != ElementId.InvalidElementId:
        etype = doc.GetElement(tid)
        if etype:
            for name in names:
                p = etype.LookupParameter(name)
                if p and p.HasValue:
                    val = p.AsString()
                    if not val and hasattr(p, "AsValueString"):
                        val = p.AsValueString()
                    if val:
                        return val.strip()
    for name in names:
        p = inst.LookupParameter(name)
        if p and p.HasValue:
            val = p.AsString()
            if not val and hasattr(p, "AsValueString"):
                val = p.AsValueString()
            if val:
                return val.strip()
    return None


def _walk_solids(geom, current, out):
    """Collect solids with cumulative transform (instance/symbol space)."""
    if geom is None:
        return
    try:
        from Autodesk.Revit.DB import SolidUtils

        it = geom.GetEnumerator()
        while it.MoveNext():
            obj = it.Current
            if isinstance(obj, Solid):
                try:
                    if obj.Volume > 1e-9:
                        if current is not None and not current.IsIdentity:
                            try:
                                out.append(SolidUtils.CreateTransformed(obj, current))
                            except Exception:
                                out.append(obj)
                        else:
                            out.append(obj)
                except Exception:
                    pass
            elif isinstance(obj, GeometryInstance):
                t = current.Multiply(obj.Transform) if current is not None else obj.Transform
                sub = obj.GetSymbolGeometry()
                _walk_solids(sub, t, out)
    except Exception:
        return


def extract_solids_from_instance(instance):
    """Return list of Solid in approximate instance coordinates."""
    opt = Options()
    opt.DetailLevel = ViewDetailLevel.Fine
    opt.ComputeReferences = False
    geom = instance.get_Geometry(opt)
    solids = []
    _walk_solids(geom, Transform.Identity, solids)
    return solids


def _union_solids(solids):
    """Union solids into one; return first solid if union fails."""
    if not solids:
        return None
    if len(solids) == 1:
        return solids[0]
    try:
        from Autodesk.Revit.DB import BooleanOperationsUtils, BooleanOperationsType

        acc = solids[0]
        for s in solids[1:]:
            try:
                acc = BooleanOperationsUtils.ExecuteBooleanOperation(
                    acc, s, BooleanOperationsType.Union
                )
            except Exception:
                return solids[0]
        return acc
    except Exception:
        return solids[0]


def _try_freeform(family_doc, solid):
    try:
        from Autodesk.Revit.DB import FreeFormElement

        return FreeFormElement.Create(family_doc, solid)
    except Exception:
        return None


def _try_direct_shape(family_doc, solid, category=None):
    try:
        cat = ElementId(category or BuiltInCategory.OST_GenericModel)
        ds = DirectShape.CreateElement(family_doc, cat)
        ds.SetShape([solid])
        return ds
    except Exception:
        return None


def _solid_center(solid):
    """Return bounding-box center of a solid as XYZ."""
    bb = solid.GetBoundingBox()
    return XYZ(
        (bb.Min.X + bb.Max.X) / 2.0,
        (bb.Min.Y + bb.Max.Y) / 2.0,
        (bb.Min.Z + bb.Max.Z) / 2.0,
    )


def _translate_solid(solid, vector):
    """Translate a solid by an XYZ vector."""
    xf = Transform.CreateTranslation(vector)
    return SolidUtils.CreateTransformed(solid, xf)


def _delete_placeholder_geometry(family_doc):
    """Remove template extrusions/forms so we can insert new geometry."""
    try:
        extrusions = list(FilteredElementCollector(family_doc).OfClass(Extrusion).ToElements())
        for ex in extrusions:
            try:
                family_doc.Delete(ex.Id)
            except Exception:
                pass
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import GenericForm, Form

        for cls in (Form, GenericForm):
            try:
                for el in FilteredElementCollector(family_doc).OfClass(cls).ToElements():
                    try:
                        family_doc.Delete(el.Id)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


def _find_family_by_name(doc, name):
    """Return Family whose Name == name, or None."""
    if not name:
        return None
    for f in FilteredElementCollector(doc).OfClass(Family).ToElements():
        if f.Name == name:
            return f
    return None


def _resolve_loaded_family(doc, load_result, base_name):
    """Interpret IronPython LoadFamily return (bool, tuple, Family, or None)."""
    if load_result is None:
        return None
    try:
        if isinstance(load_result, tuple):
            if len(load_result) > 1 and load_result[1] is not None:
                return load_result[1]
            if len(load_result) > 0 and load_result[0] is True:
                return _find_family_by_name(doc, base_name)
            return None
        if isinstance(load_result, Family):
            return load_result
        if load_result is True:
            return _find_family_by_name(doc, base_name)
        if load_result is False:
            return None
    except Exception:
        pass
    return _find_family_by_name(doc, base_name)


def _load_family_from_disk(doc, app, work_path):
    """Load .rfa into project; return (Family or None, error_message or None)."""
    if not work_path or not os.path.isfile(work_path):
        return None, "RFA file missing: {0}".format(work_path)

    load_opts = param_cache_floor._default_family_load_options()
    base_name = os.path.splitext(os.path.basename(work_path))[0]
    load_result = None
    last_err = None

    for attempt in (1, 2):
        try:
            if attempt == 1:
                load_result = doc.LoadFamily(work_path, load_opts)
            else:
                load_result = doc.LoadFamily(work_path)
        except Exception as ex:
            last_err = str(ex)
            load_result = None
            continue
        loaded = _resolve_loaded_family(doc, load_result, base_name)
        if loaded is not None:
            return loaded, None

    fd = None
    try:
        fd = app.OpenDocumentFile(work_path)
        if fd is not None:
            load_result = fd.LoadFamily(doc, load_opts)
    except Exception as ex:
        last_err = str(ex)
        load_result = None
    finally:
        if fd is not None:
            try:
                fd.Close(False)
            except Exception:
                pass

    loaded = _resolve_loaded_family(doc, load_result, base_name)
    if loaded is not None:
        return loaded, None

    return None, last_err or "LoadFamily did not load family (name: {0})".format(base_name)


def _get_default_symbol(family):
    ids = family.GetFamilySymbolIds()
    if not ids:
        return None
    try:
        for sid in ids:
            return family.Document.GetElement(sid)
    except Exception:
        pass
    return None


def _copy_ifc_guid_between_elements(src, dst):
    """Copy IFC GUID string params from src to dst when writable."""
    guid = param_cache_floor.get_ifc_guid(src)
    if not guid:
        return
    for name in ("IfcGUID", "IFC GUID"):
        p = dst.LookupParameter(name)
        if p and not p.IsReadOnly and p.StorageType == StorageType.String:
            try:
                p.Set(guid)
                return
            except Exception:
                pass
    try:
        p = dst.get_Parameter(BuiltInParameter.IFC_GUID)
        if p and not p.IsReadOnly:
            p.Set(guid)
    except Exception:
        pass


def _prepare_loadable_family(doc, app, inst, template_path, target_category):
    """
    Prepare phase: extract geometry, build family RFA, load into project.
    No project-level transaction — only family-doc transactions.
    Returns dict with 'symbol', 'placement_pt', 'level', 'inst_id', 'timings' on success,
    or 'success': False on failure.
    """
    import time as _t
    timings = {}

    if not isinstance(inst, FamilyInstance):
        return {"success": False, "message": "Not a family instance."}

    _s = _t.time()
    solids = extract_solids_from_instance(inst)
    if not solids:
        return {"success": False, "message": "No solid geometry extracted from the instance."}

    solid = _union_solids(solids)
    if solid is None:
        return {"success": False, "message": "Could not build a solid from extracted geometry."}

    solid_origin = _solid_center(solid)
    solid = _translate_solid(solid, XYZ(-solid_origin.X, -solid_origin.Y, -solid_origin.Z))
    timings["extract"] = _t.time() - _s

    _s = _t.time()
    work_path = _unique_rfa_work_path(doc, inst, target_category)
    try:
        shutil.copy2(template_path, work_path)
    except Exception as ex:
        return {"success": False, "message": "Could not copy template: {0}".format(ex)}

    family_doc = app.OpenDocumentFile(work_path)
    if not family_doc:
        return {"success": False, "message": "Failed to open copied family document."}
    timings["open_template"] = _t.time() - _s

    _s = _t.time()
    t = Transaction(family_doc, "Byggstyrning: insert geometry into template")
    t.Start()
    try:
        _delete_placeholder_geometry(family_doc)
        ff = _try_freeform(family_doc, solid)
        if ff is None:
            ds = _try_direct_shape(family_doc, solid, category=target_category)
            if ds is None:
                t.RollBack()
                try:
                    family_doc.Close(False)
                except Exception:
                    pass
                return {
                    "success": False,
                    "message": "Could not create FreeForm or DirectShape in the family.",
                }
        try:
            family_doc.Regenerate()
        except Exception:
            pass
        t.Commit()
    except Exception as ex:
        if t.HasStarted():
            t.RollBack()
        try:
            family_doc.Close(False)
        except Exception:
            pass
        return {"success": False, "message": "Family edit failed: {0}".format(ex)}
    timings["insert_geo"] = _t.time() - _s

    _s = _t.time()
    save_opts = SaveAsOptions()
    save_opts.OverwriteExistingFile = True
    try:
        family_doc.SaveAs(work_path, save_opts)
    except Exception as ex:
        try:
            family_doc.Close(False)
        except Exception:
            pass
        return {"success": False, "message": "SaveAs failed: {0}".format(ex)}
    timings["save"] = _t.time() - _s

    _s = _t.time()
    load_opts = param_cache_floor._default_family_load_options()
    load_result = None
    load_err = None
    try:
        load_result = family_doc.LoadFamily(doc, load_opts)
    except Exception as ex:
        load_err = str(ex)
    finally:
        try:
            family_doc.Close(False)
        except Exception:
            pass

    base_name = os.path.splitext(os.path.basename(work_path))[0]
    loaded_family = _resolve_loaded_family(doc, load_result, base_name)

    if not loaded_family:
        loaded_family, disk_err = _load_family_from_disk(doc, app, work_path)
        if not load_err:
            load_err = disk_err

    if not loaded_family:
        return {
            "success": False,
            "message": "LoadFamily failed: {0}".format(load_err or "unknown"),
            "temp_rfa_path": work_path,
        }
    timings["load"] = _t.time() - _s

    try:
        fid = loaded_family.Id
        loaded_family = doc.GetElement(fid)
    except Exception:
        pass

    symbol = _get_default_symbol(loaded_family)
    if symbol is None:
        return {
            "success": False,
            "message": "Loaded family has no types.",
            "temp_rfa_path": work_path,
            "family_name": getattr(loaded_family, "Name", ""),
        }

    level = None
    try:
        lid = inst.LevelId
        if lid and lid != ElementId.InvalidElementId:
            level = doc.GetElement(lid)
    except Exception:
        pass
    if level is None:
        try:
            levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
            if levels:
                level = levels[0]
        except Exception:
            pass
    if level is None:
        return {
            "success": False,
            "message": "Could not resolve level for new instance.",
            "temp_rfa_path": work_path,
        }

    level_elev = 0.0
    try:
        level_elev = level.Elevation
    except Exception:
        pass
    placement_pt = XYZ(solid_origin.X, solid_origin.Y, solid_origin.Z - level_elev)

    return {
        "success": True,
        "symbol": symbol,
        "placement_pt": placement_pt,
        "level": level,
        "inst_id": inst.Id,
        "inst": inst,
        "family_name": loaded_family.Name,
        "temp_rfa_path": work_path,
        "timings": timings,
    }


def _convert_single_inplace(doc, app, inst, template_path, target_category):
    """
    Build RFA from template + instance geometry, load into project, place instance, copy GUID.
    Does NOT call prepare_migration or restore_from_cache (caller handles cache).
    Returns dict with success/failure info and per-step timing ('timings' key).
    """
    import time as _t

    prep = _prepare_loadable_family(doc, app, inst, template_path, target_category)
    if not prep.get("success"):
        return prep
    timings = dict(prep.get("timings") or {})

    _s = _t.time()
    symbol = prep["symbol"]
    new_inst = None
    tp = Transaction(doc, "Byggstyrning: place loaded family + copy GUID")
    tp.Start()
    try:
        try:
            if hasattr(symbol, "IsActive") and not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
        except Exception:
            pass
        new_inst = doc.Create.NewFamilyInstance(
            prep["placement_pt"], symbol, prep["level"], StructuralType.NonStructural
        )
        _copy_ifc_guid_between_elements(inst, new_inst)
        doc.Delete(inst.Id)
        tp.Commit()
    except Exception as ex:
        if tp.HasStarted():
            tp.RollBack()
        return {
            "success": False,
            "message": "Failed to place instance: {0}".format(ex),
            "temp_rfa_path": prep.get("temp_rfa_path"),
            "family_name": prep.get("family_name"),
        }
    timings["place_delete"] = _t.time() - _s

    return {
        "success": True,
        "message": "Done.",
        "family_name": prep["family_name"],
        "temp_rfa_path": prep["temp_rfa_path"],
        "new_element_id": new_inst.Id.IntegerValue,
        "timings": timings,
    }


def _read_param_value(p):
    """Read a parameter value into a Python-native tuple (storage_tag, value)."""
    if p is None or not p.HasValue:
        return None
    st = p.StorageType
    if st == StorageType.String:
        return ("string", p.AsString())
    if st == StorageType.Double:
        return ("double", p.AsDouble())
    if st == StorageType.Integer:
        return ("integer", p.AsInteger())
    if st == StorageType.ElementId:
        eid = p.AsElementId()
        if eid is None or eid == ElementId.InvalidElementId:
            return None
        return ("elementid", eid.IntegerValue)
    return None


def _write_param_value(p, pair):
    """Write a (storage_tag, value) pair to a parameter. Returns True on success."""
    if p is None or pair is None or p.IsReadOnly:
        return False
    tag, val = pair
    st = p.StorageType
    try:
        if st == StorageType.String and tag == "string":
            return p.Set(val or "")
        if st == StorageType.Double and tag == "double":
            return p.Set(float(val))
        if st == StorageType.Integer and tag == "integer":
            return p.Set(int(val))
        if st == StorageType.ElementId and tag == "elementid":
            return p.Set(ElementId(int(val)))
    except Exception:
        return False
    return False


def _snapshot_element_params(doc, elem):
    """Snapshot all writable params from instance + type into a dict.

    Returns { (scope, param_name): (storage_tag, value), ... }
    """
    snap = {}
    for p in elem.Parameters:
        if param_cache_floor._should_skip_parameter(p):
            continue
        v = _read_param_value(p)
        if v is not None:
            snap[("instance", p.Definition.Name)] = v
    tid = elem.GetTypeId()
    if tid and tid != ElementId.InvalidElementId:
        et = doc.GetElement(tid)
        if et:
            for p in et.Parameters:
                if param_cache_floor._should_skip_parameter(p):
                    continue
                v = _read_param_value(p)
                if v is not None:
                    snap[("type", p.Definition.Name)] = v
    return snap


def _apply_snapshot_to_element(doc, elem, snap):
    """Write snapshot values using the same parameter names as on the source element."""
    ok = 0
    skipped = 0
    applied = []
    skipped_names = []
    etype = None
    tid = elem.GetTypeId()
    if tid and tid != ElementId.InvalidElementId:
        etype = doc.GetElement(tid)
    for (scope, name), pair in snap.items():
        target = None
        if scope == "instance":
            target = elem.LookupParameter(name)
        elif scope == "type" and etype is not None:
            target = etype.LookupParameter(name)
        if target is None:
            skipped += 1
            skipped_names.append("{0} ({1})".format(name, scope))
            continue
        if _write_param_value(target, pair):
            ok += 1
            applied.append("{0} ({1})".format(name, scope))
        else:
            skipped += 1
            skipped_names.append("{0} ({1}) write_failed".format(name, scope))
    return ok, skipped, applied


def batch_convert_all_inplace(doc, app, script_path, progress_callback=None):
    """
    Convert ALL in-place Generic Model instances in the project.

    1. Collect every Generic Model FamilyInstance where Family.IsInPlace.
    2. Filter/group by IFC Predefined Type -> template mapping.
    3. Snapshot all parameter values in-memory (no JSON cache).
    4. Ensure shared parameters are bound to target categories.
    5. Build loadable families, place instances, delete originals.
    6. Write cached values directly to new instances.

    Returns dict with summary counts and per-phase timing.
    """
    import time as _t

    t_collect_start = _t.time()

    gm_cat = ElementId(BuiltInCategory.OST_GenericModel)
    all_gm = (
        FilteredElementCollector(doc)
        .OfCategoryId(gm_cat)
        .OfClass(FamilyInstance)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    work_items = []
    total_inplace = 0
    skipped_no_pdt = 0
    skipped_unmapped = 0
    skipped_no_template = 0
    template_cache = {}

    for inst in all_gm:
        fam = inst.Symbol.Family
        if not param_cache_floor.family_is_inplace(fam):
            continue
        total_inplace += 1
        pdt = get_ifc_predefined_type(doc, inst)
        pdt_key = (pdt or "").strip().upper()
        if not pdt_key:
            skipped_no_pdt += 1
            continue
        mapping = PREDEFINED_TYPE_MAP.get(pdt_key)
        if mapping is None:
            skipped_unmapped += 1
            continue
        tpl_name, tgt_cat = mapping
        if tpl_name not in template_cache:
            template_cache[tpl_name] = _find_template(script_path, tpl_name)
        tpl_path = template_cache[tpl_name]
        if not tpl_path:
            skipped_no_template += 1
            continue
        work_items.append((inst, tpl_path, tgt_cat, pdt))

    t_collect = _t.time() - t_collect_start
    total = len(work_items)
    empty_result = {
        "total_inplace": total_inplace,
        "total_eligible": 0,
        "converted": 0,
        "skipped_no_pdt": skipped_no_pdt,
        "skipped_unmapped": skipped_unmapped,
        "skipped_no_template": skipped_no_template,
        "errors": [],
        "restore_ok": 0,
        "restore_fail": 0,
        "restore_skipped": 0,
        "applied_labels": [],
        "t_collect": t_collect,
        "t_cache": 0.0,
        "t_convert": 0.0,
        "t_restore": 0.0,
    }
    if total == 0:
        return empty_result

    # -- Phase 0: snapshot params in-memory + bind shared params --
    t_cache_start = _t.time()
    all_eids = [inst.Id for inst, _, _, _ in work_items]

    snapshots = {}
    for inst, _, _, _ in work_items:
        guid = param_cache_floor.get_ifc_guid(inst)
        snap = _snapshot_element_params(doc, inst)
        snapshots[inst.Id.IntegerValue] = {"guid": guid, "snap": snap}

    param_cache_floor.ensure_and_bind_shared_params(
        doc, app, all_eids, script_path
    )
    n_cached = len(snapshots)
    t_cache = _t.time() - t_cache_start

    # -- Phase 1: prepare families, reusing template docs --
    prepared = []
    errors = []
    step_totals = {}

    groups = {}
    for idx, item in enumerate(work_items):
        tpl_path = item[1]
        groups.setdefault(tpl_path, []).append((idx, item))

    t_convert_start = _t.time()
    load_opts = param_cache_floor._default_family_load_options()
    save_opts = SaveAsOptions()
    save_opts.OverwriteExistingFile = True
    progress_idx = [0]

    for tpl_path, group in groups.items():
        tpl_copy = os.path.join(tempfile.gettempdir(), "Byggstyrning_tpl_{0}.rfa".format(
            uuid.uuid4().hex[:6]
        ))
        try:
            shutil.copy2(tpl_path, tpl_copy)
        except Exception as ex:
            for _, (inst, _, _, pdt) in group:
                errors.append("Template copy failed: {0} (PDT={1})".format(ex, pdt))
            progress_idx[0] += len(group)
            continue

        _s = _t.time()
        family_doc = app.OpenDocumentFile(tpl_copy)
        step_totals["open_template"] = step_totals.get("open_template", 0.0) + (_t.time() - _s)
        if not family_doc:
            for _, (inst, _, _, pdt) in group:
                errors.append("Failed to open template (PDT={0})".format(pdt))
            progress_idx[0] += len(group)
            continue

        t_del = Transaction(family_doc, "Byggstyrning: clear placeholder")
        t_del.Start()
        try:
            _delete_placeholder_geometry(family_doc)
            t_del.Commit()
        except Exception:
            if t_del.HasStarted():
                t_del.RollBack()

        for _, (inst, _, tgt_cat, pdt) in group:
            if progress_callback:
                progress_callback(progress_idx[0], total)
            progress_idx[0] += 1

            _s = _t.time()
            solids = extract_solids_from_instance(inst)
            if not solids:
                errors.append("No solid geometry extracted from the instance. (PDT={0})".format(pdt))
                continue
            solid = _union_solids(solids)
            if solid is None:
                errors.append("Could not union solids. (PDT={0})".format(pdt))
                continue
            solid_origin = _solid_center(solid)
            solid = _translate_solid(solid, XYZ(-solid_origin.X, -solid_origin.Y, -solid_origin.Z))
            step_totals["extract"] = step_totals.get("extract", 0.0) + (_t.time() - _s)

            _s = _t.time()
            t_ins = Transaction(family_doc, "Byggstyrning: insert geometry")
            t_ins.Start()
            try:
                ff = _try_freeform(family_doc, solid)
                if ff is None:
                    ds = _try_direct_shape(family_doc, solid, category=tgt_cat)
                    if ds is None:
                        t_ins.RollBack()
                        errors.append("Could not create geometry in family. (PDT={0})".format(pdt))
                        continue
                try:
                    family_doc.Regenerate()
                except Exception:
                    pass
                t_ins.Commit()
            except Exception as ex:
                if t_ins.HasStarted():
                    t_ins.RollBack()
                errors.append("Family edit failed: {0} (PDT={1})".format(ex, pdt))
                continue
            step_totals["insert_geo"] = step_totals.get("insert_geo", 0.0) + (_t.time() - _s)

            unique_path = _unique_rfa_work_path(doc, inst, tgt_cat)

            _s = _t.time()
            try:
                family_doc.SaveAs(unique_path, save_opts)
            except Exception as ex:
                errors.append("SaveAs failed: {0} (PDT={1})".format(ex, pdt))
                continue
            step_totals["save"] = step_totals.get("save", 0.0) + (_t.time() - _s)

            _s = _t.time()
            load_result = None
            try:
                load_result = family_doc.LoadFamily(doc, load_opts)
            except Exception:
                pass
            base_name = os.path.splitext(os.path.basename(unique_path))[0]
            loaded_family = _resolve_loaded_family(doc, load_result, base_name)
            if not loaded_family:
                errors.append("LoadFamily failed (PDT={0})".format(pdt))
                continue
            step_totals["load"] = step_totals.get("load", 0.0) + (_t.time() - _s)

            try:
                loaded_family = doc.GetElement(loaded_family.Id)
            except Exception:
                pass
            symbol = _get_default_symbol(loaded_family)
            if symbol is None:
                errors.append("No family types after load (PDT={0})".format(pdt))
                continue

            level = None
            try:
                lid = inst.LevelId
                if lid and lid != ElementId.InvalidElementId:
                    level = doc.GetElement(lid)
            except Exception:
                pass
            if level is None:
                try:
                    levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
                    if levels:
                        level = levels[0]
                except Exception:
                    pass
            if level is None:
                errors.append("No level found (PDT={0})".format(pdt))
                continue
            level_elev = 0.0
            try:
                level_elev = level.Elevation
            except Exception:
                pass

            prepared.append({
                "success": True,
                "symbol": symbol,
                "placement_pt": XYZ(solid_origin.X, solid_origin.Y, solid_origin.Z - level_elev),
                "level": level,
                "inst_id": inst.Id,
                "inst": inst,
                "family_name": loaded_family.Name,
            })

            t_rst = Transaction(family_doc, "Byggstyrning: reset")
            t_rst.Start()
            try:
                try:
                    from Autodesk.Revit.DB import FreeFormElement
                    for el in FilteredElementCollector(family_doc).OfClass(FreeFormElement).ToElements():
                        family_doc.Delete(el.Id)
                except Exception:
                    pass
                for el in FilteredElementCollector(family_doc).OfClass(DirectShape).ToElements():
                    try:
                        family_doc.Delete(el.Id)
                    except Exception:
                        pass
                t_rst.Commit()
            except Exception:
                if t_rst.HasStarted():
                    t_rst.RollBack()

        try:
            family_doc.Close(False)
        except Exception:
            pass

    t_prepare = _t.time() - t_convert_start

    if progress_callback:
        progress_callback(total, total)

    # -- Phase 2: batch place + delete + write params in ONE transaction --
    t_place_start = _t.time()
    converted = 0
    ok = fail_count = skipped_count = 0
    applied_labels = []

    if prepared:
        try:
            doc.Regenerate()
        except Exception:
            pass
        tp = Transaction(doc, "Byggstyrning: batch place loaded families + restore params")
        tp.Start()
        try:
            for p in prepared:
                old_id = p["inst_id"].IntegerValue
                entry = snapshots.get(old_id)

                st = SubTransaction(doc)
                st.Start()
                try:
                    sym = p["symbol"]
                    if hasattr(sym, "IsActive") and not sym.IsActive:
                        sym.Activate()
                    new_inst = doc.Create.NewFamilyInstance(
                        p["placement_pt"], sym, p["level"],
                        StructuralType.NonStructural,
                    )
                    _copy_ifc_guid_between_elements(p["inst"], new_inst)
                    doc.Delete(p["inst_id"])

                    if entry:
                        _ok, _sk, _ap = _apply_snapshot_to_element(
                            doc, new_inst, entry["snap"]
                        )
                        ok += _ok
                        skipped_count += _sk
                        applied_labels.extend(_ap)
                    else:
                        fail_count += 1

                    st.Commit()
                    converted += 1
                except Exception as ex:
                    if st.HasStarted():
                        st.RollBack()
                    errors.append("Place failed ({0}): {1}".format(
                        p.get("family_name", "?"), ex
                    ))
            tp.Commit()
        except Exception as ex:
            if tp.HasStarted():
                tp.RollBack()
            errors.append("Batch transaction failed: {0}".format(ex))

    t_place = _t.time() - t_place_start
    step_totals["place_delete"] = t_place
    t_convert = t_prepare + t_place

    return {
        "total_inplace": total_inplace,
        "total_eligible": total,
        "converted": converted,
        "skipped_no_pdt": skipped_no_pdt,
        "skipped_unmapped": skipped_unmapped,
        "skipped_no_template": skipped_no_template,
        "errors": errors,
        "n_cached": n_cached,
        "restore_ok": ok,
        "restore_fail": fail_count,
        "restore_skipped": skipped_count,
        "applied_labels": applied_labels,
        "t_collect": t_collect,
        "t_cache": t_cache,
        "t_convert": t_convert,
        "t_restore": 0.0,
        "step_totals": step_totals,
    }


def run_inplace_to_floor_rfa(doc, app, element_ids, script_path):
    """
    Standalone button: validate → IFC Predefined Type → prepare_migration once
    → _convert_single_inplace → restore_from_cache for the new instance.
    """
    if not element_ids:
        return {"success": False, "message": "Nothing selected."}

    eid = element_ids[0]
    inst = doc.GetElement(eid)
    if not isinstance(inst, FamilyInstance):
        return {"success": False, "message": "Select a family instance."}

    fam = inst.Symbol.Family
    if not param_cache_floor.family_is_inplace(fam):
        return {
            "success": False,
            "message": "Selected family is not in-place. Use Migrate IFC to Floor instead.",
        }

    pdt = get_ifc_predefined_type(doc, inst)
    pdt_key = (pdt or "").upper()
    mapping = PREDEFINED_TYPE_MAP.get(pdt_key)
    if mapping is None:
        return {
            "success": False,
            "skipped": True,
            "message": "IFC Predefined Type '{0}' is not mapped for conversion.".format(
                pdt or "(none)"
            ),
            "predefined_type": pdt,
        }

    template_name, target_category = mapping
    template_path = _find_template(script_path, template_name)
    if not template_path:
        return {
            "success": False,
            "message": "Template not found: place '{0}' in the extension folder.".format(
                template_name
            ),
            "predefined_type": pdt,
        }

    path, n = param_cache_floor.prepare_migration(doc, app, element_ids, script_path)

    r = _convert_single_inplace(doc, app, inst, template_path, target_category)
    if not r.get("success"):
        out = dict(r)
        out["path"] = path
        out["n_prepared"] = n
        return out

    ok, fail, skipped, labels = param_cache_floor.restore_from_cache(
        doc, [ElementId(r["new_element_id"])], script_path
    )

    return {
        "success": True,
        "message": "Done.",
        "path": path,
        "n_prepared": n,
        "family_name": r.get("family_name"),
        "temp_rfa_path": r.get("temp_rfa_path"),
        "restore_ok": ok,
        "restore_fail": fail,
        "restore_skipped": skipped,
        "applied_labels": labels,
        "new_element_id": r["new_element_id"],
        "predefined_type": pdt,
    }
