<#
.SYNOPSIS
  Build Release outputs and create zip files under dist/ for GitHub Releases.

.DESCRIPTION
  Requires a Windows machine with Revit, matching Revit API HintPaths in the .csproj files,
  and Graphisoft IFC Model Exchange for ByggstyrningIFCImporter.

.PARAMETER RevitYear
  Used in output zip names (e.g. 2025 -> ByggstyrningIFCImporter-RVT2025.zip).

.EXAMPLE
  cd <repo-root>
  .\scripts\Package-Release.ps1 -RevitYear 2025
#>
[CmdletBinding()]
param(
    [int]$RevitYear = 2025
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$Dist = Join-Path $RepoRoot 'dist'
New-Item -ItemType Directory -Path $Dist -Force | Out-Null

$ifcProj = Join-Path $RepoRoot 'tools\ByggstyrningIFCImporter\ByggstyrningIFCImporter.csproj'
$roomProj = Join-Path $RepoRoot 'tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\ByggstyrningRoomImporter.csproj'

Write-Host "Building ByggstyrningIFCImporter (Release)..."
dotnet build $ifcProj -c Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Building ByggstyrningRoomImporter (Release)..."
dotnet build $roomProj -c Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$tag = "RVT$RevitYear"
$ifcBin = Join-Path $RepoRoot 'tools\ByggstyrningIFCImporter\bin\Release'
$roomBin = Join-Path $RepoRoot 'tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\bin\Release'

$ifcZip = Join-Path $Dist "ByggstyrningIFCImporter-$tag.zip"
$roomZip = Join-Path $Dist "ByggstyrningRoomImporter-$tag.zip"

$ifcStaging = Join-Path $Dist "staging-ifc"
$roomStaging = Join-Path $Dist "staging-room"
Remove-Item -LiteralPath $ifcStaging, $roomStaging -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $ifcStaging -Force | Out-Null
Copy-Item -Path (Join-Path $ifcBin 'ByggstyrningIFCImporter.dll') -Destination $ifcStaging -Force
Copy-Item -Path (Join-Path $RepoRoot 'tools\ByggstyrningIFCImporter\ByggstyrningIFCImporter.addin') -Destination $ifcStaging -Force
@"
Install (ByggstyrningIFCImporter)
=================================
Copy ByggstyrningIFCImporter.dll and ByggstyrningIFCImporter.addin to:
  %APPDATA%\Autodesk\Revit\Addins\$RevitYear\

Prerequisites: Revit $RevitYear, Graphisoft IFC Model Exchange with Archicad for Revit $RevitYear.
"@ | Set-Content -Path (Join-Path $ifcStaging 'INSTALL.txt') -Encoding UTF8

Compress-Archive -Path (Join-Path $ifcStaging '*') -DestinationPath $ifcZip -Force

New-Item -ItemType Directory -Path $roomStaging -Force | Out-Null
Copy-Item -Path (Join-Path $roomBin '*') -Destination $roomStaging -Recurse -Force
@"
Install (ByggstyrningRoomImporter)
==================================
Keep this entire folder together (xBIM dependencies sit next to the DLL).

Point your pipeline environment variable BYGG_XBIM_ROOMS_DLL to:
  <this-folder>\ByggstyrningRoomImporter.dll

Prerequisites: Revit $RevitYear (same version as the build).
"@ | Set-Content -Path (Join-Path $roomStaging 'INSTALL.txt') -Encoding UTF8

Compress-Archive -Path (Join-Path $roomStaging '*') -DestinationPath $roomZip -Force

Remove-Item -LiteralPath $ifcStaging, $roomStaging -Recurse -Force

Write-Host "OK: $ifcZip"
Write-Host "OK: $roomZip"
Write-Host ""
Write-Host "Upload both zips to a GitHub Release (gh release create ... --attach dist\*.zip)."
