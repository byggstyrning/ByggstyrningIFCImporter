<#
.SYNOPSIS
  Removes IFC importer add-ins from Revit Program Files AddIns (run PowerShell as Administrator).

.DESCRIPTION
  Deletes subfolders for both the current name (ByggstyrningIFCImporter) and the legacy
  pre-rename name (NobelIFCImporter) under:
    C:\Program Files\Autodesk\Revit <year>\AddIns\

.NOTES
  Unsigned add-ins in Program Files\Autodesk\Revit\...\AddIns are rejected by Revit 2025
  (DBG_WARN: not signed as internal addin). Remove this copy and use %APPDATA% deploy only.

  If NobelIFCImporter.dll / .addin still appear under %APPDATA% or
  C:\ProgramData\Autodesk\Revit\Addins\<year>\, delete those files manually.
#>
[CmdletBinding()]
param([int]$RevitYear = 2025)

$base = "C:\Program Files\Autodesk\Revit $RevitYear\AddIns"
$folders = @(
    (Join-Path $base 'ByggstyrningIFCImporter'),
    (Join-Path $base 'NobelIFCImporter')
)

foreach ($path in $folders) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Host "Removed: $path"
    } else {
        Write-Host "Nothing to remove: $path"
    }
}
