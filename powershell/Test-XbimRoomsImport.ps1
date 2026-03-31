<#
.SYNOPSIS
    Smoke test: build ByggstyrningRoomImporter (if needed) and run -ImportRoomsIfcOnly with -RoomsImporter Xbim.

.DESCRIPTION
    Requires Revit, BatchRvt, demo IFC in demo\in, and demo\in\empty_R{RevitYear}.rvt (see docs\empty-rvt-seed-README.txt).
    Exit 0 when Run-ByggPipelineSetup.ps1 succeeds; inspect RW_RESULT and import_rooms step in the launcher output.

.PARAMETER RevitYear
    Revit version year (default: 2025).

.EXAMPLE
    .\Test-XbimRoomsImport.ps1
#>

param(
    [int]$RevitYear = 2025
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$Dll = Join-Path $RepoRoot "tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\bin\Release\ByggstyrningRoomImporter.dll"

if (-not (Test-Path -LiteralPath $Dll)) {
    Write-Host "Building ByggstyrningRoomImporter ..."
    dotnet build (Join-Path $RepoRoot "tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\ByggstyrningRoomImporter.csproj") -c Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$Launcher = Join-Path $PSScriptRoot "Run-ByggPipelineSetup.ps1"
& $Launcher -ImportRoomsIfcOnly -RoomsImporter Xbim -RevitYear $RevitYear @args
exit $LASTEXITCODE
