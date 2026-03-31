<#
.SYNOPSIS
    End-to-end smoke test: invoke Run-ByggPipelineSetup.ps1 with demo IFCs.

.DESCRIPTION
    By default writes main and rooms RVTs under demo\out\ (persistent; same paths on each run).
    Use -UseTempOutput to use %TEMP%\bygg_pipeline_e2e_<timestamp>\ instead.

    Expect a long run (multiple Revit launches: BatchRvt, three RBP steps).

    Exit code 0 means the launcher finished; inspect RW_RESULT and step sidecars for
    per-step success.  Requires demo\in\empty_R{RevitYear}.rvt (or pass -RbpSeedRvt).

.PARAMETER RbpSeedRvt
    Optional override for the BatchRvt seed .rvt. When omitted, uses demo\in\empty_R{RevitYear}.rvt.

.PARAMETER RevitYear
    Revit version year (default: 2025).

.PARAMETER RoomsImporter
    Xbim (default) or Graphisoft for Phase 1b rooms IFC import.

.PARAMETER UseTempOutput
    If set, outputs go to %TEMP%\bygg_pipeline_e2e_<timestamp>\ instead of demo\out\.

.PARAMETER PublishAcc
    Pass through to Run-ByggPipelineSetup.ps1: optional Phase 3 ACC publish. Requires
    -AccAccountId, -AccProjectId, -AccFolderId (demo uses -MainIfcPath for default cloud name).

.PARAMETER AccAccountId
.PARAMETER AccProjectId
.PARAMETER AccFolderId
.PARAMETER CloudModelName
    ACC publish options (see Run-ByggPipelineSetup.ps1).

.PARAMETER SkipSetup
    Pass through: skip setup_model_rbp.py (see Run-ByggPipelineSetup.ps1).

.EXAMPLE
    .\Test-ByggPipelineFull.ps1
.EXAMPLE
    .\Test-ByggPipelineFull.ps1 -RoomsImporter Graphisoft
.EXAMPLE
    .\Test-ByggPipelineFull.ps1 -UseTempOutput
#>

param(
    [int]$RevitYear = 2025,
    [string]$RbpSeedRvt = "",
    [ValidateSet("Graphisoft", "Xbim")]
    [string]$RoomsImporter = "Xbim",
    [switch]$UseTempOutput,
    [switch]$PublishAcc,
    [string]$AccAccountId = "",
    [string]$AccProjectId = "",
    [string]$AccFolderId = "",
    [string]$CloudModelName = "",
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"

$ExtRoot = Split-Path $PSScriptRoot -Parent
$DemoIn  = Join-Path $ExtRoot "demo\in"
$MainIfc  = Join-Path $DemoIn "A1_2b_BIM_XXX_0001_00.ifc"
$RoomsIfc = Join-Path $DemoIn "A1_2b_BIM_XXX_0003_00.ifc"
if ([string]::IsNullOrWhiteSpace($RbpSeedRvt)) {
    $SeedRvt = Join-Path $DemoIn "empty_R$RevitYear.rvt"
} else {
    $SeedRvt = $RbpSeedRvt
}
$SeedRvt = [System.IO.Path]::GetFullPath($SeedRvt)

if (-not (Test-Path -LiteralPath $MainIfc)) {
    Write-Error "Demo main IFC not found: $MainIfc"
    exit 1
}
if (-not (Test-Path -LiteralPath $RoomsIfc)) {
    Write-Error "Demo rooms IFC not found: $RoomsIfc"
    exit 1
}
if (-not (Test-Path -LiteralPath $SeedRvt)) {
    Write-Error "Seed RVT not found: $SeedRvt — create demo\in\empty_R$RevitYear.rvt (see docs\empty-rvt-seed-README.txt)."
    exit 1
}

if ($UseTempOutput) {
    $OutDir = Join-Path $env:TEMP "bygg_pipeline_e2e_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
} else {
    $OutDir = Join-Path $ExtRoot "demo\out"
}
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

$MainRvt  = Join-Path $OutDir "main_model.rvt"
$RoomsRvt = Join-Path $OutDir "rooms_model.rvt"

Write-Host "E2E output directory: $OutDir"
Write-Host "Starting Run-ByggPipelineSetup (long run) ..."

$Launcher = Join-Path $PSScriptRoot "Run-ByggPipelineSetup.ps1"
$launcherArgs = @{
    MainIfcPath    = $MainIfc
    RoomsIfcPath   = $RoomsIfc
    MainModelPath  = $MainRvt
    RoomsModelPath = $RoomsRvt
    RbpSeedRvt     = $SeedRvt
    RevitYear      = $RevitYear
    RoomsImporter  = $RoomsImporter
}
if ($PublishAcc) {
    $launcherArgs['PublishAcc'] = $true
    if ($AccAccountId) { $launcherArgs['AccAccountId'] = $AccAccountId }
    if ($AccProjectId) { $launcherArgs['AccProjectId'] = $AccProjectId }
    if ($AccFolderId) { $launcherArgs['AccFolderId'] = $AccFolderId }
    if ($CloudModelName) { $launcherArgs['CloudModelName'] = $CloudModelName }
}
if ($SkipSetup) {
    $launcherArgs['SkipSetup'] = $true
}
& $Launcher @launcherArgs

exit $LASTEXITCODE
