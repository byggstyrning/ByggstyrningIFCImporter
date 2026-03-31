<#
.SYNOPSIS
    IFC-to-Revit automation pipeline (main IFC via BatchRvt + 2 RBP runs).

.DESCRIPTION
    Automates the checklist *Uppdatera modell till Revit* (IFC deliverables to Revit):

    Phase 1 -- IFC to RVT
        Main IFC (1a): Improved IFC Import (BatchRvt + graphisoft_import_rbp.py +
        ByggstyrningIFCImporter: Revit OpenIFCDocument + Graphisoft CorrectIFCImport).
        Rooms IFC (1b): default xBIM (BatchRvt + xbim_rooms_import_rbp.py +
        ByggstyrningRoomImporter). Use -RoomsImporter Graphisoft for the same Graphisoft
        stack as 1a.  A small seed .RVT is the BatchRvt file list (see -RbpSeedRvt).

    Phase 2 -- RBP runs (BatchRvt.exe)
        Run 1  (setup_model_rbp.py)   -- purge IFC openings, worksets, rotate,
                                          True North, link Config, acquire coords.
        Run 2  (merge_rooms_rbp.py)   -- open rooms RVT, copy rooms + separation
                                          lines into main model, close rooms model.

    Optional Phase 3 -- ACC cloud publish (publish_acc_rbp.py)
        When -PublishAcc is set, opens the finished main model and calls
        Document.SaveAsCloudModel to Autodesk Docs / ACC (IDs via parameters;
        no name resolution in this script).

    Each run writes a JSON sidecar; the launcher reads it and emits RW_RESULT.

.PARAMETER MainIfcPath
    Absolute path to the main architecture .IFC (0001_00).
    When provided, Phase 1 converts it to .RVT via BatchRvt (main IFC).
    Mutually exclusive with -MainModelPath (one of them is required).

.PARAMETER RoomsIfcPath
    Absolute path to the rooms .IFC (0003_00).
    When provided, Phase 1b converts it to .RVT (default: xBIM ByggstyrningRoomImporter;
    use -RoomsImporter Graphisoft to match the main IFC import). Mutually exclusive
    with -RoomsModelPath.

.PARAMETER MainModelPath
    Absolute path to the main architecture .RVT (already converted).
    Use this when Phase 1 was already completed or -SkipImport is set.

.PARAMETER RoomsModelPath
    Absolute path to the rooms .RVT (already converted).
    Required unless -SkipRooms is set.

.PARAMETER RevitYear
    Revit version year (default: 2025).

.PARAMETER JobId
    Optional job correlation ID; auto-generated if omitted.

.PARAMETER SkipImport
    Skip Phase 1 (IFC import).  Requires -MainModelPath.

.PARAMETER SkipRooms
    Skip Run 2 (rooms merge). Use when only re-running setup, or with -SkipSetup for ACC
    publish-only on an already-prepared model.

.PARAMETER SkipSetup
    Skip Run 1 (setup_model_rbp.py). Use when the main .rvt is already prepared and you
    only need merge and/or -PublishAcc (e.g. publish-only with -SkipImport
    -SkipRooms -SkipSetup -PublishAcc).

.PARAMETER RbpSeedRvt
    Absolute path to a minimal host .RVT opened by BatchRvt before the
    Graphisoft import task runs. Default: demo\in\empty_R{RevitYear}.rvt (e.g. empty_R2025.rvt);
    override with this parameter or BYGG_RBP_SEED_RVT (see docs\empty-rvt-seed-README.txt).

.PARAMETER ImportRoomsIfcOnly
    Run only the rooms IFC -> RVT import (same step as full pipeline Phase 1b), then exit.
    Default: demo\in\A1_2b_BIM_XXX_0003_00.ifc to demo\out\roomsdemo.rvt.
    Importer is chosen with -RoomsImporter (default Xbim; Graphisoft for ArchiCAD
    plugin stack same as main).

.PARAMETER RoomsImporter
    Which engine imports the rooms IFC: Xbim (ByggstyrningRoomImporter + native Revit rooms,
    default) or Graphisoft (OpenIFCDocument + CorrectIFCImport, same as main IFC).

.PARAMETER PublishAcc
    After Phase 2, publish the workshared main model to ACC using SaveAsCloudModel.
    Requires -AccAccountId, -AccProjectId, -AccFolderId, and either -CloudModelName or
    -MainIfcPath (for default name {base}.ifc_yyyy-MM-dd.rvt). Hub/project GUIDs may
    use a b. prefix; it is stripped before parsing.

.PARAMETER AccAccountId
    ACC hub (account) GUID string for SaveAsCloudModel.

.PARAMETER AccProjectId
    ACC project GUID string for SaveAsCloudModel.

.PARAMETER AccFolderId
    Data Management folder id string (not a path) for SaveAsCloudModel.

.PARAMETER CloudModelName
    Optional cloud file name (e.g. MyModel.ifc_2026-03-28.rvt). When omitted with
    -PublishAcc, the name is derived from -MainIfcPath.

.EXAMPLE
    # Full pipeline from IFC to finished Revit model (run from repo root)
    .\powershell\Run-ByggPipelineSetup.ps1 `
        -MainIfcPath  "demo\in\A1_2b_BIM_XXX_0001_00.ifc" `
        -RoomsIfcPath "demo\in\A1_2b_BIM_XXX_0003_00.ifc" `
        -RevitYear 2025

.EXAMPLE
    # Skip import if .RVT files already exist
    .\powershell\Run-ByggPipelineSetup.ps1 `
        -MainModelPath  "demo\out\A1_2b_BIM_XXX_0001_00.rvt" `
        -RoomsModelPath "demo\out\A1_2b_BIM_XXX_0003_00.rvt" `
        -SkipImport

.EXAMPLE
    # Debug: only import rooms IFC to demo\out\roomsdemo.rvt (open in Revit to check rooms)
    .\powershell\Run-ByggPipelineSetup.ps1 -ImportRoomsIfcOnly
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$MainIfcPath = "",

    [Parameter(Mandatory = $false)]
    [string]$RoomsIfcPath = "",

    [Parameter(Mandatory = $false)]
    [string]$MainModelPath = "",

    [Parameter(Mandatory = $false)]
    [string]$RoomsModelPath = "",

    [Parameter(Mandatory = $false)]
    [Alias("RevitVersion")]
    [int]$RevitYear = 2025,

    [Parameter(Mandatory = $false)]
    [string]$JobId = "",

    [Parameter(Mandatory = $false)]
    [switch]$SkipImport,

    [Parameter(Mandatory = $false)]
    [switch]$SkipRooms,

    [Parameter(Mandatory = $false)]
    [switch]$SkipSetup,

    [Parameter(Mandatory = $false)]
    [string]$RbpSeedRvt = "",

    [Parameter(Mandatory = $false)]
    [switch]$ImportRoomsIfcOnly,

    [Parameter(Mandatory = $false)]
    [ValidateSet("Graphisoft", "Xbim")]
    [string]$RoomsImporter = "Xbim",

    [Parameter(Mandatory = $false)]
    [switch]$PublishAcc,

    [Parameter(Mandatory = $false)]
    [string]$AccAccountId = "",

    [Parameter(Mandatory = $false)]
    [string]$AccProjectId = "",

    [Parameter(Mandatory = $false)]
    [string]$AccFolderId = "",

    [Parameter(Mandatory = $false)]
    [string]$CloudModelName = ""
)

$ErrorActionPreference = "Stop"

# Repository root (this script lives in .\powershell\)
$RepoRoot = Split-Path $PSScriptRoot -Parent
$JournalTemplatesDir = Join-Path $RepoRoot "archive\journal-automation\journal_templates"

# ---------------------------------------------------------------------------
# Job setup
# ---------------------------------------------------------------------------
if (-not $JobId) { $JobId = [guid]::NewGuid().ToString('N').Substring(0, 8) }
$env:IFC_PIPELINE_JOB_ID = $JobId

$TempDir = Join-Path $env:TEMP "rbp_bygg_pipeline\$JobId"
if (-not (Test-Path $TempDir)) { New-Item -ItemType Directory -Path $TempDir -Force | Out-Null }

if ([string]::IsNullOrWhiteSpace($RbpSeedRvt)) {
    if (-not [string]::IsNullOrWhiteSpace($env:BYGG_RBP_SEED_RVT)) {
        $RbpSeedRvt = $env:BYGG_RBP_SEED_RVT
    } else {
        $demoInSeed = Join-Path $RepoRoot "demo\in"
        $RbpSeedRvt = Join-Path $demoInSeed "empty_R$RevitYear.rvt"
    }
}
$RbpSeedRvt = [System.IO.Path]::GetFullPath($RbpSeedRvt)

$DiagLog = Join-Path $TempDir "diag.log"
$OverallResult = @{
    job_id       = $JobId
    main_ifc     = $MainIfcPath
    rooms_ifc    = $RoomsIfcPath
    main_model   = $MainModelPath
    rooms_model  = $RoomsModelPath
    steps        = @{}
    error        = $null
}

function Diag($msg) {
    $ts = Get-Date -Format "HH:mm:ss.fff"
    $line = "[$ts] $msg"
    $line | Out-File -Append -FilePath $DiagLog -Encoding UTF8
    Write-Host $line
}

function EmitRwResult($data) {
    $json = $data | ConvertTo-Json -Compress -Depth 10
    Write-Output "RW_RESULT:$json"
}

function FailFast($msg, $extraData = @{}) {
    Diag "FAIL-FAST: $msg"
    $OverallResult.error = $msg
    foreach ($k in $extraData.Keys) { $OverallResult[$k] = $extraData[$k] }
    EmitRwResult $OverallResult
    exit 1
}

function Get-NormalizedAccGuidString {
    <#
    .SYNOPSIS
        Strip optional b. prefix (Data Management) and validate GUID for SaveAsCloudModel.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Raw,
        [Parameter(Mandatory)]
        [string]$Label
    )
    $t = $Raw.Trim()
    if ($t.StartsWith("b.", [System.StringComparison]::OrdinalIgnoreCase)) {
        $t = $t.Substring(2)
    }
    try {
        [void][guid]::Parse($t)
    } catch {
        FailFast "Invalid $Label ACC GUID (after optional b. strip): $Raw"
    }
    return $t
}

function Wait-RevitAfterBatchRvtForJournal {
    <#
    .SYNOPSIS
        Gives BatchRvt's Revit time to exit before the next Revit session (Phase 1b or Phase 2).
    #>
    Diag "Waiting for Revit to release after BatchRvt before next step..."
    Start-Sleep -Seconds 15
    $waitTries = 0
    $stillRevit = $null
    while ($waitTries -lt 24) {
        $stillRevit = Get-Process -Name "Revit" -ErrorAction SilentlyContinue
        if (-not $stillRevit) { break }
        Start-Sleep -Seconds 5
        $waitTries++
    }
    if ($stillRevit) {
        Diag "WARN: Revit still running after wait (PIDs: $($stillRevit.Id -join ', ')); Phase 1b may fail if Revit blocks."
    }
}

Diag "=== Bygg pipeline setup start ==="
Diag "JobId: $JobId  RevitYear: $RevitYear"
if ($ImportRoomsIfcOnly) {
    Diag "Mode: ImportRoomsIfcOnly (rooms IFC -> RVT only, then exit)"
}
Diag "RoomsImporter: $RoomsImporter"
Diag "MainIfc:   $MainIfcPath"
Diag "RoomsIfc:  $RoomsIfcPath"
Diag "MainModel: $MainModelPath"
Diag "RoomsModel: $RoomsModelPath"
Diag "RbpSeed:   $RbpSeedRvt"
if ($SkipSetup) { Diag "SkipSetup: true (setup_model_rbp.py will not run)" }

# ---------------------------------------------------------------------------
# Resolve Revit.exe
# ---------------------------------------------------------------------------
$RevitExe = "C:\Program Files\Autodesk\Revit $RevitYear\Revit.exe"

# ---------------------------------------------------------------------------
# Validate BatchRvt.exe
# ---------------------------------------------------------------------------
$BatchRvtExe = Join-Path $env:LOCALAPPDATA "RevitBatchProcessor\BatchRvt.exe"
if (-not (Test-Path $BatchRvtExe)) {
    FailFast "BatchRvt.exe not found at $BatchRvtExe" @{ host = "rbp" }
}
Diag "BatchRvt: $BatchRvtExe"

# ---------------------------------------------------------------------------
# Validate parameter combinations
# ---------------------------------------------------------------------------
if ($ImportRoomsIfcOnly) {
    if ([string]::IsNullOrWhiteSpace($RoomsIfcPath)) {
        $RoomsIfcPath = Join-Path $RepoRoot "demo\in\A1_2b_BIM_XXX_0003_00.ifc"
    }
    if ([string]::IsNullOrWhiteSpace($RoomsModelPath)) {
        $RoomsModelPath = Join-Path $RepoRoot "demo\out\roomsdemo.rvt"
    }
} else {
    if (-not $SkipImport -and -not $MainIfcPath -and -not $MainModelPath) {
        FailFast "Either -MainIfcPath (for IFC import) or -MainModelPath (skip import) is required."
    }
    if ($SkipImport -and -not $MainModelPath) {
        FailFast "-SkipImport requires -MainModelPath to be set."
    }
}

# ---------------------------------------------------------------------------
# Phase 1: IFC to RVT (helpers; execution runs after sync below)
# ---------------------------------------------------------------------------

function Deploy-ByggstyrningIFCImporter {
    <#
    .SYNOPSIS
        Deploys the ByggstyrningIFCImporter add-in DLL and manifest to the Revit
        addins directory so it loads on next Revit startup.
    .DESCRIPTION
        Copies ByggstyrningIFCImporter.dll and .addin from tools/ByggstyrningIFCImporter
        to %APPDATA%\Autodesk\Revit\Addins\<RevitYear>\.
    #>
    $srcDir = Join-Path $RepoRoot "tools\ByggstyrningIFCImporter"
    $dllSrc  = Join-Path $srcDir "bin\Release\ByggstyrningIFCImporter.dll"
    $addinSrc = Join-Path $srcDir "ByggstyrningIFCImporter.addin"
    $destDir = "$env:APPDATA\Autodesk\Revit\Addins\$RevitYear"

    if (-not (Test-Path $dllSrc)) {
        Diag "ERROR: ByggstyrningIFCImporter.dll not found at $dllSrc -- build first"
        return $false
    }
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    # Use byte-level copy to handle OneDrive dehydrated (cloud-only) files
    [IO.File]::Copy($dllSrc,   (Join-Path $destDir "ByggstyrningIFCImporter.dll"),   $true)
    [IO.File]::Copy($addinSrc, (Join-Path $destDir "ByggstyrningIFCImporter.addin"), $true)
    Diag "Deployed ByggstyrningIFCImporter to $destDir"
    return $true
}

function Invoke-RBPGraphisoftImport {
    <#
    .SYNOPSIS
        Improved IFC Import via BatchRvt + graphisoft_import_rbp.py +
        ByggstyrningIFCImporter.ImportRunner (OpenIFCDocument + CorrectIFCImport; same as ribbon).
        Used for main IFC (Phase 1a) and for rooms IFC (Phase 1b) when -RoomsImporter Graphisoft.
    .PARAMETER GraphisoftDir
        If set, sets BYGG_GRAPHISOFT_DIR to the folder containing RevitConnectionManaged.dll.
    .PARAMETER GraphisoftRevitYear
        If set, sets BYGG_REVIT_YEAR (default Graphisoft path/registry when GraphisoftDir omitted).
    .PARAMETER GraphisoftRegistryKey
        If set, sets BYGG_GRAPHISOFT_REGISTRY_KEY (full HKCU subkey for Graphisoft settings).
    .PARAMETER GraphisoftVerbose
        Sets BYGG_IFC_VERBOSE=1 so Graphisoft import/export step IDs are logged to BYGG_IFC_LOG_PATH.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$IfcPath,
        [Parameter(Mandatory)]
        [string]$OutputRvtPath,
        [Parameter(Mandatory)]
        [string]$SeedRvtPath,
        [string]$StepName = "import_main",
        [string]$GraphisoftDir,
        [string]$GraphisoftRevitYear,
        [string]$GraphisoftRegistryKey,
        [switch]$GraphisoftVerbose
    )

    if (-not (Test-Path -LiteralPath $SeedRvtPath)) {
        Diag "ERROR: RBP seed model not found: $SeedRvtPath"
        Diag "Create a minimal metric project in Revit and save as demo\in\empty_R$RevitYear.rvt; see docs\empty-rvt-seed-README.txt."
        return $false
    }

    $deployed = Deploy-ByggstyrningIFCImporter
    if (-not $deployed) { return $false }

    $dllPath = Join-Path $RepoRoot "tools\ByggstyrningIFCImporter\bin\Release\ByggstyrningIFCImporter.dll"
    if (-not (Test-Path -LiteralPath $dllPath)) {
        Diag "ERROR: ByggstyrningIFCImporter.dll not built: $dllPath"
        return $false
    }

    $IfcPath = [System.IO.Path]::GetFullPath($IfcPath)
    $OutputRvtPath = [System.IO.Path]::GetFullPath($OutputRvtPath)
    $SeedRvtPath = [System.IO.Path]::GetFullPath($SeedRvtPath)

    $resultPath = Join-Path $TempDir "${StepName}_result.json"
    $logPath    = Join-Path $TempDir "${StepName}_addin.log"

    $env:BYGG_IFC_PATH          = $IfcPath
    $env:BYGG_IFC_OUTPUT_PATH       = $OutputRvtPath
    $env:BYGG_IFC_RESULT_PATH       = $resultPath
    $env:BYGG_IFC_LOG_PATH          = $logPath
    $env:BYGG_IFC_AUTO_JOIN         = "0"
    $env:BYGG_IFC_CORRECT_OFF_AXIS  = "0"
    $env:BYGG_IFC_IMPORT_ALL_PARAMS = "1"
    $env:BYGG_IFC_IMPORTER_DLL  = $dllPath
    if ($GraphisoftDir) { $env:BYGG_GRAPHISOFT_DIR = $GraphisoftDir }
    if ($GraphisoftRevitYear)      { $env:BYGG_REVIT_YEAR = $GraphisoftRevitYear }
    if ($GraphisoftRegistryKey) { $env:BYGG_GRAPHISOFT_REGISTRY_KEY = $GraphisoftRegistryKey }
    if ($GraphisoftVerbose)        { $env:BYGG_IFC_VERBOSE = "1" }

    Diag "Environment:"
    Diag "  BYGG_IFC_PATH=$IfcPath"
    Diag "  BYGG_IFC_OUTPUT_PATH=$OutputRvtPath"
    Diag "  BYGG_IFC_RESULT_PATH=$resultPath"
    Diag "  BYGG_IFC_IMPORTER_DLL=$dllPath"
    if ($env:BYGG_GRAPHISOFT_DIR) { Diag "  BYGG_GRAPHISOFT_DIR=$($env:BYGG_GRAPHISOFT_DIR)" }
    if ($env:BYGG_REVIT_YEAR) { Diag "  BYGG_REVIT_YEAR=$($env:BYGG_REVIT_YEAR)" }
    if ($env:BYGG_GRAPHISOFT_REGISTRY_KEY) { Diag "  BYGG_GRAPHISOFT_REGISTRY_KEY=$($env:BYGG_GRAPHISOFT_REGISTRY_KEY)" }
    if ($env:BYGG_IFC_VERBOSE) { Diag "  BYGG_IFC_VERBOSE=$($env:BYGG_IFC_VERBOSE)" }
    Diag "  Seed RVT (file list): $SeedRvtPath"

    $taskScript = Join-Path $LocalScriptDir "graphisoft_import_rbp.py"
    if (-not (Test-Path -LiteralPath $taskScript)) {
        Diag "ERROR: graphisoft_import_rbp.py not found: $taskScript"
        return $false
    }

    $sidecarPath = Join-Path $TempDir "${StepName}_rbp.json"
    $preflightJson = @{
        step      = $StepName
        error     = "RBP graphisoft import did not complete (pre-flight)"
        preflight = $true
        job_id    = $JobId
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($sidecarPath, $preflightJson, (New-Object System.Text.UTF8Encoding $false))
    $env:RBP_SIDECAR_PATH = $sidecarPath

    $fileListPath = Join-Path $TempDir "filelist_${StepName}_graphisoft.txt"
    [System.IO.File]::WriteAllText($fileListPath, $SeedRvtPath, (New-Object System.Text.UTF8Encoding $false))

    $stepLog = Join-Path $TempDir "batchrvt_${StepName}_graphisoft.log"
    $rbpArgs = @(
        "--task_script", $taskScript,
        "--file_list",   $fileListPath,
        "--revit_version", $RevitYear,
        "--log_folder",  $LogFolder
    )

    $exitCode = 0
    try {
        Diag "Running BatchRvt (Graphisoft import): $($rbpArgs -join ' ')"
        & $BatchRvtExe @rbpArgs > $stepLog 2>&1
        $exitCode = $LASTEXITCODE
    } catch {
        Diag "ERROR running BatchRvt: $_"
        $exitCode = 99
    }
    Diag "BatchRvt exit code: $exitCode"

    @("BYGG_IFC_PATH","BYGG_IFC_OUTPUT_PATH","BYGG_IFC_RESULT_PATH","BYGG_IFC_LOG_PATH",
      "BYGG_IFC_AUTO_JOIN","BYGG_IFC_CORRECT_OFF_AXIS","BYGG_IFC_IMPORT_ALL_PARAMS","BYGG_IFC_IMPORTER_DLL",
      "BYGG_GRAPHISOFT_DIR","BYGG_REVIT_YEAR","BYGG_GRAPHISOFT_REGISTRY_KEY","BYGG_IFC_VERBOSE") | ForEach-Object {
        Remove-Item "Env:\$_" -ErrorAction SilentlyContinue
    }
    Remove-Item Env:\RBP_SIDECAR_PATH -ErrorAction SilentlyContinue

    if ($exitCode -ne 0) {
        Diag "ERROR: BatchRvt failed with exit code $exitCode (see $stepLog)"
        return $false
    }

    $gsApplied = $false
    if (Test-Path $resultPath) {
        $resultJson = Get-Content $resultPath -Raw | ConvertFrom-Json
        Diag "Add-in result: success=$($resultJson.success), graphisoft_applied=$($resultJson.graphisoft_applied)"
        if ($null -ne $resultJson.corrected_floors) { Diag "  corrected_floors=$($resultJson.corrected_floors)" }
        if ($null -ne $resultJson.corrected_rooms)  { Diag "  corrected_rooms=$($resultJson.corrected_rooms)" }
        if ($resultJson.error) { Diag "Add-in error: $($resultJson.error)" }
        if ($resultJson.preflight_error) { Diag "Preflight error: $($resultJson.preflight_error)" }
        $gsApplied = $resultJson.graphisoft_applied -eq $true
    } else {
        Diag "WARNING: No IFC import result JSON at $resultPath"
    }

    if (Test-Path $logPath) {
        $logLines = Get-Content $logPath
        Diag "Add-in log ($($logLines.Count) lines):"
        $logLines | Select-Object -Last 10 | ForEach-Object { Diag "  $_" }
    }

    if (-not (Test-Path -LiteralPath $OutputRvtPath)) {
        Diag "ERROR: Output RVT not found at $OutputRvtPath"
        return $false
    }

    $sizeMB = [math]::Round((Get-Item $OutputRvtPath).Length / 1MB, 1)
    Diag "Output RVT: $OutputRvtPath ($sizeMB MB)"
    if ($gsApplied) {
        Diag "Graphisoft geometry correction was applied"
    } else {
        Diag "WARNING: Graphisoft correction may not have been applied"
    }
    return $true
}

function Invoke-RBPXbimRoomsImport {
    <#
    .SYNOPSIS
        Imports rooms IFC via BatchRvt + xbim_rooms_import_rbp.py + ByggstyrningRoomImporter
        (xBIM + native Revit rooms, no Graphisoft).
    #>
    param(
        [Parameter(Mandatory)]
        [string]$IfcPath,
        [Parameter(Mandatory)]
        [string]$OutputRvtPath,
        [Parameter(Mandatory)]
        [string]$SeedRvtPath,
        [string]$StepName = "import_rooms_xbim"
    )

    if (-not (Test-Path -LiteralPath $SeedRvtPath)) {
        Diag "ERROR: RBP seed model not found: $SeedRvtPath"
        return $false
    }

    $dllPath = Join-Path $RepoRoot "tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\bin\Release\ByggstyrningRoomImporter.dll"
    if (-not (Test-Path -LiteralPath $dllPath)) {
        Diag "ERROR: ByggstyrningRoomImporter.dll not built: $dllPath"
        Diag "Build: dotnet build tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\ByggstyrningRoomImporter.csproj -c Release"
        return $false
    }

    $IfcPath = [System.IO.Path]::GetFullPath($IfcPath)
    $OutputRvtPath = [System.IO.Path]::GetFullPath($OutputRvtPath)
    $SeedRvtPath = [System.IO.Path]::GetFullPath($SeedRvtPath)

    $resultPath = Join-Path $TempDir "${StepName}_result.json"
    $logPath    = Join-Path $TempDir "${StepName}_addin.log"

    $env:BYGG_IFC_PATH          = $IfcPath
    $env:BYGG_IFC_OUTPUT_PATH       = $OutputRvtPath
    $env:BYGG_IFC_RESULT_PATH       = $resultPath
    $env:BYGG_IFC_LOG_PATH          = $logPath
    $env:BYGG_XBIM_ROOMS_DLL    = $dllPath
    $env:BYGG_RBP_SEED_RVT     = $SeedRvtPath

    Diag "Environment:"
    Diag "  BYGG_IFC_PATH=$IfcPath"
    Diag "  BYGG_IFC_OUTPUT_PATH=$OutputRvtPath"
    Diag "  BYGG_IFC_RESULT_PATH=$resultPath"
    Diag "  BYGG_XBIM_ROOMS_DLL=$dllPath"
    Diag "  BYGG_RBP_SEED_RVT=$SeedRvtPath"
    Diag "  Seed RVT (file list): $SeedRvtPath"

    $taskScript = Join-Path $LocalScriptDir "xbim_rooms_import_rbp.py"
    if (-not (Test-Path -LiteralPath $taskScript)) {
        Diag "ERROR: xbim_rooms_import_rbp.py not found: $taskScript"
        return $false
    }

    $sidecarPath = Join-Path $TempDir "${StepName}_rbp.json"
    $preflightJson = @{
        step      = $StepName
        error     = "RBP xBIM rooms import did not complete (pre-flight)"
        preflight = $true
        job_id    = $JobId
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($sidecarPath, $preflightJson, (New-Object System.Text.UTF8Encoding $false))
    $env:RBP_SIDECAR_PATH = $sidecarPath

    $fileListPath = Join-Path $TempDir "filelist_${StepName}_xbim.txt"
    [System.IO.File]::WriteAllText($fileListPath, $SeedRvtPath, (New-Object System.Text.UTF8Encoding $false))

    $stepLog = Join-Path $TempDir "batchrvt_${StepName}_xbim.log"
    $rbpArgs = @(
        "--task_script", $taskScript,
        "--file_list",   $fileListPath,
        "--revit_version", $RevitYear,
        "--log_folder",  $LogFolder
    )

    $exitCode = 0
    try {
        Diag "Running BatchRvt (xBIM rooms import): $($rbpArgs -join ' ')"
        & $BatchRvtExe @rbpArgs > $stepLog 2>&1
        $exitCode = $LASTEXITCODE
    } catch {
        Diag "ERROR running BatchRvt: $_"
        $exitCode = 99
    }
    Diag "BatchRvt exit code: $exitCode"

    @("BYGG_IFC_PATH","BYGG_IFC_OUTPUT_PATH","BYGG_IFC_RESULT_PATH","BYGG_IFC_LOG_PATH","BYGG_XBIM_ROOMS_DLL","BYGG_RBP_SEED_RVT") | ForEach-Object {
        Remove-Item "Env:\$_" -ErrorAction SilentlyContinue
    }
    Remove-Item Env:\RBP_SIDECAR_PATH -ErrorAction SilentlyContinue

    if ($exitCode -ne 0) {
        Diag "ERROR: BatchRvt failed with exit code $exitCode (see $stepLog)"
        return $false
    }

    if (Test-Path $resultPath) {
        $resultJson = Get-Content $resultPath -Raw | ConvertFrom-Json
        $bl = $resultJson.boundary_loops_applied
        if ($null -ne $bl) {
            Diag "Add-in result: success=$($resultJson.success), rooms_created=$($resultJson.rooms_created), boundary_loops_applied=$bl"
        } else {
            Diag "Add-in result: success=$($resultJson.success), rooms_created=$($resultJson.rooms_created)"
        }
        if ($resultJson.error -and $resultJson.error -ne "null") { Diag "Add-in error: $($resultJson.error)" }
    } else {
        Diag "WARNING: No IFC import result JSON at $resultPath"
    }

    if (Test-Path $logPath) {
        $logLines = Get-Content $logPath
        Diag "Add-in log ($($logLines.Count) lines):"
        $logLines | Select-Object -Last 10 | ForEach-Object { Diag "  $_" }
    }

    if (-not (Test-Path -LiteralPath $OutputRvtPath)) {
        Diag "ERROR: Output RVT not found at $OutputRvtPath"
        return $false
    }

    $sizeMB = [math]::Round((Get-Item $OutputRvtPath).Length / 1MB, 1)
    Diag "Output RVT: $OutputRvtPath ($sizeMB MB)"
    return $true
}

function Invoke-GraphisoftImport {
    <#
    .SYNOPSIS
        Imports an IFC file using the Graphisoft geometry correction engine
        via the ByggstyrningIFCImporter add-in.
    .DESCRIPTION
        Deploys the add-in, sets BYGG_* environment variables, runs Revit
        with a journal that invokes the add-in, and verifies the output.
        The add-in calls OpenIFCDocument + CorrectIFCImport + SaveAs.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$IfcPath,
        [Parameter(Mandatory)]
        [string]$OutputRvtPath,
        [string]$StepName = "graphisoft_import"
    )

    $templatePath = Join-Path $JournalTemplatesDir "ifc_graphisoft_import.template.txt"
    if (-not (Test-Path $templatePath)) {
        Diag "ERROR: Graphisoft import template not found: $templatePath"
        return $false
    }

    # Deploy the add-in
    $deployed = Deploy-ByggstyrningIFCImporter
    if (-not $deployed) { return $false }

    $IfcPath = [System.IO.Path]::GetFullPath($IfcPath)
    $OutputRvtPath = [System.IO.Path]::GetFullPath($OutputRvtPath)
    $revitVersion = "$RevitYear.000"

    $resultPath = Join-Path $TempDir "${StepName}_result.json"
    $logPath    = Join-Path $TempDir "${StepName}_addin.log"

    # Set environment variables for the add-in
    $env:BYGG_IFC_PATH          = $IfcPath
    $env:BYGG_IFC_OUTPUT_PATH       = $OutputRvtPath
    $env:BYGG_IFC_RESULT_PATH       = $resultPath
    $env:BYGG_IFC_LOG_PATH          = $logPath
    $env:BYGG_IFC_AUTO_JOIN         = "0"
    $env:BYGG_IFC_CORRECT_OFF_AXIS  = "0"
    $env:BYGG_IFC_IMPORT_ALL_PARAMS = "1"

    Diag "Environment:"
    Diag "  BYGG_IFC_PATH=$IfcPath"
    Diag "  BYGG_IFC_OUTPUT_PATH=$OutputRvtPath"
    Diag "  BYGG_IFC_RESULT_PATH=$resultPath"

    $template = Get-Content $templatePath -Raw -Encoding UTF8
    $journal = $template -replace '\{\{REVIT_VERSION\}\}', $revitVersion

    $journalPath = Join-Path $TempDir "journal_${StepName}.txt"
    [System.IO.File]::WriteAllText($journalPath, $journal, (New-Object System.Text.UTF8Encoding $false))
    Diag "Journal written: $journalPath"

    if (-not (Test-Path $RevitExe)) {
        Diag "ERROR: Revit.exe not found at $RevitExe"
        return $false
    }

    Diag "Starting Revit journal replay for $StepName ..."
    $journalLog = Join-Path $TempDir "revit_${StepName}.log"
    $proc = Start-Process -FilePath $RevitExe `
                          -ArgumentList "`"$journalPath`"" `
                          -PassThru `
                          -NoNewWindow `
                          -RedirectStandardOutput $journalLog `
                          -RedirectStandardError (Join-Path $TempDir "revit_${StepName}_err.log")

    Diag "Revit PID: $($proc.Id) -- waiting for exit (timeout 45 min) ..."
    $exited = $proc.WaitForExit(2700000)
    if (-not $exited) {
        Diag "WARNING: Revit did not exit within 45 minutes, killing process."
        try { $proc.Kill() } catch {}
    }
    Diag "Revit exited with code: $($proc.ExitCode)"

    # Clean up environment variables
    @("BYGG_IFC_PATH","BYGG_IFC_OUTPUT_PATH","BYGG_IFC_RESULT_PATH","BYGG_IFC_LOG_PATH",
      "BYGG_IFC_AUTO_JOIN","BYGG_IFC_CORRECT_OFF_AXIS","BYGG_IFC_IMPORT_ALL_PARAMS") | ForEach-Object {
        Remove-Item "Env:\$_" -ErrorAction SilentlyContinue
    }

    # Check result sidecar
    $gsApplied = $false
    if (Test-Path $resultPath) {
        $resultJson = Get-Content $resultPath -Raw | ConvertFrom-Json
        Diag "Add-in result: success=$($resultJson.success), graphisoft_applied=$($resultJson.graphisoft_applied)"
        if ($resultJson.error) { Diag "Add-in error: $($resultJson.error)" }
        $gsApplied = $resultJson.graphisoft_applied -eq $true
    } else {
        Diag "WARNING: No result sidecar at $resultPath"
    }

    # Check add-in log
    if (Test-Path $logPath) {
        $logLines = Get-Content $logPath
        Diag "Add-in log ($($logLines.Count) lines):"
        $logLines | Select-Object -Last 10 | ForEach-Object { Diag "  $_" }
    }

    # Verify output
    if (Test-Path -LiteralPath $OutputRvtPath) {
        $sizeMB = [math]::Round((Get-Item $OutputRvtPath).Length / 1MB, 1)
        Diag "Output RVT: $OutputRvtPath ($sizeMB MB)"
        if ($gsApplied) {
            Diag "Graphisoft geometry correction was applied"
        } else {
            Diag "WARNING: Graphisoft correction may not have been applied"
        }
        return $true
    } else {
        Diag "ERROR: Output RVT not found at $OutputRvtPath"
        return $false
    }
}

function Invoke-JournalImport {
    <#
    .SYNOPSIS
        Imports an IFC file using Revit's native IFC-to-RVT conversion.
        Links the IFC via ID_IFC_LINK (proven reliable), then extracts
        the .ifc.RVT cache file as the imported rooms model.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$IfcPath,
        [Parameter(Mandatory)]
        [string]$OutputRvtPath,
        [string]$StepName = "import_ifc"
    )

    $templatePath = Join-Path $JournalTemplatesDir "ifc_open_import.template.txt"

    if (-not (Test-Path $templatePath)) {
        Diag "ERROR: Import template not found: $templatePath"
        return $false
    }

    # Copy IFC to a temp work directory so .ifc.RVT cache is created there
    $workDir = Join-Path $TempDir "${StepName}_work"
    New-Item -ItemType Directory -Path $workDir -Force | Out-Null
    $tempIfc = Join-Path $workDir ([System.IO.Path]::GetFileName($IfcPath))
    Copy-Item $IfcPath $tempIfc
    Diag "Copied IFC to work dir: $tempIfc"

    $tempIfc = [System.IO.Path]::GetFullPath($tempIfc)
    $OutputRvtPath = [System.IO.Path]::GetFullPath($OutputRvtPath)
    $ifcFilename = [System.IO.Path]::GetFileName($tempIfc)
    $hostRvt = [System.IO.Path]::ChangeExtension($OutputRvtPath, ".host.rvt")
    $revitVersion = "$RevitYear.000"

    $template = Get-Content $templatePath -Raw -Encoding UTF8
    $journal = $template `
        -replace '\{\{IFC_FILE_PATH\}\}',        $tempIfc `
        -replace '\{\{IFC_FILENAME\}\}',          $ifcFilename `
        -replace '\{\{LINK_HOST_RVT_PATH\}\}',   $hostRvt `
        -replace '\{\{REVIT_VERSION\}\}',         $revitVersion

    $journalPath = Join-Path $TempDir "journal_${StepName}.txt"
    [System.IO.File]::WriteAllText($journalPath, $journal, (New-Object System.Text.UTF8Encoding $false))
    Diag "Journal written: $journalPath"

    if (-not (Test-Path $RevitExe)) {
        Diag "ERROR: Revit.exe not found at $RevitExe"
        return $false
    }

    Diag "Starting Revit journal replay for $StepName ..."
    $journalLog = Join-Path $TempDir "revit_${StepName}.log"
    $proc = Start-Process -FilePath $RevitExe `
                          -ArgumentList "`"$journalPath`"" `
                          -PassThru `
                          -NoNewWindow `
                          -RedirectStandardOutput $journalLog `
                          -RedirectStandardError (Join-Path $TempDir "revit_${StepName}_err.log")

    Diag "Revit PID: $($proc.Id) -- waiting for exit (timeout 30 min) ..."
    $exited = $proc.WaitForExit(1800000)
    if (-not $exited) {
        Diag "WARNING: Revit did not exit within 30 minutes, killing process."
        try { $proc.Kill() } catch {}
        return $false
    }
    Diag "Revit exited with code: $($proc.ExitCode)"

    # The real output is the .ifc.RVT cache file created next to the IFC
    $cacheFile = "$tempIfc.RVT"
    if (Test-Path -LiteralPath $cacheFile) {
        Diag ".ifc.RVT cache created: $cacheFile ($([math]::Round((Get-Item $cacheFile).Length / 1MB, 1)) MB)"
        Copy-Item $cacheFile $OutputRvtPath -Force
        Diag "Rooms RVT extracted to: $OutputRvtPath"

        # Clean up throwaway host project
        if (Test-Path $hostRvt) { Remove-Item $hostRvt -Force -ErrorAction SilentlyContinue }
        return $true
    } else {
        Diag "ERROR: .ifc.RVT cache NOT created at $cacheFile"
        return $false
    }
}

# ---------------------------------------------------------------------------
# Repository paths, RBP script cache, logs (Phase 1a BatchRvt + Phase 2)
# ---------------------------------------------------------------------------
$ExtDir = $RepoRoot
$LibDir = Join-Path $ExtDir "lib"

$LocalScriptDir = Join-Path $env:LOCALAPPDATA "Byggstyrning\rbp_scripts\$JobId"
if (-not (Test-Path $LocalScriptDir)) { New-Item -ItemType Directory -Path $LocalScriptDir -Force | Out-Null }

$LogFolder = Join-Path $TempDir "logs"
if (-not (Test-Path $LogFolder)) { New-Item -ItemType Directory -Path $LogFolder -Force | Out-Null }

Diag "Syncing Python scripts to $LocalScriptDir"

$syncSources = @(
    @{ Src = $LibDir; Filter = "*.py" },
    @{ Src = (Join-Path $LibDir "revit"); Filter = "*.py" },
    @{ Src = (Join-Path $ExtDir "scripts\rbp\setup"); Filter = "*_rbp.py" },
    @{ Src = (Join-Path $ExtDir "scripts\rbp\merge_rooms"); Filter = "*_rbp.py" },
    @{ Src = (Join-Path $ExtDir "scripts\rbp\publish_acc"); Filter = "*_rbp.py" }
)

foreach ($src in $syncSources) {
    if (Test-Path -LiteralPath $src.Src) {
        Get-ChildItem -LiteralPath $src.Src -Filter $src.Filter -File -ErrorAction SilentlyContinue | ForEach-Object {
            $dst = Join-Path $LocalScriptDir $_.Name
            try {
                $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
                [System.IO.File]::WriteAllBytes($dst, $bytes)
                Diag "  Synced: $($_.Name)"
            } catch {
                Diag "  WARN: Could not sync $($_.Name): $_"
            }
        }
    } else {
        Diag "  WARN: Source dir not found: $($src.Src)"
    }
}

$settingsSrc = Join-Path $ExtDir "settings.json"
if (Test-Path $settingsSrc) {
    Copy-Item $settingsSrc (Join-Path $LocalScriptDir "settings.json") -Force
    Diag "  Synced: settings.json"
}

# RBP task scripts are copied flat to LocalScriptDir; Python cannot walk to lib/ from __file__.
$env:BYGG_REPO_ROOT = $RepoRoot

if ($ImportRoomsIfcOnly) {
    if (-not (Test-Path -LiteralPath $RoomsIfcPath)) {
        FailFast "Rooms IFC not found: $RoomsIfcPath"
    }
    $RoomsIfcPath = [System.IO.Path]::GetFullPath($RoomsIfcPath)
    $RoomsModelPath = [System.IO.Path]::GetFullPath($RoomsModelPath)
    $demoParent = Split-Path -Parent $RoomsModelPath
    if ($demoParent -and -not (Test-Path -LiteralPath $demoParent)) {
        New-Item -ItemType Directory -Path $demoParent -Force | Out-Null
    }

    if ($RoomsImporter -eq "Xbim") {
        Diag "--- ImportRoomsIfcOnly: rooms IFC -> RVT (xBIM BatchRvt, ByggstyrningRoomImporter) ---"
        $importOk = Invoke-RBPXbimRoomsImport -IfcPath $RoomsIfcPath -OutputRvtPath $RoomsModelPath -SeedRvtPath $RbpSeedRvt -StepName "import_rooms"
    } else {
        Diag "--- ImportRoomsIfcOnly: rooms IFC -> RVT (Graphisoft BatchRvt, same as pipeline Phase 1b) ---"
        $importOk = Invoke-RBPGraphisoftImport -IfcPath $RoomsIfcPath -OutputRvtPath $RoomsModelPath -SeedRvtPath $RbpSeedRvt -StepName "import_rooms"
    }
    $OverallResult.steps["import_rooms"] = @{
        ifc_path       = $RoomsIfcPath
        rvt_path       = $RoomsModelPath
        success        = $importOk
        rooms_importer = $RoomsImporter
    }
    $OverallResult.rooms_model = $RoomsModelPath
    if (-not $importOk) {
        FailFast "ImportRoomsIfcOnly failed: rooms IFC import did not complete ($RoomsImporter)."
    }
    Diag "Open this file in Revit to inspect rooms/spaces: $RoomsModelPath"
    Diag "=== ImportRoomsIfcOnly complete ==="
    EmitRwResult $OverallResult
    exit 0
}

# --- Phase 1 execution ---
$Phase1aBatchRvtCompleted = $false
$Phase1bBatchRvtCompleted = $false
if (-not $SkipImport) {
    # Link main IFC
    if ($MainIfcPath) {
        if (-not (Test-Path -LiteralPath $MainIfcPath)) {
            FailFast "Main IFC not found: $MainIfcPath"
        }
        $MainIfcPath = [System.IO.Path]::GetFullPath($MainIfcPath)

        if (-not $MainModelPath) {
            $MainModelPath = [System.IO.Path]::ChangeExtension($MainIfcPath, ".rvt")
        }

        Diag "--- Phase 1a: Improved IFC Import (ByggstyrningIFCImporter: OpenIFCDocument + CorrectIFCImport, BatchRvt) ---"
        $importOk = Invoke-RBPGraphisoftImport -IfcPath $MainIfcPath -OutputRvtPath $MainModelPath -SeedRvtPath $RbpSeedRvt -StepName "import_main"
        $OverallResult.steps["import_main"] = @{
            ifc_path      = $MainIfcPath
            rvt_path      = $MainModelPath
            success       = $importOk
            main_importer = "ImprovedIFCImport"
        }
        if (-not $importOk) {
            FailFast "Phase 1a failed: could not import main IFC (Improved IFC Import / ByggstyrningIFCImporter)."
        }
        $OverallResult.main_model = $MainModelPath
        $Phase1aBatchRvtCompleted = $true
    }

    # Import rooms IFC
    if ($RoomsIfcPath -and -not $SkipRooms) {
        if (-not (Test-Path -LiteralPath $RoomsIfcPath)) {
            FailFast "Rooms IFC not found: $RoomsIfcPath"
        }
        $RoomsIfcPath = [System.IO.Path]::GetFullPath($RoomsIfcPath)

        if (-not $RoomsModelPath) {
            $RoomsModelPath = [System.IO.Path]::ChangeExtension($RoomsIfcPath, ".rvt")
        }

        if ($Phase1aBatchRvtCompleted) {
            Wait-RevitAfterBatchRvtForJournal
        }

        if ($RoomsImporter -eq "Xbim") {
            Diag "--- Phase 1b: xBIM import rooms IFC (BatchRvt, ByggstyrningRoomImporter) ---"
            $importOk = Invoke-RBPXbimRoomsImport -IfcPath $RoomsIfcPath -OutputRvtPath $RoomsModelPath -SeedRvtPath $RbpSeedRvt -StepName "import_rooms"
        } else {
            Diag "--- Phase 1b: Graphisoft import rooms IFC (BatchRvt) ---"
            $importOk = Invoke-RBPGraphisoftImport -IfcPath $RoomsIfcPath -OutputRvtPath $RoomsModelPath -SeedRvtPath $RbpSeedRvt -StepName "import_rooms"
        }
        $OverallResult.steps["import_rooms"] = @{
            ifc_path       = $RoomsIfcPath
            rvt_path       = $RoomsModelPath
            success        = $importOk
            rooms_importer = $RoomsImporter
        }
        if (-not $importOk) {
            FailFast "Phase 1b failed: could not import rooms IFC ($RoomsImporter)."
        }
        $OverallResult.rooms_model = $RoomsModelPath
        $Phase1bBatchRvtCompleted = $true
    }

    Diag "Phase 1 complete."
} else {
    Diag "Phase 1 skipped (-SkipImport)."
}

# ---------------------------------------------------------------------------
# Validate inputs for Phase 2
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $MainModelPath)) {
    FailFast "Main model not found: $MainModelPath"
}
if (-not $SkipRooms -and $RoomsModelPath -and -not (Test-Path -LiteralPath $RoomsModelPath)) {
    FailFast "Rooms model not found: $RoomsModelPath"
}
if (-not $SkipRooms -and -not $RoomsModelPath) {
    FailFast "RoomsModelPath is required unless -SkipRooms is set."
}

$CloudModelNameResolved = $null
if ($PublishAcc) {
    if ([string]::IsNullOrWhiteSpace($AccAccountId) -or [string]::IsNullOrWhiteSpace($AccProjectId) -or [string]::IsNullOrWhiteSpace($AccFolderId)) {
        FailFast "-PublishAcc requires -AccAccountId, -AccProjectId, and -AccFolderId"
    }
    if (-not [string]::IsNullOrWhiteSpace($CloudModelName)) {
        $CloudModelNameResolved = $CloudModelName.Trim()
    } elseif (-not [string]::IsNullOrWhiteSpace($MainIfcPath)) {
        $ifcFull = [System.IO.Path]::GetFullPath($MainIfcPath)
        $ifcBase = [System.IO.Path]::GetFileNameWithoutExtension($ifcFull)
        $d = Get-Date -Format 'yyyy-MM-dd'
        $CloudModelNameResolved = "${ifcBase}.ifc_${d}.rvt"
    } else {
        FailFast "-PublishAcc requires -CloudModelName when -MainIfcPath is not set (e.g. -SkipImport without IFC path)."
    }
    Diag "ACC publish: cloud model name = $CloudModelNameResolved"
}

if ($Phase1bBatchRvtCompleted) {
    Wait-RevitAfterBatchRvtForJournal
}

# ---------------------------------------------------------------------------
# Phase 2: RBP runs (scripts already synced before Phase 1)
# ---------------------------------------------------------------------------

function Get-RbpTaskDefaultSidecarPath {
    <#
    .SYNOPSIS
        Path where *_rbp.py writes when RBP_SIDECAR_PATH is not visible in the worker
        (must match setup_model_rbp.py / merge_rooms_rbp.py / publish_acc_rbp.py).
    #>
    param(
        [Parameter(Mandatory)]
        [string]$ModelPath,
        [Parameter(Mandatory)]
        [string]$StepName
    )
    $dir = Split-Path -Parent $ModelPath
    $base = [System.IO.Path]::GetFileNameWithoutExtension($ModelPath)
    $suffix = switch ($StepName) {
        "setup" { "setup" }
        "merge_rooms" { "rooms" }
        "publish_acc" { "publish_acc" }
        default { $StepName }
    }
    return Join-Path $dir "${base}.rbp_${suffix}_result.json"
}

function Invoke-RBPStep {
    param(
        [string]$StepName,
        [string]$TaskScript,
        [string]$SidecarPath
    )

    Diag "--- Starting step: $StepName ---"

    if (-not (Test-Path -LiteralPath $TaskScript)) {
        Diag "ERROR: task script not found: $TaskScript"
        return $null
    }

    # Pre-flight sidecar: if Python crashes before writing its own, we still get parseable JSON
    $preflightJson = @{
        step    = $StepName
        error   = "RBP task did not complete (pre-flight)"
        preflight = $true
        job_id  = $JobId
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($SidecarPath, $preflightJson, (New-Object System.Text.UTF8Encoding $false))
    $env:RBP_SIDECAR_PATH = $SidecarPath

    $FileListPath = Join-Path $TempDir "filelist_${StepName}.txt"
    [System.IO.File]::WriteAllText($FileListPath, $MainModelPath, (New-Object System.Text.UTF8Encoding $false))

    $StepLog = Join-Path $TempDir "batchrvt_${StepName}.log"
    $rbpArgs = @(
        "--task_script", $TaskScript,
        "--file_list",   $FileListPath,
        "--revit_version", $RevitYear,
        "--log_folder",  $LogFolder
        # No --detach: we are saving changes in place between steps
    )

    $exitCode = 0
    try {
        Diag "Running BatchRvt with args: $($rbpArgs -join ' ')"
        & $BatchRvtExe @rbpArgs > $StepLog 2>&1
        $exitCode = $LASTEXITCODE
    } catch {
        Diag "ERROR running BatchRvt: $_"
        $exitCode = 99
    }
    Diag "BatchRvt exit code: $exitCode"

    if ($exitCode -ne 0) {
        FailFast "BatchRvt failed at step '$StepName' with exit code $exitCode (see $StepLog)"
    }

    # Read sidecar
    $sidecarContent = $null
    if (Test-Path -LiteralPath $SidecarPath) {
        $sidecarContent = Get-Content -LiteralPath $SidecarPath -Raw -Encoding utf8 -ErrorAction SilentlyContinue
    }

    if ($sidecarContent) {
        try { $parsed = $sidecarContent | ConvertFrom-Json } catch { $parsed = $null }
        if ($parsed -and $parsed.preflight -eq $true) {
            $altPath = Get-RbpTaskDefaultSidecarPath -ModelPath $MainModelPath -StepName $StepName
            if (Test-Path -LiteralPath $altPath) {
                $altRaw = Get-Content -LiteralPath $altPath -Raw -Encoding utf8 -ErrorAction SilentlyContinue
                if ($altRaw) {
                    try {
                        $altParsed = $altRaw | ConvertFrom-Json
                        if ($altParsed -and $altParsed.preflight -ne $true) {
                            Diag "Sidecar: read model-adjacent result for step '$StepName': $altPath"
                            return $altParsed
                        }
                    } catch { }
                }
            }
        }
        return $parsed
    }

    return @{ step = $StepName; error = "No sidecar produced"; rbp_exit = $exitCode }
}

# ---------------------------------------------------------------------------
# Phase 2, Run 1: Setup model
# ---------------------------------------------------------------------------
$setupResult = $null
if (-not $SkipSetup) {
    $setupScript  = Join-Path $LocalScriptDir "setup_model_rbp.py"
    $setupSidecar = Join-Path $TempDir "setup_result.json"

    $env:BYGG_SETUP_SAVEAS_FALLBACK = (Join-Path $env:TEMP "bygg_setup_${JobId}_main.rvt")
    $setupResult = Invoke-RBPStep -StepName "setup" -TaskScript $setupScript -SidecarPath $setupSidecar
    Remove-Item Env:\BYGG_SETUP_SAVEAS_FALLBACK -ErrorAction SilentlyContinue

    $setupMergeTemp = $null
    if ($setupResult -and $setupResult.setup_temp_saved_path) {
        $setupMergeTemp = [string]$setupResult.setup_temp_saved_path
    }
    if ($setupMergeTemp -and (Test-Path -LiteralPath $setupMergeTemp)) {
        try {
            Copy-Item -LiteralPath $setupMergeTemp -Destination $MainModelPath -Force
            Remove-Item -LiteralPath $setupMergeTemp -Force -ErrorAction SilentlyContinue
            $setupResult | Add-Member -NotePropertyName setup_os_copy_done -NotePropertyValue $true -Force
            Diag "Setup: copied temp save to main model: $MainModelPath"
        } catch {
            Diag "WARN: setup temp to main copy failed: $_"
        }
    }

    $OverallResult.steps["setup"] = $setupResult

    if ($setupResult) {
        $sd = $setupResult.openings_deleted
        $sr = $setupResult.elements_rotated
        $sw = $setupResult.worksharing_enabled
        $sms = $setupResult.model_saved
        $cfg = $setupResult.config_linked
        Diag "Setup RBP summary: openings_deleted=$sd elements_rotated=$sr worksharing_enabled=$sw config_linked=$cfg model_saved=$sms"
        if ($setupResult.save_error) {
            Diag "Setup save_error: $($setupResult.save_error)"
        }
        $setupSidecarModel = Join-Path (Split-Path -Parent $MainModelPath) (([System.IO.Path]::GetFileNameWithoutExtension($MainModelPath)) + ".rbp_setup_result.json")
        Diag "Setup sidecar (model-adjacent): $setupSidecarModel"
    }

    if ($setupResult -and $setupResult.error -and -not $setupResult.preflight) {
        Diag "Step 'setup' reported error: $($setupResult.error)"
        # Non-fatal: log and continue unless catastrophic
        if ($setupResult.error -like "*FATAL*") {
            FailFast "Fatal error in setup step: $($setupResult.error)"
        }
    }

    # Same RVT as next BatchRvt step: wait until Revit releases file locks (Phase 1 already does this).
    Wait-RevitAfterBatchRvtForJournal
} else {
    Diag "Skipping setup model (SkipSetup set)."
    $OverallResult.steps["setup"] = @{ skipped = $true }
}

# If Phase 1 ran BatchRvt but setup was skipped, wait so Revit releases the model before the next step.
if ($SkipSetup -and ($Phase1aBatchRvtCompleted -or $Phase1bBatchRvtCompleted)) {
    Wait-RevitAfterBatchRvtForJournal
}

# ---------------------------------------------------------------------------
# Phase 2, Run 2: Merge rooms
# ---------------------------------------------------------------------------
if (-not $SkipRooms) {
    $env:ROOMS_MODEL_PATH = $RoomsModelPath
    $env:BYGG_MERGE_SAVEAS_PATH = $MainModelPath
    $env:BYGG_MERGE_SAVEAS_FALLBACK = (Join-Path $env:TEMP "bygg_merge_${JobId}_main.rvt")

    $roomsScript  = Join-Path $LocalScriptDir "merge_rooms_rbp.py"
    $roomsSidecar = Join-Path $TempDir "rooms_result.json"

    $roomsResult = Invoke-RBPStep -StepName "merge_rooms" -TaskScript $roomsScript -SidecarPath $roomsSidecar

    Remove-Item Env:\ROOMS_MODEL_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:\BYGG_MERGE_SAVEAS_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:\BYGG_MERGE_SAVEAS_FALLBACK -ErrorAction SilentlyContinue

    $mergeTemp = $null
    if ($roomsResult -and $roomsResult.merge_temp_saved_path) {
        $mergeTemp = [string]$roomsResult.merge_temp_saved_path
    }
    if ($mergeTemp -and (Test-Path -LiteralPath $mergeTemp)) {
        try {
            Copy-Item -LiteralPath $mergeTemp -Destination $MainModelPath -Force
            Remove-Item -LiteralPath $mergeTemp -Force -ErrorAction SilentlyContinue
            $roomsResult | Add-Member -NotePropertyName target_os_copy_done -NotePropertyValue $true -Force
            Diag "Merge: copied temp save to main model: $MainModelPath"
        } catch {
            Diag "WARN: merge temp to main copy failed: $_"
        }
    }

    $OverallResult.steps["merge_rooms"] = $roomsResult

    if ($roomsResult -and $roomsResult.error -and -not $roomsResult.preflight) {
        Diag "Step 'merge_rooms' reported error: $($roomsResult.error)"
    }
    if ($roomsResult -and $roomsResult.save_error -and -not $roomsResult.target_saved) {
        Diag "Step 'merge_rooms' save failed: $($roomsResult.save_error)"
    }
} else {
    Diag "Skipping rooms merge (SkipRooms set)."
    $OverallResult.steps["merge_rooms"] = @{ skipped = $true }
}

if (-not $SkipRooms) {
    Wait-RevitAfterBatchRvtForJournal
}

# ---------------------------------------------------------------------------
# Optional Phase 3: Publish main model to ACC (SaveAsCloudModel)
# ---------------------------------------------------------------------------
if ($PublishAcc) {
    Wait-RevitAfterBatchRvtForJournal

    $accAcc = Get-NormalizedAccGuidString -Raw $AccAccountId -Label "account (hub)"
    $accPrj = Get-NormalizedAccGuidString -Raw $AccProjectId -Label "project"
    $accFld = $AccFolderId.Trim()

    $env:BYGG_ACC_ACCOUNT_GUID = $accAcc
    $env:BYGG_ACC_PROJECT_GUID = $accPrj
    $env:BYGG_ACC_FOLDER_ID = $accFld
    $env:BYGG_CLOUD_MODEL_NAME = $CloudModelNameResolved

    $publishScript  = Join-Path $LocalScriptDir "publish_acc_rbp.py"
    $publishSidecar = Join-Path $TempDir "publish_acc_result.json"

    Diag "--- Phase 3: ACC cloud publish (SaveAsCloudModel) ---"
    $publishResult = Invoke-RBPStep -StepName "publish_acc" -TaskScript $publishScript -SidecarPath $publishSidecar
    $OverallResult.steps["publish_acc"] = $publishResult

    Remove-Item Env:\BYGG_ACC_ACCOUNT_GUID -ErrorAction SilentlyContinue
    Remove-Item Env:\BYGG_ACC_PROJECT_GUID -ErrorAction SilentlyContinue
    Remove-Item Env:\BYGG_ACC_FOLDER_ID -ErrorAction SilentlyContinue
    Remove-Item Env:\BYGG_CLOUD_MODEL_NAME -ErrorAction SilentlyContinue

    if ($publishResult -and $publishResult.error -and -not $publishResult.preflight) {
        Diag "Step 'publish_acc' reported error: $($publishResult.error)"
    }
    $ok = $publishResult -and ($publishResult.cloud_publish_succeeded -eq $true)
    if (-not $ok) {
        $err = if ($publishResult -and $publishResult.error) { $publishResult.error } else { "unknown" }
        FailFast "ACC publish failed (publish_acc): $err"
    }
    Diag "ACC publish succeeded: $CloudModelNameResolved"
}

# ---------------------------------------------------------------------------
# Optional: clean up Revit incremental backups
# ---------------------------------------------------------------------------
$revitCleanup = Join-Path $RepoRoot "RevitBackupCleanup.ps1"
if (Test-Path -LiteralPath $revitCleanup) {
    try {
        . $revitCleanup
        Remove-RevitIncrementalBackupRvt -ModelPath $MainModelPath -LogMessage { param($m) Diag $m }
    } catch {
        Diag "WARN: RevitBackupCleanup failed: $_"
    }
}

# ---------------------------------------------------------------------------
# Clean up env vars and temp scripts
# ---------------------------------------------------------------------------
Remove-Item Env:\BYGG_REPO_ROOT -ErrorAction SilentlyContinue
Remove-Item Env:\RBP_SIDECAR_PATH -ErrorAction SilentlyContinue
try { Remove-Item -LiteralPath $LocalScriptDir -Recurse -Force -ErrorAction SilentlyContinue } catch {}

# ---------------------------------------------------------------------------
# Emit final RW_RESULT
# ---------------------------------------------------------------------------
Diag "=== Bygg pipeline setup complete ==="
Write-Output "Logs: $LogFolder\"
Write-Output """$DiagLog"""

EmitRwResult $OverallResult
