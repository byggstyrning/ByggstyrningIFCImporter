# Reference: templates and snippets

Use these as copy-paste starting points when adding a new RBP task script next to an existing PyRevit script.

## RBP task script skeleton (`your_task_rbp.py`)

```python
# -*- coding: utf-8 -*-
"""RBP task script — calls shared logic; BatchRvt already opened the document."""

from __future__ import print_function

import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")
# Add RevitAPIUI etc. only if needed

import revit_script_util
from revit_script_util import Output

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.getcwd()
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# Import shared symbols from your main module (no pyrevit at import time)
from your_main_module import process_open_document, Logger, _normalize_model_path_for_revit

log = Logger()
doc = revit_script_util.GetScriptDocument()
raw_path = revit_script_util.GetRevitFilePath() or ""
model_path_abs = _normalize_model_path_for_revit(raw_path)

# Optional: env-driven flags
analytics_only = os.environ.get("ANALYTICS_ONLY", "").lower() in ("1", "true", "yes")

# Build ModelPath / workshared flags as your shared function requires
from Autodesk.Revit.DB import BasicFileInfo, ModelPathUtils

try:
    fi = BasicFileInfo.Extract(model_path_abs)
    is_workshared_file = fi.IsWorkshared
except Exception:
    is_workshared_file = False
try:
    doc_is_workshared = doc.IsWorkshared
except Exception:
    doc_is_workshared = is_workshared_file

model_path_obj = ModelPathUtils.ConvertUserVisiblePathToModelPath(model_path_abs)
extra_paths = []
_sc = os.environ.get("RBP_SIDECAR_PATH", "").strip()
if _sc:
    extra_paths.append(_sc)

_ok = process_open_document(
    doc,
    model_path_abs,
    analytics_only,
    log,
    is_workshared_file,
    doc_is_workshared,
    "rbp",
    model_path_obj,
    extra_rw_result_paths=extra_paths or None,
)

Output('Log File: "{}"'.format(log.log_file))
```

## Shared module: `_script_base_dir` and lazy pyRevit

```python
def _script_base_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()

def process_model(model_path, analytics_only=False):
    from pyrevit import HOST_APP
    # ... open_document_with_fallbacks(HOST_APP.app, ...) ...
    return process_open_document(doc, ...)
```

## Emitting RW_RESULT with extra sidecar paths

Pattern from `detach_repath.py` / `_emit_rw_result`:

- Always `print("RW_RESULT:" + rw_json)` for any host that captures stdout.
- If `extra_rw_result_paths` is set, also write the **same** JSON to those paths (UTF-8).
- For analytics-only mode, you may skip writing next to the model; still honor RBP sidecars.

## PowerShell launcher skeleton

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelPath,
    [Parameter(Mandatory = $false)]
    [Alias("RevitVersion")]
    [int]$RevitYear = 2025,
    [string]$JobId = "",
    [switch]$AnalyticsOnly
)

$BatchRvtExe = Join-Path $env:LOCALAPPDATA "RevitBatchProcessor\BatchRvt.exe"
if (-not (Test-Path $BatchRvtExe)) {
    $fallback = @{ error = "BatchRvt.exe not found"; host = "rbp" } | ConvertTo-Json -Compress
    Write-Output "RW_RESULT:$fallback"
    exit 1
}

# Sync *.py from UNC to local dir, then:
$TaskScript = Join-Path $LocalScriptDir "your_task_rbp.py"
$FileListPath = Join-Path $TempDir "filelist_$JobId.txt"
[System.IO.File]::WriteAllText($FileListPath, $ModelPath, (New-Object System.Text.UTF8Encoding $false))

if ($AnalyticsOnly) { $env:ANALYTICS_ONLY = "1" } else { Remove-Item Env:\ANALYTICS_ONLY -ErrorAction SilentlyContinue }

$preflightSidecar = Join-Path $TempDir "$modelBaseName.rbp_rw_result.json"
$env:RBP_SIDECAR_PATH = $preflightSidecar
$preflightJson = @{ error = "RBP task did not complete"; host = "rbp"; preflight = $true } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($preflightSidecar, $preflightJson, (New-Object System.Text.UTF8Encoding $false))

& $BatchRvtExe --task_script $TaskScript --file_list $FileListPath `
    --detach --worksets open_all --revit_version $RevitYear --log_folder $LogFolder

# Resolve sidecar (model dir, detached name variant, or preflight)
$rwJson = Get-Content -LiteralPath $rwFile -Raw -Encoding utf8 -ErrorAction SilentlyContinue
if ($rwJson) { Write-Output "RW_RESULT:$rwJson" }
Remove-Item Env:\RBP_SIDECAR_PATH -ErrorAction SilentlyContinue
```

## API enqueue example (analytics / generic RBP)

```bash
curl -s -X POST "http://localhost:8000/revit/execute" \
  -H "X-API-Key: $IFC_PIPELINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "command_type": "powershell",
    "script_path": "\\\\server\\share\\INTERAXO\\Run-RBPDetachRepath.ps1",
    "model_path": "\\\\server\\share\\...\\model.rvt",
    "arguments": ["-AnalyticsOnly"],
    "timeout_seconds": 3600,
    "meta": {"commandtype": "RBP_DETACH_REPATH", "triggered_by": "manual"}
  }'
```

## Self-heal IFC (separate parallel script)

`selfheal_ifc_export.py` is **not** a thin wrapper around `export_ifc.py`; it is a full RBP task script using env vars (`RBP_EXPORT_DIR`, `RBP_IFC_FILENAME`, …). Use that pattern when the PyRevit script cannot create views or fails on open—implement RBP-native Revit API logic instead of forcing one shared file.
