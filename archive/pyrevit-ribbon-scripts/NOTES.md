# PyRevit ribbon `script.py` (retired from active tree)

2026-03 — These files were **interactive pyRevit** wrappers next to the BatchRvt task scripts. The bygg IFC workflow is **Revit Batch Processor + `*_rbp.py` only**; we do not ship or maintain a pyRevit extension tab for this repo.

## What was archived

| File (historical layout) | Role |
|--------------------------|------|
| `setup/script.py` | `forms.alert` UI after `bygg_setup_core.run_full_setup` |

**In-place conversion** (pyRevit `script.py`, RBP `convert_inplace_rbp.py`, and the three family template `.rfa` files) now lives in one place: **`archive/inplace-convert-kit/`** (see `NOTES.md` there).

Shared logic remains in `lib/` (`bygg_setup_core`, `inplace_to_loadable_floor`, etc.). Active RBP entry points: `scripts/rbp/setup/setup_model_rbp.py`, `scripts/rbp/merge_rooms/merge_rooms_rbp.py`, optional `scripts/rbp/publish_acc/publish_acc_rbp.py`.

## If you revive these for pyRevit

1. Copy the `script.py` files into a real **`.pushbutton`** folder under your extension’s **`*.tab/`** (not under `scripts/rbp/`).
2. Fix **`sys.path` / `ext_dir`**: dirname depth depends on ribbon folder depth (typically three levels from `.pushbutton` to extension root, not four).
3. Ensure `lib/` is on the pyRevit extension path or duplicate the path logic used elsewhere in your extension.
