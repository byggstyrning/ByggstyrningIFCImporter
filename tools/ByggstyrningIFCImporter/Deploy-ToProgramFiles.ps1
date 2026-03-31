<#
.SYNOPSIS
  Deploy ByggstyrningIFCImporter to Revit's Program Files AddIns folder (requires Admin).

.DESCRIPTION
  WARNING: Revit 2025 treats DLLs under Program Files\Autodesk\Revit\...\AddIns as "internal"
  add-ins and expects them to be signed like Autodesk builds. Unsigned ByggstyrningIFCImporter.dll will
  log DBG_WARN and may NOT load — the ribbon command will never exist.

  Prefer normal user deployment: %APPDATA%\Autodesk\Revit\Addins\<year>\ (Run-ByggPipelineSetup / Deploy-ByggstyrningIFCImporter).

  If you previously copied this add-in here, remove the folder:
    C:\Program Files\Autodesk\Revit 2025\AddIns\ByggstyrningIFCImporter

  Paths are derived from this script's location — do not rely on $src/$dest variables.

.EXAMPLE
  # From elevated PowerShell (Run as Administrator):
  cd "<repo-root>\tools\ByggstyrningIFCImporter"
  .\Deploy-ToProgramFiles.ps1

.EXAMPLE
  pwsh -Command "Start-Process pwsh -Verb RunAs -ArgumentList '-ExecutionPolicy Bypass -File `"$PWD\Deploy-ToProgramFiles.ps1`"'"
#>
[CmdletBinding()]
param(
    [int]$RevitYear = 2025
)

$ErrorActionPreference = 'Stop'
$toolDir = $PSScriptRoot
$dllSrc = Join-Path $toolDir "bin\Release\ByggstyrningIFCImporter.dll"
$addinSrc = Join-Path $toolDir "ByggstyrningIFCImporter.addin"
$destDir = "C:\Program Files\Autodesk\Revit $RevitYear\AddIns\ByggstyrningIFCImporter"

if (-not (Test-Path $dllSrc)) {
    Write-Error "Build Release first: dotnet build -c Release`nMissing: $dllSrc"
}
if (-not (Test-Path $addinSrc)) {
    Write-Error "Missing manifest: $addinSrc"
}

New-Item -ItemType Directory -Path $destDir -Force | Out-Null
Copy-Item -LiteralPath $dllSrc -Destination (Join-Path $destDir "ByggstyrningIFCImporter.dll") -Force
# Byte copy for OneDrive-dehydrated .addin if needed
[IO.File]::Copy($addinSrc, (Join-Path $destDir "ByggstyrningIFCImporter.addin"), $true)

Write-Host "OK: Deployed to $destDir"
Get-ChildItem $destDir | Format-Table Name, Length -AutoSize
