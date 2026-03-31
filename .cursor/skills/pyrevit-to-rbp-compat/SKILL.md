---
name: pyrevit-to-rbp-compat
description: >-
  Adapts PyRevit IronPython scripts to run under Revit Batch Processor (BatchRvt/RBP):
  shared process_open_document pattern, revit_script_util adapters, IronPython quirks
  (__file__, sys.path, lazy pyrevit), RW_RESULT sidecars, PowerShell launchers, and
  pipeline wiring (powershell command_type, RevitVersion alias). Use when porting
  pyrevit run scripts to RBP, debugging detach/repath or analytics task scripts, or
  integrating new BatchRvt task scripts with RevitWorkerApp.
---

# PyRevit-to-RBP compatibility

Use this when moving logic from **pyRevit CLI** (`pyrevit run …`) to **Revit Batch Processor** (`BatchRvt.exe` + task script). The worker still invokes **PowerShell**; RBP is not a separate `command_type` in `TaskRunner.cs`.

## Mental model

| Aspect | PyRevit path | RBP path |
|--------|--------------|----------|
| Who opens the model | `HOST_APP.app.OpenDocumentFile` (or fallbacks) | BatchRvt (`--detach`, `--worksets`, etc.) |
| Python entry | `detach_repath.py` → `process_model()` | `detach_repath_rbp.py` → thin adapter |
| `Document` from | Return value of `OpenDocumentFile` | `revit_script_util.GetScriptDocument()` |
| Shared work | `process_open_document(doc, …)` | Same function |

## 1. Refactor: one shared function

1. Move all post-open logic into **`process_open_document(doc, model_path_abs, …, open_mode, extra_rw_result_paths=None)`** (or equivalent name).
2. **PyRevit-only** entry (`process_model`): normalize path, `BasicFileInfo`, open with fallbacks, then call `process_open_document`.
3. **RBP-only** entry: new file (e.g. `*_rbp.py`) that imports `revit_script_util`, gets `doc` from `GetScriptDocument()`, path from `GetRevitFilePath()`, then calls **`process_open_document`** with `open_mode="rbp"` (or `"rbp_analytics"`).

Do **not** import `pyrevit` at module top level in the shared module; RBP does not ship pyRevit.

## 2. IronPython / RBP quirks

Apply these in the shared module and RBP adapter:

1. **`__file__` may be undefined** — use `_script_base_dir()` with `try: dirname(abspath(__file__))` except `NameError: return getcwd()`.
2. **`sys.path`** — insert `_script_dir` before `from model_audit import …` or other local imports.
3. **Lazy pyRevit** — `from pyrevit import HOST_APP` only inside the PyRevit-specific function.
4. **RBP imports** — `import revit_script_util` and `from revit_script_util import Output` only in the `*_rbp.py` task script.
5. **JSON for workers/DB** — sanitize byte strings (`sanitize_for_json`), `json.dumps(..., ensure_ascii=False)`, write with `io.open` / `codecs.open` UTF-8.

See [reference.md](reference.md) for minimal snippets.

## 3. RW_RESULT: stdout vs sidecar

`RevitWorkerApp` parses **`RW_RESULT:`** from the **PowerShell process stdout** (see `TaskRunner`).

- **PyRevit**: `print("RW_RESULT:" + json)` reaches the worker.
- **RBP**: BatchRvt stdout does not reliably surface as the PS1 stdout line the worker expects. **Write the same JSON to disk** (sidecar), then have the **launcher PS1** read the file and emit `Write-Output "RW_RESULT:$json"`.

Typical sidecars:

- Next to model: `<model>.rbp_rw_result.json`
- Optional temp: set **`RBP_SIDECAR_PATH`** so the launcher always has a known path (pre-flight write a stub JSON with `"error": "RBP task did not complete"` before BatchRvt so a failed run still leaves parseable output).

## 4. PowerShell launcher responsibilities

Canonical pattern on this host: [`/home/jonatan/INTERAXO/Run-RBPDetachRepath.ps1`](/home/jonatan/INTERAXO/Run-RBPDetachRepath.ps1) (adjust to your deploy path).

1. Resolve **`BatchRvt.exe`** — `%LOCALAPPDATA%\RevitBatchProcessor\BatchRvt.exe`; fail fast with `RW_RESULT:` JSON if missing.
2. **Sync `*.py`** from INTERAXO UNC to a **local** folder (e.g. under pyRevit extensions) so IronPython resolves imports reliably.
3. **`--task_script`** path to the RBP adapter, **`--file_list`** one model per line, **`--detach`**, **`--worksets open_all`**, **`--revit_version`**, **`--log_folder`**.
4. Set env vars: `ANALYTICS_ONLY`, `RBP_SIDECAR_PATH`, job-specific vars (`RBP_EXPORT_DIR`, etc.).
5. After BatchRvt: **read sidecar with UTF-8** (`Get-Content -Encoding utf8`), emit **`RW_RESULT:`**, optionally cleanup.
6. Optional: **`RevitBackupCleanup.ps1`** to remove `.0001.rvt` incremental backups.

## 5. Pipeline integration checklist

- **API / worker** — `command_type: **powershell**`, `script_path` = UNC to your PS1, `model_path`, `revit_version` / `revit_year` as today.
- **PS1 parameter binding** — worker may pass **`-RevitVersion`**. On the `[int]$RevitYear` parameter add **`[Alias("RevitVersion")]`** so both names work.
- **n8n** — point submit node to the new PS1; update **`meta.commandtype`** (e.g. `RBP_DETACH_REPATH`) and any “Track pyRevit” labels to RBP for clarity.
- **Dashboard / job history** — match `rbp`, legacy `pyrevit`, and `powershell` where old jobs exist; read `command_type` from **`args`** as well as **`meta`** if enriched at enqueue.

## 6. Reference implementations in-repo

| Role | Example path (home layout) |
|------|------------------------------|
| Shared pipeline + PyRevit open | `INTERAXO/detach_repath.py` |
| RBP adapter | `INTERAXO/detach_repath_rbp.py` |
| Launcher | `INTERAXO/Run-RBPDetachRepath.ps1` |
| IFC self-heal (RBP-only parallel to pyRevit) | `INTERAXO/selfheal_ifc_export.py` + `Run-RBPSelfhealExport.ps1` |
| Analytics via RBP | `ifcpipeline/dashboard/routers/revit_analytics.py` → `Run-RBPDetachRepath.ps1 -AnalyticsOnly` |

## 7. Architecture note

Keep **RevitWorkerApp** as the queue/orchestrator; use **RBP as an execution engine** (BatchRvt from PowerShell). Do not replace the worker with BatchRvt alone.

## Additional detail

- Full templates: [reference.md](reference.md)
