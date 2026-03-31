# -*- coding: utf-8 -*-
"""Cache IFC / generic-model parameters and prepare Floor bindings for category migration."""

from __future__ import print_function

import io
import json
import os
import re

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Category,
    CategorySet,
    ElementId,
    ExternalDefinition,
    ExternalDefinitionCreationOptions,
    FamilyInstance,
    FilteredElementCollector,
    InstanceBinding,
    InternalDefinition,
    StorageType,
    Transaction,
    TypeBinding,
)

CACHE_FILENAME = "floor_param_migrate_cache.json"
SP_FILENAME = "Byggstyrning_IFC_param_migrate.txt"
SP_GROUP_NAME = "IFC_to_Floor_Migrate"


def migration_mode_for_selection(doc, element_ids):
    """
    Decide prepare vs restore from element categories.

    Returns:
        ('prepare', None) if all are Generic Model,
        ('restore', None) if all are Floors,
        (None, error_message) if empty, mixed, or unsupported.
    """
    if not element_ids:
        return None, "No elements selected."
    gm_id = ElementId(BuiltInCategory.OST_GenericModel)
    fl_id = ElementId(BuiltInCategory.OST_Floors)
    modes = set()
    for eid in element_ids:
        elem = doc.GetElement(eid)
        if elem is None:
            return None, "Selection contains a deleted element."
        cat = elem.Category
        if cat is None:
            return None, "Selection contains an element with no category."
        cid = cat.Id
        if cid == gm_id:
            modes.add("prepare")
        elif cid == fl_id:
            modes.add("restore")
        else:
            try:
                cname = cat.Name
            except Exception:
                cname = "?"
            return None, (
                "Unsupported category: {0}. Select only Generic Model (before "
                "category change) or Floor (after)."
            ).format(cname)
    if len(modes) > 1:
        return None, (
            "Mixed selection: select only Generic Model elements, or only Floor "
            "elements, not both."
        )
    if "prepare" in modes:
        return "prepare", None
    if "restore" in modes:
        return "restore", None
    return None, "Could not determine migration step."


def _extension_dir_from_script(script_path):
    """Resolve extension root (folder containing lib/ and settings.json)."""
    d = os.path.dirname(script_path)
    for _ in range(8):
        if os.path.basename(d).endswith(".extension"):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.dirname(os.path.dirname(os.path.dirname(script_path)))


def cache_file_path(script_path):
    lib_dir = os.path.join(_extension_dir_from_script(script_path), "lib")
    if not os.path.isdir(lib_dir):
        os.makedirs(lib_dir)
    return os.path.join(lib_dir, CACHE_FILENAME)


def _safe_param_name(name):
    if not name:
        return "UNNAMED_PARAM"
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", name.strip())
    if not s:
        s = "UNNAMED_PARAM"
    if len(s) > 120:
        s = s[:120]
    return s


def get_ifc_guid(element):
    p = None
    try:
        p = element.get_Parameter(BuiltInParameter.IFC_GUID)
    except Exception:
        p = None
    if (p is None) or (not p.HasValue):
        for name in ("IFC GUID", "IfcGUID"):
            p = element.LookupParameter(name)
            if p and p.HasValue:
                break
        else:
            p = None
    if p is None:
        return None
    s = p.AsString()
    if not s and hasattr(p, "AsValueString"):
        s = p.AsValueString()
    return s.strip() if s else None


def _builtin_skip(bip):
    if bip is None:
        return False
    skips = [
        BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM,
        BuiltInParameter.ELEM_TYPE_PARAM,
        BuiltInParameter.ELEM_PARTITION_PARAM,
    ]
    try:
        BuiltInParameter.ELEM_CATEGORY_PARAM
    except Exception:
        pass
    else:
        skips.append(BuiltInParameter.ELEM_CATEGORY_PARAM)
    return bip in skips


def _should_skip_parameter(p):
    if p is None:
        return True
    try:
        if p.IsReadOnly:
            return True
    except Exception:
        pass
    try:
        bip = None
        if hasattr(p, "Definition") and p.Definition:
            idef = p.Definition
            if isinstance(idef, InternalDefinition) and idef.BuiltInParameter != BuiltInParameter.INVALID:
                bip = idef.BuiltInParameter
        if _builtin_skip(bip):
            return True
    except Exception:
        pass
    return False


def _spec_type_for_parameter(p):
    """Pick spec-type identifier for a new shared parameter.

    Handles three Revit API generations:
      Revit 2022+  → SpecTypeId  (ForgeTypeId)
      transitional → SpecType
      Revit ≤2021  → ParameterType  (enum)
    """
    st = p.StorageType

    try:
        from Autodesk.Revit.DB import SpecTypeId
        if st == StorageType.String:
            return SpecTypeId.String.Text
        if st == StorageType.Double:
            return SpecTypeId.Number
        if st == StorageType.Integer:
            try:
                return SpecTypeId.Int.Integer
            except Exception:
                try:
                    return SpecTypeId.Boolean.YesNo
                except Exception:
                    return SpecTypeId.Number
        if st == StorageType.ElementId:
            return SpecTypeId.String.Text
        return SpecTypeId.String.Text
    except Exception:
        pass

    try:
        from Autodesk.Revit.DB import SpecType
        if st == StorageType.String:
            return SpecType.String.Text
        if st == StorageType.Double:
            return SpecType.Number
        if st == StorageType.Integer:
            try:
                return SpecType.Int.Integer
            except Exception:
                return SpecType.Number
        if st == StorageType.ElementId:
            return SpecType.String.Text
        return SpecType.String.Text
    except Exception:
        pass

    try:
        from Autodesk.Revit.DB import ParameterType as PT
        if st == StorageType.String:
            return PT.Text
        if st == StorageType.Double:
            return PT.Number
        if st == StorageType.Integer:
            try:
                return PT.YesNo
            except Exception:
                return PT.Integer
        if st == StorageType.ElementId:
            return PT.Text
        return PT.Text
    except Exception:
        pass

    return None


def _serialize_value(p):
    """Return JSON-serializable payload for a parameter value."""
    st = p.StorageType
    if not p.HasValue:
        return {"storage": str(int(st)), "kind": "empty"}
    if st == StorageType.String:
        return {"storage": "string", "kind": "value", "value": p.AsString()}
    if st == StorageType.Double:
        return {"storage": "double", "kind": "value", "value": p.AsDouble()}
    if st == StorageType.Integer:
        return {"storage": "integer", "kind": "value", "value": p.AsInteger()}
    if st == StorageType.ElementId:
        eid = p.AsElementId()
        if eid is None or eid == ElementId.InvalidElementId:
            return {"storage": "elementid", "kind": "empty"}
        return {
            "storage": "elementid",
            "kind": "value",
            "value": eid.IntegerValue,
        }
    return {"storage": "string", "kind": "value", "value": p.AsValueString()}


def _param_record(p, scope):
    """Build a cache record for one parameter."""
    if p is None or not p.Definition:
        return None
    name = p.Definition.Name
    rec = {
        "scope": scope,
        "definition_name": name,
        "safe_name": _safe_param_name(name),
        "is_shared": p.IsShared,
        "value": _serialize_value(p),
    }
    try:
        idef = p.Definition
        if isinstance(idef, InternalDefinition) and idef.BuiltInParameter != BuiltInParameter.INVALID:
            rec["built_in"] = int(idef.BuiltInParameter)
    except Exception:
        pass
    try:
        if p.IsShared and isinstance(p.Definition, ExternalDefinition):
            rec["shared_guid"] = str(p.Definition.GUID)
    except Exception:
        pass
    return rec


def _collect_parameters_for_element(doc, elem):
    """Collect instance and type parameter records."""
    rows = []
    for p in elem.Parameters:
        if _should_skip_parameter(p):
            continue
        r = _param_record(p, "instance")
        if r:
            rows.append(r)

    tid = elem.GetTypeId()
    if tid and tid != ElementId.InvalidElementId:
        et = doc.GetElement(tid)
        if et:
            for p in et.Parameters:
                if _should_skip_parameter(p):
                    continue
                r = _param_record(p, "type")
                if r:
                    rows.append(r)
    return rows


def ensure_shared_parameter_file(app, extension_dir):
    lib_dir = os.path.join(extension_dir, "lib")
    if not os.path.isdir(lib_dir):
        os.makedirs(lib_dir)
    sp_path = os.path.join(lib_dir, SP_FILENAME)
    if not os.path.isfile(sp_path):
        with io.open(sp_path, "w", encoding="utf-8") as fh:
            fh.write("")
    cur = app.SharedParametersFilename
    if not cur or os.path.normpath(cur) != os.path.normpath(sp_path):
        app.SharedParametersFilename = sp_path
    return app.OpenSharedParameterFile()


def _get_or_create_group(sp_file):
    for g in sp_file.Groups:
        if g.Name == SP_GROUP_NAME:
            return g
    return sp_file.Groups.Create(SP_GROUP_NAME)


def _find_external_definition(group, safe_name):
    for d in group.Definitions:
        if d.Name == safe_name:
            return d
    return None


def _create_external_definition(app, group, safe_name, spec_type):
    opts = ExternalDefinitionCreationOptions(safe_name, spec_type)
    opts.Visible = True
    opts.UserModifiable = True
    return group.Definitions.Create(opts)


def _insert_group_for_binding(doc):
    try:
        from Autodesk.Revit.DB import GroupTypeId
        return GroupTypeId.Data
    except Exception:
        return None


def _merge_binding_core(doc, ext_def, categories_to_add, binding_class=None):
    """Merge categories into an existing or new binding.  Must run inside an
    open document Transaction.

    binding_class: InstanceBinding (default) or TypeBinding.
    """
    if binding_class is None:
        binding_class = InstanceBinding
    if not categories_to_add:
        return
    gtid = _insert_group_for_binding(doc)
    existing_def = None
    existing_binding = None
    itr = doc.ParameterBindings.ForwardIterator()
    while itr.MoveNext():
        d = itr.Key
        if d.Name != ext_def.Name:
            continue
        try:
            if isinstance(d, ExternalDefinition) and isinstance(ext_def, ExternalDefinition):
                if d.GUID == ext_def.GUID:
                    existing_def = d
                    existing_binding = itr.Current
                    break
        except Exception:
            existing_def = d
            existing_binding = itr.Current
            break

    new_set = CategorySet()
    if existing_binding is not None:
        try:
            old = existing_binding.Categories
            for c in old:
                new_set.Insert(c)
        except Exception:
            pass
    for c in categories_to_add:
        if c is not None:
            new_set.Insert(c)

    new_bind = binding_class(new_set)
    if existing_def is not None:
        if gtid is not None:
            doc.ParameterBindings.ReInsert(existing_def, new_bind, gtid)
        else:
            doc.ParameterBindings.ReInsert(existing_def, new_bind)
    else:
        if gtid is not None:
            doc.ParameterBindings.Insert(ext_def, new_bind, gtid)
        else:
            doc.ParameterBindings.Insert(ext_def, new_bind)


def _merge_instance_binding_core(doc, ext_def, categories_to_add):
    """Convenience wrapper — bind as InstanceBinding."""
    _merge_binding_core(doc, ext_def, categories_to_add, InstanceBinding)


def _ensure_shared_def_for_record(app, sp_file, group, rec, sample_param):
    """Return ExternalDefinition for a cache record, creating one if needed."""
    safe = rec.get("safe_name") or _safe_param_name(rec.get("definition_name", ""))
    existing = _find_external_definition(group, safe)
    if existing:
        return existing
    spec = _spec_type_for_parameter(sample_param)
    if spec is None:
        try:
            from Autodesk.Revit.DB import SpecType
            spec = SpecType.String.Text
        except Exception:
            return None
    return _create_external_definition(app, group, safe, spec)


def _copy_param_value(src, dst):
    """Copy value from src to dst when storage types match."""
    if not src or not dst:
        return False
    if src.IsReadOnly or dst.IsReadOnly:
        return False
    if not src.HasValue:
        return False
    if src.StorageType != dst.StorageType:
        return False
    st = src.StorageType
    try:
        if st == StorageType.String:
            return dst.Set(src.AsString())
        if st == StorageType.Double:
            return dst.Set(src.AsDouble())
        if st == StorageType.Integer:
            return dst.Set(src.AsInteger())
        if st == StorageType.ElementId:
            return dst.Set(src.AsElementId())
    except Exception:
        return False
    return False


def prepare_migration(doc, app, element_ids, script_path, extra_categories=None):
    """
    1) Snapshot parameters for each element (instance + type) to JSON.
    2) Ensure shared parameters exist for non-shared definitions; bind all relevant
       ExternalDefinitions (existing IFC shared + new) to every target category
       (GenericModel, Floors, Roofs, Ceilings + any extras) so parameters survive
       category changes.
    3) Copy values from original parameters into the new shared parameters (same element)
       so data lives in project parameters before you change category.
    """
    extension_dir = _extension_dir_from_script(script_path)
    path = cache_file_path(script_path)

    sp_file = ensure_shared_parameter_file(app, extension_dir)
    group = _get_or_create_group(sp_file)

    target_cats = []
    for bic in (
        BuiltInCategory.OST_GenericModel,
        BuiltInCategory.OST_Floors,
        BuiltInCategory.OST_Roofs,
        BuiltInCategory.OST_Ceilings,
    ):
        try:
            c = Category.GetCategory(doc, bic)
            if c is not None:
                target_cats.append(c)
        except Exception:
            pass
    if extra_categories:
        for c in extra_categories:
            if c is not None and c not in target_cats:
                target_cats.append(c)
    if not target_cats:
        raise RuntimeError("Could not resolve any target categories.")

    payload = {
        "version": 1,
        "elements": [],
    }

    unique_samples = {}

    for eid in element_ids:
        elem = doc.GetElement(eid)
        if elem is None:
            continue
        guid = get_ifc_guid(elem)
        rows = _collect_parameters_for_element(doc, elem)
        entry = {
            "element_id": eid.IntegerValue,
            "ifc_guid": guid,
            "parameters": rows,
        }
        payload["elements"].append(entry)

        for rec in rows:
            key = (rec.get("scope"), rec.get("safe_name"))
            if key not in unique_samples:
                p = None
                if rec["scope"] == "instance":
                    p = elem.LookupParameter(rec["definition_name"])
                else:
                    tid = elem.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        et = doc.GetElement(tid)
                        if et:
                            p = et.LookupParameter(rec["definition_name"])
                if p:
                    unique_samples[key] = (rec, p)

    instance_defs = {}
    type_defs = {}

    for key, pair in unique_samples.items():
        scope, _ = key
        rec, sample = pair
        idef = sample.Definition
        ext_def = None
        if isinstance(idef, ExternalDefinition):
            ext_def = idef
        else:
            ext_def = _ensure_shared_def_for_record(
                app, sp_file, group, rec, sample
            )
        if ext_def is None:
            continue
        try:
            dedup_key = str(ext_def.GUID)
        except Exception:
            dedup_key = ext_def.Name
        if scope == "type":
            type_defs[dedup_key] = ext_def
        else:
            instance_defs[dedup_key] = ext_def

    t_bind = Transaction(doc, "IFC migrate: bind shared parameters to all target categories")
    t_bind.Start()
    try:
        for _, ext_def in instance_defs.items():
            _merge_binding_core(doc, ext_def, target_cats, InstanceBinding)
        for _, ext_def in type_defs.items():
            _merge_binding_core(doc, ext_def, target_cats, TypeBinding)
        t_bind.Commit()
    except Exception as ex:
        t_bind.RollBack()
        raise

    try:
        doc.Regenerate()
    except Exception:
        pass

    t_copy = Transaction(doc, "IFC Floor migrate: copy values to shared params")
    t_copy.Start()
    try:
        for ent in payload["elements"]:
            elem = doc.GetElement(ElementId(ent["element_id"]))
            if elem is None:
                continue
            for rec in ent["parameters"]:
                if rec.get("is_shared"):
                    continue
                scope = rec.get("scope")
                src = None
                dst = None
                if scope == "instance":
                    src = elem.LookupParameter(rec["definition_name"])
                    dst = elem.LookupParameter(rec["safe_name"])
                elif scope == "type":
                    tid = elem.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        et = doc.GetElement(tid)
                        if et:
                            src = et.LookupParameter(rec["definition_name"])
                            dst = et.LookupParameter(rec["safe_name"])
                if src and dst:
                    _copy_param_value(src, dst)
        t_copy.Commit()
    except Exception:
        t_copy.RollBack()
        raise

    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    return path, len(payload["elements"])


def ensure_and_bind_shared_params(doc, app, element_ids, script_path, extra_categories=None):
    """Extend existing project parameter bindings to target categories.

    Looks up each parameter name on the source elements in ``doc.ParameterBindings``
    and merges Floors / Roofs / Ceilings / Generic Models into that binding.
    Does **not** create new shared parameters or write a JSON cache.

    ``app`` and ``script_path`` are unused but kept for API compatibility with callers.
    """
    _ = app, script_path

    target_cats = []
    for bic in (
        BuiltInCategory.OST_GenericModel,
        BuiltInCategory.OST_Floors,
        BuiltInCategory.OST_Roofs,
        BuiltInCategory.OST_Ceilings,
    ):
        try:
            c = Category.GetCategory(doc, bic)
            if c is not None:
                target_cats.append(c)
        except Exception:
            pass
    if extra_categories:
        for c in extra_categories:
            if c is not None and c not in target_cats:
                target_cats.append(c)
    if not target_cats:
        return

    all_bindings = []
    itr = doc.ParameterBindings.ForwardIterator()
    while itr.MoveNext():
        all_bindings.append((itr.Key.Name, itr.Key, itr.Current))

    all_names = set()
    for eid in element_ids:
        elem = doc.GetElement(eid)
        if elem is None:
            continue
        for p in elem.Parameters:
            if _should_skip_parameter(p):
                continue
            all_names.add(p.Definition.Name)
        tid = elem.GetTypeId()
        if tid and tid != ElementId.InvalidElementId:
            et = doc.GetElement(tid)
            if et:
                for p in et.Parameters:
                    if _should_skip_parameter(p):
                        continue
                    all_names.add(p.Definition.Name)

    if not all_names:
        return

    def _extend_one(defn, binding):
        """Add missing target categories to an existing binding.

        Uses 3-arg ReInsert with the definition's original GroupTypeId to
        preserve the parameter group.  Falls back to 2-arg for definitions
        without a group.  ParameterElement-backed (non-shared) definitions
        cannot be modified via the ParameterBindings API and are skipped.
        """
        try:
            old_cats = binding.Categories
        except Exception:
            return False
        existing_ids = set()
        for c in old_cats:
            try:
                existing_ids.add(c.Id.IntegerValue)
            except Exception:
                pass
        missing = []
        for c in target_cats:
            try:
                if c.Id.IntegerValue not in existing_ids:
                    missing.append(c)
            except Exception:
                pass
        if not missing:
            return False
        new_set = CategorySet()
        for c in old_cats:
            new_set.Insert(c)
        for c in missing:
            new_set.Insert(c)
        if isinstance(binding, InstanceBinding):
            new_bind = InstanceBinding(new_set)
        elif isinstance(binding, TypeBinding):
            new_bind = TypeBinding(new_set)
        else:
            return False

        original_gtid = None
        try:
            original_gtid = defn.GetGroupTypeId()
        except Exception:
            pass

        _result = False
        if original_gtid is not None:
            _result = doc.ParameterBindings.ReInsert(defn, new_bind, original_gtid)
        if not _result:
            _result = doc.ParameterBindings.ReInsert(defn, new_bind)
        return _result

    t_bind = Transaction(doc, "Byggstyrning: extend param bindings to target categories")
    t_bind.Start()
    try:
        for name, defn, binding in all_bindings:
            if name not in all_names:
                continue
            _extend_one(defn, binding)
        t_bind.Commit()
    except Exception:
        if t_bind.HasStarted():
            t_bind.RollBack()

    try:
        doc.Regenerate()
    except Exception:
        pass


def _default_family_load_options():
    from Autodesk.Revit.DB import IFamilyLoadOptions, FamilySource

    class FamilyLoadOptions(IFamilyLoadOptions):
        def OnFamilyFound(self, familyInUse, overwriteParameterValues):
            overwriteParameterValues[0] = True
            return True

        def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
            source[0] = FamilySource.Family
            overwriteParameterValues[0] = True
            return True

    return FamilyLoadOptions()


def collect_unique_families_from_selection(doc, element_ids):
    """Return unique Family objects from FamilyInstance selection (order preserved)."""
    seen = set()
    out = []
    for eid in element_ids:
        elem = doc.GetElement(eid)
        if elem is None:
            continue
        if not isinstance(elem, FamilyInstance):
            continue
        fam = elem.Symbol.Family
        fid = fam.Id.IntegerValue
        if fid not in seen:
            seen.add(fid)
            out.append(fam)
    return out


def family_is_inplace(family):
    """True if Revit in-place family (EditFamily / API category change not supported)."""
    try:
        return bool(family.IsInPlace)
    except Exception:
        return False


def partition_families_inplace(families):
    """Split into (in_place_families, loadable_families)."""
    inplace = []
    loadable = []
    for fam in families:
        if family_is_inplace(fam):
            inplace.append(fam)
        else:
            loadable.append(fam)
    return inplace, loadable


def change_family_category_to_floor(doc, family):
    """
    For a loadable (non–in-place) family: open family document in memory (not the
    interactive editor UI), set FamilyCategory to Floor, LoadFamily back.

    Revit does not support Document.EditFamily for in-place families — do not pass those.
    Must not be called inside an active project transaction.
    """
    if family_is_inplace(family):
        raise RuntimeError(
            "In-place families cannot change category via the API (EditFamily is unsupported)."
        )
    load_opts = _default_family_load_options()
    family_doc = doc.EditFamily(family)
    if family_doc is None:
        raise RuntimeError("EditFamily returned no document — family may be read-only or unsupported.")

    t = Transaction(family_doc, "IFC Floor migrate: set category to Floor")
    t.Start()
    try:
        cat_floor = Category.GetCategory(family_doc, BuiltInCategory.OST_Floors)
        if cat_floor is None:
            raise RuntimeError("Could not resolve BuiltInCategory.OST_Floors in the family document.")
        fam = family_doc.OwnerFamily
        fam.FamilyCategory = cat_floor
        t.Commit()
    except Exception:
        if t.HasStarted():
            t.RollBack()
        try:
            family_doc.Close(False)
        except Exception:
            pass
        raise

    try:
        family_doc.LoadFamily(doc, load_opts)
    finally:
        try:
            family_doc.Close(False)
        except Exception:
            pass

    try:
        doc.Regenerate()
    except Exception:
        pass


def read_ifc_guids_from_cache(script_path):
    path = cache_file_path(script_path)
    if not os.path.isfile(path):
        return []
    with io.open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    guids = []
    for ent in payload.get("elements", []):
        g = ent.get("ifc_guid")
        if g:
            guids.append(g)
    return guids


def find_floor_instance_ids_by_ifc_guids(doc, guids):
    """Return ElementIds of floor instances whose IFC GUID is in guids."""
    if not guids:
        return []
    want = set(guids)
    floor_cat = ElementId(BuiltInCategory.OST_Floors)
    ids = []
    for e in FilteredElementCollector(doc).OfCategoryId(floor_cat).WhereElementIsNotElementType():
        g = get_ifc_guid(e)
        if g and g in want:
            ids.append(e.Id)
    return ids


def _collect_inplace_instance_ids(doc, element_ids):
    """Return list of ElementId for in-place FamilyInstance elements."""
    out = []
    for eid in element_ids:
        elem = doc.GetElement(eid)
        if elem is None:
            continue
        if not isinstance(elem, FamilyInstance):
            continue
        if family_is_inplace(elem.Symbol.Family):
            out.append(eid)
    return out


def migrate_prepare_change_category_and_restore(doc, app, element_ids, script_path):
    """
    Full automated path for both loadable and in-place families.

    Loadable: EditFamily in memory → set Floor category → LoadFamily back.
    In-place: per element, IFC Predefined Type → template .rfa → geometry → load →
              place instance → copy IFC GUID (cache already written once above).
    Finally: restore cached parameters on all matched instances (including new IDs).

    Returns dict with keys:
      path, n_prepared, families_changed, families_inplace_count,
      inplace_converted, inplace_errors, floor_ids_found,
      restore_ok, restore_fail, restore_skipped, applied_labels,
      category_skipped_reason (str or None)
    """
    path, n = prepare_migration(doc, app, element_ids, script_path)
    families = collect_unique_families_from_selection(doc, element_ids)
    category_skipped_reason = None

    if not families:
        category_skipped_reason = (
            "No loadable family instances in the selection (e.g. DirectShape only). "
            "Cache was written; change category manually if needed, then run this button "
            "with Floor selected to restore."
        )
        return {
            "path": path,
            "n_prepared": n,
            "families_changed": 0,
            "families_inplace_count": 0,
            "inplace_converted": 0,
            "inplace_skipped": 0,
            "inplace_errors": [],
            "floor_ids_found": 0,
            "restore_ok": 0,
            "restore_fail": 0,
            "restore_skipped": 0,
            "applied_labels": [],
            "category_skipped_reason": category_skipped_reason,
        }

    inplace_fams, loadable_fams = partition_families_inplace(families)
    families_changed = 0
    for fam in loadable_fams:
        change_family_category_to_floor(doc, fam)
        families_changed += 1

    inplace_converted = 0
    inplace_skipped = 0
    inplace_errors = []
    new_converted_ids = []

    if inplace_fams:
        import inplace_to_loadable_floor as ip2l

        inplace_eids = _collect_inplace_instance_ids(doc, element_ids)
        for ip_eid in inplace_eids:
            inst = doc.GetElement(ip_eid)
            if inst is None:
                continue
            pdt = ip2l.get_ifc_predefined_type(doc, inst)
            mapping = ip2l.PREDEFINED_TYPE_MAP.get((pdt or "").upper())
            if mapping is None:
                inplace_skipped += 1
                continue
            tpl_name, tgt_cat = mapping
            tpl_path = ip2l._find_template(script_path, tpl_name)
            if not tpl_path:
                inplace_errors.append(
                    "Template '{0}' not found (IFC Predefined Type: {1}).".format(
                        tpl_name, pdt or "(none)"
                    )
                )
                continue
            r = ip2l._convert_single_inplace(doc, app, inst, tpl_path, tgt_cat)
            if r.get("success"):
                inplace_converted += 1
                nid = r.get("new_element_id")
                if nid is not None:
                    new_converted_ids.append(ElementId(nid))
            else:
                inplace_errors.append(r.get("message", "Unknown error"))

    guids = read_ifc_guids_from_cache(script_path)
    floor_ids = find_floor_instance_ids_by_ifc_guids(doc, guids)
    for fid in new_converted_ids:
        if fid not in floor_ids:
            floor_ids.append(fid)

    if not floor_ids:
        ok = fail = skipped = 0
        labels = []
        if not category_skipped_reason:
            category_skipped_reason = (
                "No Floor instances matched cached IFC GUIDs yet. "
                "Select the Floor elements and run this button again (restore)."
            )
    else:
        ok, fail, skipped, labels = restore_from_cache(doc, floor_ids, script_path)

    if inplace_errors and not category_skipped_reason:
        category_skipped_reason = (
            "Some in-place conversions failed:\n"
            + "\n".join("  - {0}".format(e) for e in inplace_errors)
        )

    return {
        "path": path,
        "n_prepared": n,
        "families_changed": families_changed,
        "families_inplace_count": len(inplace_fams),
        "inplace_converted": inplace_converted,
        "inplace_skipped": inplace_skipped,
        "inplace_errors": inplace_errors,
        "floor_ids_found": len(floor_ids),
        "restore_ok": ok,
        "restore_fail": fail,
        "restore_skipped": skipped,
        "applied_labels": labels,
        "category_skipped_reason": category_skipped_reason,
    }



def _lookup_parameter_for_record(elem, etype, rec, scope):
    """Resolve parameter on instance or type; try definition_name then safe_name (Floor often keeps shared names)."""
    name = rec.get("definition_name")
    safe = rec.get("safe_name")
    if scope == "instance":
        target = elem.LookupParameter(name) if name else None
        if target is None and safe and safe != name:
            target = elem.LookupParameter(safe)
        return target
    if scope == "type" and etype is not None:
        target = etype.LookupParameter(name) if name else None
        if target is None and safe and safe != name:
            target = etype.LookupParameter(safe)
        return target
    return None


def _apply_value(p, blob):
    if p is None or blob is None:
        return False
    if blob.get("kind") != "value":
        return False
    st = p.StorageType
    try:
        if st == StorageType.String:
            return p.Set(blob.get("value", ""))
        if st == StorageType.Double:
            return p.Set(float(blob["value"]))
        if st == StorageType.Integer:
            v = blob["value"]
            if isinstance(v, float):
                v = int(v)
            return p.Set(int(v))
        if st == StorageType.ElementId:
            return p.Set(ElementId(int(blob["value"])))
    except Exception:
        return False
    return False


def restore_from_cache(doc, element_ids, script_path):
    """Apply cached values to current selection (match by IFC GUID, then element id).

    Returns (applied_count, elements_no_match, skipped_value_count, applied_labels).
    skipped_value_count counts cache rows that had a stored value but no target param or Set failed.
    applied_labels is a list of short strings for logging (definition_name or safe_name used).
    """
    path = cache_file_path(script_path)
    if not os.path.isfile(path):
        raise RuntimeError("Cache file not found: {0}".format(path))

    with io.open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    by_guid = {}
    by_id = {}
    for ent in payload.get("elements", []):
        g = ent.get("ifc_guid")
        if g:
            by_guid[g] = ent
        by_id[ent.get("element_id")] = ent

    t = Transaction(doc, "IFC Floor migrate: restore parameters")
    t.Start()
    ok = 0
    fail = 0
    skipped = 0
    applied_labels = []
    try:
        for eid in element_ids:
            elem = doc.GetElement(eid)
            if elem is None:
                fail += 1
                continue
            guid = get_ifc_guid(elem)
            ent = None
            if guid and guid in by_guid:
                ent = by_guid[guid]
            if ent is None:
                ent = by_id.get(eid.IntegerValue)
            if not ent:
                fail += 1
                continue
            etype = None
            tid = elem.GetTypeId()
            if tid and tid != ElementId.InvalidElementId:
                etype = doc.GetElement(tid)
            for rec in ent.get("parameters", []):
                scope = rec.get("scope")
                blob = rec.get("value")
                if blob is None or blob.get("kind") != "value":
                    continue
                target = None
                if scope == "instance":
                    target = _lookup_parameter_for_record(elem, None, rec, "instance")
                elif scope == "type":
                    target = _lookup_parameter_for_record(elem, etype, rec, "type")
                if target is None:
                    skipped += 1
                    continue
                result = _apply_value(target, blob)
                if result:
                    ok += 1
                    label = rec.get("definition_name") or rec.get("safe_name") or "?"
                    applied_labels.append(
                        "{0} ({1})".format(label, scope)
                    )
                else:
                    skipped += 1
        t.Commit()
    except Exception:
        t.RollBack()
        raise

    return ok, fail, skipped, applied_labels
