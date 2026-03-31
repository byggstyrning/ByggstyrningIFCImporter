<#
.SYNOPSIS
  Runs ByggstyrningRoomImporter.Inspect on an IFC to show IfcRelSpaceBoundary counts and per-space geometry.

.DESCRIPTION
  Use this to see whether an ArchiCAD (or other) export includes space boundaries and whether our
  IfcCurveBoundaryExtractor can read ConnectionGeometry. Requires .NET 8.

.PARAMETER IfcPath
  Path to .ifc (default: demo\in\A1_2b_BIM_XXX_0003_00.ifc).

.PARAMETER SpaceGlobalId
  Optional IfcSpace GlobalId; default is first space in file.

.EXAMPLE
  .\archive\Diagnose-IfcSpaceBoundaries.ps1
.EXAMPLE
  .\archive\Diagnose-IfcSpaceBoundaries.ps1 -IfcPath "D:\project\model.ifc" -SpaceGlobalId "abc123..."
#>

param(
    [string]$IfcPath = "",
    [string]$SpaceGlobalId = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$DemoIn = Join-Path $RepoRoot "demo\in"
$InspectProj = Join-Path $RepoRoot "tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter.Inspect\ByggstyrningRoomImporter.Inspect.csproj"

if (-not (Test-Path -LiteralPath $InspectProj)) {
    Write-Error "Inspect project not found: $InspectProj"
}

if ([string]::IsNullOrWhiteSpace($IfcPath)) {
    $IfcPath = Join-Path $DemoIn "A1_2b_BIM_XXX_0003_00.ifc"
}

$IfcPath = [System.IO.Path]::GetFullPath($IfcPath)
if (-not (Test-Path -LiteralPath $IfcPath)) {
    Write-Error "IFC not found: $IfcPath"
}

$args = @($IfcPath)
if (-not [string]::IsNullOrWhiteSpace($SpaceGlobalId)) {
    $args += "--space"
    $args += $SpaceGlobalId
}

Push-Location (Split-Path $InspectProj -Parent)
try {
    dotnet run -c Release --project $InspectProj -- @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
