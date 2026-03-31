# In-place → loadable conversion (archived kit)



2026-03 — we no longer runs this step in the main pipeline. This folder bundles **family template RFAs** and the **retired pyRevit / RBP entry scripts** so they stay in one place.



## Contents



| Path | Role |

|------|------|

| `Floor Family Template.rfa`, `Roofs Family Template.rfa`, `Ceiling Family Template.rfa` (deploy beside the extension) | Floor, roof, and ceiling family templates used by `lib/revit/inplace_to_loadable_floor.py` (`PREDEFINED_TYPE_MAP`). |



Shared logic remains in `lib/revit/inplace_to_loadable_floor.py` and `lib/revit/param_cache_floor.py`.



## Templates at runtime



`_find_template` resolves files under the extension repository root or the parent of that folder. **Copy** the three `.rfa` files next to the live extension root (same folder as `lib/`, `scripts/`, etc.) before running conversion.



## Reviving pyRevit



See `archive/pyrevit-ribbon-scripts/NOTES.md` — copy `script.py` into a real `.pushbutton` folder, fix `sys.path` / `ext_dir` depth for your tab layout, and ensure `lib/` is importable.



## Reviving RBP



Copy `convert_inplace_rbp.py` to `scripts/rbp/convert_inplace/` (or your BatchRvt tasks folder), wire the launcher, and ensure the `.rfa` files are deployed beside the extension as above.

