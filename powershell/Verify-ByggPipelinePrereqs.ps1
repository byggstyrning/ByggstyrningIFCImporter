#Requires -Version 5.1
<#
.SYNOPSIS
    Check IFC pipeline prerequisites before Run-ByggPipelineSetup.ps1 or Test-ByggPipelineFull.ps1.

.DESCRIPTION
    Verifies: demo IFC paths, seed empty_R{RevitYear}.rvt, BatchRvt.exe, optional Release builds of
    ByggstyrningIFCImporter and ByggstyrningRoomImporter. Exit 0 if all required checks pass; 1 otherwise.

.PARAMETER RepoRoot
    Repository root (parent of .\powershell\). Default: parent of this script's directory.

.PARAMETER RevitYear
    Used for add-in path checks under %APPDATA%\Autodesk\Revit\Addins\{year}\ (informational).

.PARAMETER Build
    Run dotnet build -c Release for both add-in projects when DLLs are missing or when -ForceBuild.

.PARAMETER ForceBuild
    With -Build, always run dotnet build even if DLLs exist.

.EXAMPLE
    .\Verify-ByggPipelinePrereqs.ps1
.EXAMPLE
    .\Verify-ByggPipelinePrereqs.ps1 -Build
#>
param(
    [string]$RepoRoot = "",
    [int]$RevitYear = 2025,
    [switch]$Build,
    [switch]$ForceBuild
)

$ErrorActionPreference = "Stop"
if (-not $RepoRoot) { $RepoRoot = Split-Path $PSScriptRoot -Parent }
$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)

$issues = New-Object System.Collections.Generic.List[string]
$ok = New-Object System.Collections.Generic.List[string]

function Add-Issue([string]$msg) { [void]$issues.Add($msg); Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Add-Ok([string]$msg)   { [void]$ok.Add($msg); Write-Host "  [ OK ] $msg" -ForegroundColor Green }

Write-Host "Verify-ByggPipelinePrereqs (repo: $RepoRoot)" -ForegroundColor Cyan

$mainIfc  = Join-Path $RepoRoot "demo\in\A1_2b_BIM_XXX_0001_00.ifc"
$roomsIfc = Join-Path $RepoRoot "demo\in\A1_2b_BIM_XXX_0003_00.ifc"
$demoIn = Join-Path $RepoRoot "demo\in"
$seedRvt = Join-Path $demoIn "empty_R$RevitYear.rvt"

if (Test-Path -LiteralPath $mainIfc) { Add-Ok "Demo main IFC: $mainIfc" } else { Add-Issue "Demo main IFC not found: $mainIfc" }
if (Test-Path -LiteralPath $roomsIfc) { Add-Ok "Demo rooms IFC: $roomsIfc" } else { Add-Issue "Demo rooms IFC not found: $roomsIfc" }
if (Test-Path -LiteralPath $seedRvt) { Add-Ok "Seed RVT: $seedRvt" } else {
    Add-Issue "Seed RVT not found (expected $seedRvt). Create per docs\empty-rvt-seed-README.txt."
}

$batchRvt = Join-Path $env:LOCALAPPDATA "RevitBatchProcessor\BatchRvt.exe"
if (Test-Path -LiteralPath $batchRvt) { Add-Ok "BatchRvt: $batchRvt" } else { Add-Issue "BatchRvt.exe not found: $batchRvt" }

$ifcProj = Join-Path $RepoRoot "tools\ByggstyrningIFCImporter\ByggstyrningIFCImporter.csproj"
$roomProj = Join-Path $RepoRoot "tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\ByggstyrningRoomImporter.csproj"
function Find-ReleaseDll {
    param([string]$Root, [string]$Name)
    if (-not (Test-Path -LiteralPath $Root)) { return $null }
    Get-ChildItem -LiteralPath $Root -Recurse -Filter $Name -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\bin\\Release\\' } |
        Select-Object -First 1 -ExpandProperty FullName
}
$ifcDll = Find-ReleaseDll (Join-Path $RepoRoot "tools\ByggstyrningIFCImporter") "ByggstyrningIFCImporter.dll"
$roomDll = Find-ReleaseDll (Join-Path $RepoRoot "tools\ByggstyrningRoomImporter") "ByggstyrningRoomImporter.dll"

if ($Build -or $ForceBuild) {
    if (-not (Test-Path -LiteralPath $ifcProj)) { Add-Issue "IFC importer csproj missing: $ifcProj" }
    else {
        Write-Host "  Building ByggstyrningIFCImporter (Release)..." -ForegroundColor DarkGray
        & dotnet build $ifcProj -c Release 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Add-Ok "dotnet build ByggstyrningIFCImporter" } else { Add-Issue "dotnet build ByggstyrningIFCImporter failed (exit $LASTEXITCODE)" }
    }
    if (-not (Test-Path -LiteralPath $roomProj)) { Add-Issue "Room importer csproj missing: $roomProj" }
    else {
        Write-Host "  Building ByggstyrningRoomImporter (Release)..." -ForegroundColor DarkGray
        & dotnet build $roomProj -c Release 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Add-Ok "dotnet build ByggstyrningRoomImporter" } else { Add-Issue "dotnet build ByggstyrningRoomImporter failed (exit $LASTEXITCODE)" }
    }
} else {
    if ($ifcDll -and (Test-Path -LiteralPath $ifcDll)) { Add-Ok "ByggstyrningIFCImporter.dll (Release): $ifcDll" } else { Add-Issue "ByggstyrningIFCImporter.dll not found under tools\ByggstyrningIFCImporter\bin\Release (run with -Build)" }
    if ($roomDll -and (Test-Path -LiteralPath $roomDll)) { Add-Ok "ByggstyrningRoomImporter.dll (Release): $roomDll" } else { Add-Issue "ByggstyrningRoomImporter.dll not found under tools\ByggstyrningRoomImporter\...\bin\Release (run with -Build)" }
}

$addinDir = Join-Path $env:APPDATA "Autodesk\Revit\Addins\$RevitYear"
$ifcAddin = Join-Path $addinDir "ByggstyrningIFCImporter.addin"
if (Test-Path -LiteralPath $ifcAddin) { Add-Ok "User add-in manifest: $ifcAddin" } else { Write-Host "  [info] Optional: deploy ByggstyrningIFCImporter to $addinDir (see tools\ByggstyrningIFCImporter\README.md)" -ForegroundColor DarkYellow }

Write-Host ""
if ($issues.Count -eq 0) {
    Write-Host "All prerequisite checks passed." -ForegroundColor Green
    exit 0
}
Write-Host "Issues ($($issues.Count)):" -ForegroundColor Yellow
$issues | ForEach-Object { Write-Host "  - $_" }
exit 1
