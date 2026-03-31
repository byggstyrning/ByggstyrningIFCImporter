<#
.SYNOPSIS
    Extracts ArchiCAD IFC Exchange plugin commands from the latest Revit journal.

.DESCRIPTION
    After manually performing an "Improved IFC Import" or "Link IFC" through
    the Graphisoft ArchiCAD plugin in Revit, this script locates the latest
    journal file and extracts the plugin-specific lines.

    The extracted commands are written under
        archive\journal-automation\journal_templates\archicad_import_commands.txt
    (repo root), used by the ifc_import journal templates in that folder.

    Run this script once after:
      - A fresh ArchiCAD plugin install
      - A plugin or Revit version upgrade
      - Changing the target IFC file for the Import workflow

.PARAMETER RevitYear
    Revit version year.  Default: 2025.

.PARAMETER OutputFile
    Where to write the extracted commands.
    Default: archive\journal-automation\journal_templates\archicad_import_commands.txt (repo root).

.PARAMETER JournalFile
    Explicit path to a journal file.  If omitted, the script locates the
    latest  journal.*.txt  in the Revit journals folder.

.EXAMPLE
    .\Capture-ArchiCADJournal.ps1 -RevitYear 2025

.EXAMPLE
    .\Capture-ArchiCADJournal.ps1 -JournalFile "C:\path\to\journal.0042.txt"
#>

param(
    [int]$RevitYear = 2025,

    [string]$OutputFile = "",

    [string]$JournalFile = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$JournalTemplatesDir = Join-Path $RepoRoot "archive\journal-automation\journal_templates"

# --- Resolve output path --------------------------------------------------
if (-not $OutputFile) {
    $OutputFile = Join-Path $JournalTemplatesDir "archicad_import_commands.txt"
}

# --- Locate the journal file ----------------------------------------------
if ($JournalFile) {
    if (-not (Test-Path -LiteralPath $JournalFile)) {
        Write-Error "Journal file not found: $JournalFile"
        exit 1
    }
} else {
    $journalsDir = Join-Path $env:LOCALAPPDATA "Autodesk\Revit\Autodesk Revit $RevitYear\Journals"
    if (-not (Test-Path $journalsDir)) {
        Write-Error "Revit journals folder not found: $journalsDir"
        exit 1
    }
    $latest = Get-ChildItem $journalsDir -Filter "journal.*.txt" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        Write-Error "No journal.*.txt files found in: $journalsDir"
        exit 1
    }
    $JournalFile = $latest.FullName
    Write-Host "Using latest journal: $JournalFile"
}

# --- Read and filter the journal ------------------------------------------
# We extract Jrn.* lines that are related to the ArchiCAD plugin, plus
# context lines needed for journal replay (DocWarnDialog, APIStringString,
# TaskDialogResult for "Document Opened", etc.)
#
# The regex patterns below match the functional Jrn commands (not comments).

$patterns = @(
    '^\s*Jrn\.\w+.*Graphisoft'            # Graphisoft external commands
    '^\s*Jrn\.\w+.*IFC Exchange'           # IFC Exchange panel references
    '^\s*Jrn\.\w+.*IFCImporter'            # Improved IFC Import class
    '^\s*Jrn\.\w+.*IFCLinker'              # Link IFC class
    '^\s*Jrn\.Data\s+"APIStringString'     # Plugin journal data map
    '^\s*Jrn\.PushButton.*DocWarnDialog'   # Document warning OK
    '^\s*Jrn\.Data\s+"TaskDialogResult".*Document Opened'  # Document opened dialog
)

$combinedPattern = ($patterns | ForEach-Object { "($_)" }) -join "|"

$allLines = Get-Content -LiteralPath $JournalFile -Encoding UTF8
$captured = @()
$prevWasMatchPrefix = $false

for ($i = 0; $i -lt $allLines.Count; $i++) {
    $line = $allLines[$i]

    # Skip comment-only lines (lines starting with ' that aren't continuations)
    if ($line -match "^'") {
        $prevWasMatchPrefix = $false
        continue
    }

    # Check if this is a VBScript line continuation from a previous matched line
    if ($prevWasMatchPrefix) {
        # Continuation lines typically have leading whitespace and content, or
        # start with a comma.  We keep consuming until the line does NOT end in " _"
        $captured += $line
        $prevWasMatchPrefix = $line.TrimEnd() -match ' _$'
        continue
    }

    # Check against our patterns
    if ($line -match $combinedPattern) {
        $captured += $line
        $prevWasMatchPrefix = $line.TrimEnd() -match ' _$'
    }
}

if ($captured.Count -eq 0) {
    Write-Warning "No ArchiCAD plugin commands found in: $JournalFile"
    Write-Warning "Make sure you recorded an IFC Import or Link operation before running this script."
    exit 1
}

# --- Write output ---------------------------------------------------------
$outputDir = Split-Path $OutputFile -Parent
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$header = @(
    "' ArchiCAD plugin commands captured from Revit journal"
    "' Source: $JournalFile"
    "' Captured: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "' Revit: $RevitYear"
    "'"
)

$output = ($header + $captured) -join "`r`n"
[System.IO.File]::WriteAllText($OutputFile, $output, (New-Object System.Text.UTF8Encoding $false))

Write-Host ""
Write-Host "Captured $($captured.Count) lines to: $OutputFile"
Write-Host ""
Write-Host "--- Preview ---"
$captured | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }
if ($captured.Count -gt 15) { Write-Host "  ... ($($captured.Count - 15) more lines)" }
