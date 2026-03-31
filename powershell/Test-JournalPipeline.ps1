<#
.SYNOPSIS
    Diagnostic test harness for IFC import automation (journals + BatchRvt).

.DESCRIPTION
    Tests journal templates and the BatchRvt Graphisoft import step against
    the demo IFC files.  Dry-run phases generate and inspect journals without
    starting Revit.  Live phases invoke Revit (journal or BatchRvt) and
    analyse the result.

    Phases:
      0  Pre-flight   -- verify environment, files, paths, plugins
      1  Dry-link     -- generate link journal, diff against recorded journal
      2  Dry-import   -- generate import journal, inspect for known issues
      3  Live Graphisoft -- BatchRvt + graphisoft_import_rbp.py (main IFC)
      4  Live-import  -- run Revit with import journal (rooms IFC link path)

.PARAMETER Phase
    Which phase(s) to run.  Default: 0,1,2  (dry-run only).
    Use -Phase 0,1,2,3 to include the live BatchRvt Graphisoft test (needs seed .RVT).
    Use -Phase 0,1,2,3,4 for the full test suite.

.PARAMETER RbpSeedRvt
    Path to the minimal host .RVT for BatchRvt (Phase 3).  Default: demo\in\empty_R{RevitYear}.rvt,
    or BYGG_RBP_SEED_RVT when set.

.PARAMETER RevitYear
    Revit version year.  Default: 2025.

.PARAMETER TimeoutMinutes
    Max wait for Revit to exit during live tests.  Default: 15.

.EXAMPLE
    # Dry-run only (safe, no Revit started)
    .\Test-JournalPipeline.ps1

.EXAMPLE
    # Include live link test
    .\Test-JournalPipeline.ps1 -Phase 0,1,2,3

.EXAMPLE
    # Full suite
    .\Test-JournalPipeline.ps1 -Phase 0,1,2,3,4
#>

param(
    [int[]]$Phase = @(0, 1, 2),
    [int]$RevitYear = 2025,
    [int]$TimeoutMinutes = 15,
    [string]$RbpSeedRvt = ""
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths (scripts in .\powershell\; repo root is parent)
# ---------------------------------------------------------------------------
$RepoRoot = Split-Path $PSScriptRoot -Parent
$ExtDir   = $RepoRoot
$DemoIn   = Join-Path $ExtDir "demo\in"
$TplDir   = Join-Path $RepoRoot "archive\journal-automation\journal_templates"
$TestDir  = Join-Path $env:TEMP "rbp_bygg_pipeline\test_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $TestDir -Force | Out-Null
$TestDir  = [System.IO.Path]::GetFullPath($TestDir)  # resolve 8.3 short names

$MainIfc   = Join-Path $DemoIn "A1_2b_BIM_XXX_0001_00.ifc"
$RoomsIfc  = Join-Path $DemoIn "A1_2b_BIM_XXX_0003_00.ifc"
$RecordedLinkJournal  = Join-Path $DemoIn "journal.empty-linking.txt"
$RecordedImportJournal = Join-Path $DemoIn "journal.empty-importing.txt"

$GraphisoftImportTemplate = Join-Path $TplDir "ifc_graphisoft_import.template.txt"
$LinkTemplate   = Join-Path $TplDir "ifc_link.template.txt"
$ImportTemplate = Join-Path $TplDir "ifc_open_import.template.txt"

$RevitExe = "C:\Program Files\Autodesk\Revit $RevitYear\Revit.exe"
$RevitJournalsDir = "$env:LOCALAPPDATA\Autodesk\Revit\Autodesk Revit $RevitYear\Journals"

$ByggImporterDllSrc   = Join-Path $ExtDir "tools\ByggstyrningIFCImporter\bin\Release\ByggstyrningIFCImporter.dll"
$ImporterAddinSrc = Join-Path $ExtDir "tools\ByggstyrningIFCImporter\ByggstyrningIFCImporter.addin"
$AddinsDir     = "$env:APPDATA\Autodesk\Revit\Addins\$RevitYear"

$BatchRvtExe = Join-Path $env:LOCALAPPDATA "RevitBatchProcessor\BatchRvt.exe"

if ([string]::IsNullOrWhiteSpace($RbpSeedRvt)) {
    if (-not [string]::IsNullOrWhiteSpace($env:BYGG_RBP_SEED_RVT)) {
        $RbpSeedRvt = $env:BYGG_RBP_SEED_RVT
    } else {
        $RbpSeedRvt = Join-Path $DemoIn "empty_R$RevitYear.rvt"
    }
}
$RbpSeedRvt = [System.IO.Path]::GetFullPath($RbpSeedRvt)

$PassCount = 0
$FailCount = 0
$WarnCount = 0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Header($text) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}

function Pass($msg) {
    $script:PassCount++
    Write-Host "  [PASS] $msg" -ForegroundColor Green
}

function Fail($msg) {
    $script:FailCount++
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
}

function Warn($msg) {
    $script:WarnCount++
    Write-Host "  [WARN] $msg" -ForegroundColor Yellow
}

function Info($msg) {
    Write-Host "  [INFO] $msg" -ForegroundColor Gray
}

function Check($condition, $passMsg, $failMsg) {
    if ($condition) { Pass $passMsg } else { Fail $failMsg }
}

function GenerateGraphisoftImportJournal {
    $tpl = Get-Content $GraphisoftImportTemplate -Raw -Encoding UTF8
    return $tpl -replace '\{\{REVIT_VERSION\}\}', "$RevitYear.000"
}

function GenerateLinkJournal {
    param([string]$IfcPath, [string]$OutputRvt)

    $IfcPath = [System.IO.Path]::GetFullPath($IfcPath)
    $OutputRvt = [System.IO.Path]::GetFullPath($OutputRvt)
    $ifcFilename = [System.IO.Path]::GetFileName($IfcPath)
    $hostRvt = [System.IO.Path]::ChangeExtension($OutputRvt, ".host.rvt")

    $tpl = Get-Content $LinkTemplate -Raw -Encoding UTF8
    return $tpl `
        -replace '\{\{IFC_FILE_PATH\}\}',        $IfcPath `
        -replace '\{\{IFC_FILENAME\}\}',          $ifcFilename `
        -replace '\{\{LINK_HOST_RVT_PATH\}\}',   $hostRvt `
        -replace '\{\{REVIT_VERSION\}\}',         "$RevitYear.000"
}

function GenerateImportJournal {
    param([string]$IfcPath, [string]$OutputRvt)

    $IfcPath = [System.IO.Path]::GetFullPath($IfcPath)
    $OutputRvt = [System.IO.Path]::GetFullPath($OutputRvt)
    $ifcFilename = [System.IO.Path]::GetFileName($IfcPath)
    $hostRvt = [System.IO.Path]::ChangeExtension($OutputRvt, ".host.rvt")

    $tpl = Get-Content $ImportTemplate -Raw -Encoding UTF8
    return $tpl `
        -replace '\{\{IFC_FILE_PATH\}\}',        $IfcPath `
        -replace '\{\{IFC_FILENAME\}\}',          $ifcFilename `
        -replace '\{\{LINK_HOST_RVT_PATH\}\}',   $hostRvt `
        -replace '\{\{REVIT_VERSION\}\}',         "$RevitYear.000"
}

function AnalyseRevitJournal {
    <#
    .SYNOPSIS
        Reads Revit's OWN output journal (the one it writes during replay)
        and extracts errors, warnings, and key events.
    #>
    param([string[]]$JournalDir, [datetime]$StartedAfter)

    $journals = @()
    foreach ($dir in $JournalDir) {
        $journals += Get-ChildItem $dir -Filter "journal.*.txt" -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -gt $StartedAfter }
    }
    $journals = $journals | Sort-Object LastWriteTime -Descending

    if (-not $journals) {
        Warn "No Revit output journal found after $($StartedAfter.ToString('HH:mm:ss'))"
        return $null
    }

    $jrnFile = $journals[0]
    Info "Revit output journal: $($jrnFile.Name) ($([math]::Round($jrnFile.Length / 1KB)) KB)"

    $lines = Get-Content $jrnFile.FullName -ErrorAction SilentlyContinue
    if (-not $lines) {
        Warn "Could not read Revit output journal"
        return $null
    }

    $result = @{
        Path            = $jrnFile.FullName
        TotalLines      = $lines.Count
        JournalErrors   = @()
        ApiErrors       = @()
        CrashIndicators = @()
        KeyEvents       = @()
    }

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        # Journal replay errors (mismatches, unexpected dialogs, desync)
        # JOURNAL_MARKER_TAIL_END alone is normal end-of-playback; only flag it
        # if accompanied by "Execution did not correspond" or "was skipped"
        if ($line -match "Execution did not correspond|JournalData.*from file was skipped|JournalData.*not found in file") {
            $result.JournalErrors += "Line $($i+1): $($line.Trim().Substring(0, [Math]::Min(250, $line.Trim().Length)))"
        }

        # API errors from add-ins
        if ($line -match "API_ERROR") {
            $result.ApiErrors += "Line $($i+1): $($line.Trim().Substring(0, [Math]::Min(200, $line.Trim().Length)))"
        }

        # Crash or fatal indicators
        if ($line -match "FATAL|Crash|UnhandledException|StackOverflow|OutOfMemory") {
            $result.CrashIndicators += "Line $($i+1): $($line.Trim().Substring(0, [Math]::Min(200, $line.Trim().Length)))"
        }

        # Key events: file opens, saves, plugin commands
        if ($line -match "FileDialog.*IDOK|File Name.*IDOK|Save|ID_IFC_LINK|ID_REVIT_FILE_OPEN|ID_APP_EXIT|Transaction Successful" -and $line -notmatch "^'") {
            $result.KeyEvents += "Line $($i+1): $($line.Trim().Substring(0, [Math]::Min(200, $line.Trim().Length)))"
        }
    }

    return $result
}

# =====================================================================
#  PHASE 0 -- Pre-flight checks
# =====================================================================
if ($Phase -contains 0) {
    Header "Phase 0: Pre-flight checks"

    Check (Test-Path $RevitExe)      "Revit.exe found"          "Revit.exe NOT found: $RevitExe"
    Check (Test-Path $MainIfc)       "Main IFC exists in demo\\in (0001_00, $([math]::Round((Get-Item $MainIfc).Length / 1MB)) MB)"  "Main IFC NOT found: $MainIfc"
    Check (Test-Path $RoomsIfc)      "Rooms IFC exists in demo\\in (0003_00, $([math]::Round((Get-Item $RoomsIfc).Length / 1MB)) MB)" "Rooms IFC NOT found: $RoomsIfc"
    Check (Test-Path $GraphisoftImportTemplate) "Graphisoft import template exists" "Graphisoft import template NOT found"
    Check (Test-Path $LinkTemplate)  "Link template exists (for rooms)" "Link template NOT found"
    Check (Test-Path $ImportTemplate) "Import (open) template exists" "Import template NOT found: $ImportTemplate"
    if (Test-Path $RecordedLinkJournal) {
        Pass "Recorded link journal exists (for diff)"
    } else {
        Info "Recorded link journal not in repo (optional baseline for diff): demo\in\journal.empty-linking.txt"
    }
    if (Test-Path $RecordedImportJournal) {
        Pass "Recorded import journal exists (for diff)"
    } else {
        Info "Recorded import journal not in repo (optional baseline for diff): demo\in\journal.empty-importing.txt"
    }

    # ByggstyrningIFCImporter add-in
    Check (Test-Path $ByggImporterDllSrc)   "ByggstyrningIFCImporter.dll built (Release)" "ByggstyrningIFCImporter.dll NOT found -- run: dotnet build -c Release"
    Check (Test-Path $ImporterAddinSrc) "ByggstyrningIFCImporter.addin exists"        "ByggstyrningIFCImporter.addin NOT found"

    # Graphisoft plugin (required for CorrectIFCImport)
    $gsDir = "C:\Program Files\Graphisoft\IFC Model Exchange with Archicad for Revit $RevitYear\$RevitYear"
    $gsRcm = Join-Path $gsDir "RevitConnectionManaged.dll"
    Check (Test-Path $gsRcm) "Graphisoft RevitConnectionManaged.dll found" "Graphisoft plugin NOT found at $gsDir"

    # Check BatchRvt (Phase 1a main IFC + Phase 2)
    Check (Test-Path $BatchRvtExe) "BatchRvt.exe found" "BatchRvt.exe NOT found (needed for main IFC import and setup/merge/convert)"

    $graphisoftRbp = Join-Path $ExtDir "scripts\rbp\setup\graphisoft_import_rbp.py"
    Check (Test-Path $graphisoftRbp) "graphisoft_import_rbp.py present" "graphisoft_import_rbp.py NOT found"

    $seedReadme = Join-Path $ExtDir "docs\empty-rvt-seed-README.txt"
    Check (Test-Path $seedReadme) "empty-rvt-seed-README.txt present" "Seed README NOT found"

    $sv = Join-Path $DemoIn "empty_R$RevitYear.rvt"
    if (Test-Path -LiteralPath $sv) {
        Pass "Seed RVT present (empty_R$RevitYear.rvt; live Phase 3 can run)"
    } else {
        Info "No seed in demo\in (create empty_R$RevitYear.rvt for live Phase 3; see docs\empty-rvt-seed-README.txt)"
    }

    # Check Revit journals directory
    Check (Test-Path $RevitJournalsDir) "Revit journals dir exists" "Revit journals dir NOT found: $RevitJournalsDir"

    # Check for running Revit instances
    $revitProcs = Get-Process -Name "Revit" -ErrorAction SilentlyContinue
    if ($revitProcs) {
        Warn "Revit is currently running (PID: $($revitProcs.Id -join ', ')). Close it before live tests."
    } else {
        Pass "No Revit instances running"
    }

    # Path length / space check
    Info "Main IFC path length: $($MainIfc.Length) chars"
    if ($MainIfc.Length -gt 250) { Warn "Path > 250 chars; might hit MAX_PATH" }
    if ($MainIfc -match ' ') { Info "Path contains spaces (normal for this project, but watch journal escaping)" }

    # Check that the existing RVT from manual link is present
    $existingRvt = Join-Path $DemoIn "A1_2b_BIM_XXX_0001_00.ifc.RVT"
    if (Test-Path $existingRvt) {
        Pass "Existing linked RVT found ($([math]::Round((Get-Item $existingRvt).Length / 1MB)) MB) -- can compare results"
    } else {
        Info "No existing linked RVT for comparison"
    }

    Info "Test output directory: $TestDir"
}

# =====================================================================
#  PHASE 1 -- Dry-run: generate link journal + inspect
# =====================================================================
if ($Phase -contains 1) {
    Header "Phase 1: Dry-run -- Generate Graphisoft import journal (main model)"

    $journal = GenerateGraphisoftImportJournal
    $journalPath = Join-Path $TestDir "test_graphisoft_import_journal.txt"
    [System.IO.File]::WriteAllText($journalPath, $journal, (New-Object System.Text.UTF8Encoding $false))
    Info "Generated journal: $journalPath ($($journal.Length) chars)"

    # --- Check: no leftover placeholders ---
    $leftover = [regex]::Matches($journal, '\{\{[A-Z_]+\}\}')
    Check ($leftover.Count -eq 0) "No unresolved placeholders" "Unresolved placeholders: $($leftover.Value -join ', ')"

    # --- Check: Version directive matches RevitYear ---
    $verMatch = $journal -match "$RevitYear\.000"
    Check $verMatch "Version directive set to $RevitYear.000" "Version directive MISSING"

    # --- Check: key Jrn commands present in correct order ---
    $requiredCmds = @(
        'CrsJournalScript',
        'ID_FILE_NEW_CHOOSE_TEMPLATE',
        'Transaction Successful.*Create Type Previews',
        'Byggstyrning-IFC-Importer.*ByggstyrningImportIFC.*Byggstyrning\.IFCImporter\.ImportCommand',
        'ID_APP_EXIT'
    )
    $journalLines = $journal -split "`n"
    $lastIdx = -1
    foreach ($pat in $requiredCmds) {
        $found = $false
        for ($i = $lastIdx + 1; $i -lt $journalLines.Count; $i++) {
            if ($journalLines[$i] -match $pat) {
                $found = $true
                $lastIdx = $i
                break
            }
        }
        if ($found) {
            Pass "Command present in order: $pat  (line $($lastIdx + 1))"
        } else {
            Fail "Command NOT found after line $($lastIdx + 1): $pat"
        }
    }

    # --- Check: no IFC file paths in journal (all config via env vars) ---
    $ifcPathInJournal = $journal -match '\.ifc"'
    Check (-not $ifcPathInJournal) "No IFC file paths in journal (config via env vars)" "Journal contains IFC path -- should use env vars only"

    Info ""
    Info "Production: Run-ByggPipelineSetup Phase 1a uses BatchRvt + graphisoft_import_rbp.py (no journal)."
    Info "This dry-run still validates the optional journal template for diagnostics."
    Info "  Add-in replicates Graphisoft IFCImporter + CorrectIFCImport pipeline"
    Info "  Config via BYGG_IFC_* environment variables (set by PowerShell) for ByggstyrningIFCImporter"

    # --- Display the full generated journal for manual review ---
    Info ""
    Info "Full generated journal saved: $journalPath"
    $genFunctional = ($journal -split "`r?`n") | Where-Object { $_ -match '^\s*Jrn\.' }
    Info "Functional lines ($($genFunctional.Count)):"
    $genFunctional | ForEach-Object { Info "  $_" }
}

# =====================================================================
#  PHASE 2 -- Dry-run: generate import journal + inspect
# =====================================================================
if ($Phase -contains 2) {
    Header "Phase 2: Dry-run -- Generate import journal (link + extract .ifc.RVT)"

    $testImportRvt = Join-Path $TestDir "test_import_rooms.rvt"
    $journal = GenerateImportJournal -IfcPath $RoomsIfc -OutputRvt $testImportRvt
    $journalPath = Join-Path $TestDir "test_import_journal.txt"
    [System.IO.File]::WriteAllText($journalPath, $journal, (New-Object System.Text.UTF8Encoding $false))
    Info "Generated journal: $journalPath ($($journal.Length) chars)"

    # --- Check: no leftover placeholders ---
    $leftover = [regex]::Matches($journal, '\{\{[A-Z_]+\}\}')
    Check ($leftover.Count -eq 0) "No unresolved placeholders" "Unresolved placeholders: $($leftover.Value -join ', ')"

    # --- Check: IFC path present in FileDialog ---
    $absRoomsIfc = [System.IO.Path]::GetFullPath($RoomsIfc)
    $fdMatch = $journal -match [regex]::Escape($absRoomsIfc)
    Check $fdMatch "IFC absolute path present in FileDialog data" "IFC path NOT found in generated journal"

    # --- Check: host RVT path present (throwaway) ---
    $hostRvt = [System.IO.Path]::ChangeExtension($testImportRvt, ".host.rvt")
    $fnMatch = $journal -match [regex]::Escape($hostRvt)
    Check $fnMatch "Host RVT (throwaway) path present in Save data" "Host RVT path NOT found"

    # --- Check: key commands present in order ---
    $requiredCmds = @(
        'CrsJournalScript',
        'ID_FILE_NEW_CHOOSE_TEMPLATE',
        'TabActivated:Insert',
        'ID_IFC_LINK',
        '"FileDialog".*IDOK',
        'Transaction Successful.*Link IFC File',
        'ID_REVIT_FILE_SAVE',
        'Transaction Successful.*Relativize links',
        'ID_APP_EXIT'
    )
    $journalLines = $journal -split "`n"
    $lastIdx = -1
    foreach ($pat in $requiredCmds) {
        $found = $false
        for ($i = $lastIdx + 1; $i -lt $journalLines.Count; $i++) {
            if ($journalLines[$i] -match $pat) {
                $found = $true
                $lastIdx = $i
                break
            }
        }
        if ($found) {
            Pass "Command present in order: $pat  (line $($lastIdx + 1))"
        } else {
            Fail "Command NOT found after line $($lastIdx + 1): $pat"
        }
    }

    Info ""
    Info "Strategy: link IFC -> extract .ifc.RVT cache as the imported rooms model"
    Info "  The .ifc.RVT created by Revit IS a full document with imported geometry."
    Info "  The host project (.host.rvt) is discarded after run."
    Info "Generated journal saved: $journalPath"
}

# =====================================================================
#  PHASE 3 -- Live test: Graphisoft main IFC via BatchRvt
# =====================================================================
if ($Phase -contains 3) {
    Header "Phase 3: Live test -- Graphisoft import main IFC (BatchRvt)"

    $revitProcs = Get-Process -Name "Revit" -ErrorAction SilentlyContinue
    if ($revitProcs) {
        Fail "Revit is running (PID: $($revitProcs.Id -join ', ')). Close it first."
    } elseif (-not (Test-Path -LiteralPath $BatchRvtExe)) {
        Fail "BatchRvt.exe not found at $BatchRvtExe"
    } elseif (-not (Test-Path -LiteralPath $RbpSeedRvt)) {
        Fail "RBP seed model not found: $RbpSeedRvt (see docs\empty-rvt-seed-README.txt)"
    } elseif (-not (Test-Path -LiteralPath $ByggImporterDllSrc)) {
        Fail "ByggstyrningIFCImporter.dll not found -- build tools\ByggstyrningIFCImporter first"
    } else {
        $LibDir = Join-Path $ExtDir "lib"
        $rbpLocal = Join-Path $TestDir "rbp_scripts"
        New-Item -ItemType Directory -Path $rbpLocal -Force | Out-Null
        $syncSources = @(
            @{ Src = $LibDir; Filter = "*.py" },
            @{ Src = (Join-Path $LibDir "revit"); Filter = "*.py" },
            @{ Src = (Join-Path $ExtDir "scripts\rbp\setup"); Filter = "*_rbp.py" }
        )
        foreach ($src in $syncSources) {
            if (Test-Path -LiteralPath $src.Src) {
                Get-ChildItem -LiteralPath $src.Src -Filter $src.Filter -File -ErrorAction SilentlyContinue | ForEach-Object {
                    [System.IO.File]::Copy($_.FullName, (Join-Path $rbpLocal $_.Name), $true)
                }
            }
        }
        $settingsSrc = Join-Path $ExtDir "settings.json"
        if (Test-Path $settingsSrc) {
            Copy-Item $settingsSrc (Join-Path $rbpLocal "settings.json") -Force
        }

        Info "--- Deploying ByggstyrningIFCImporter add-in ---"
        [IO.File]::Copy($ByggImporterDllSrc,   (Join-Path $AddinsDir "ByggstyrningIFCImporter.dll"),   $true)
        [IO.File]::Copy($ImporterAddinSrc, (Join-Path $AddinsDir "ByggstyrningIFCImporter.addin"), $true)
        $deployedAddinSize = (Get-Item (Join-Path $AddinsDir "ByggstyrningIFCImporter.addin")).Length
        if ($deployedAddinSize -gt 0) {
            Pass "Add-in deployed to $AddinsDir (addin=$deployedAddinSize bytes)"
        } else {
            Fail "Deployed .addin is 0 bytes (OneDrive dehydration?) -- check source file"
        }

        $testOutputRvt = Join-Path $TestDir "test_graphisoft_main.rvt"
        $resultPath    = Join-Path $TestDir "graphisoft_result.json"
        $logPath       = Join-Path $TestDir "graphisoft_addin.log"
        $absMainIfc    = [System.IO.Path]::GetFullPath($MainIfc)
        $dllPath       = [System.IO.Path]::GetFullPath($ByggImporterDllSrc)

        $env:BYGG_IFC_PATH          = $absMainIfc
        $env:BYGG_IFC_OUTPUT_PATH       = $testOutputRvt
        $env:BYGG_IFC_RESULT_PATH       = $resultPath
        $env:BYGG_IFC_LOG_PATH          = $logPath
        $env:BYGG_IFC_AUTO_JOIN         = "0"
        $env:BYGG_IFC_CORRECT_OFF_AXIS  = "0"
        $env:BYGG_IFC_IMPORT_ALL_PARAMS = "1"
        $env:BYGG_IFC_IMPORTER_DLL  = $dllPath

        Info "Env: BYGG_IFC_PATH=$absMainIfc"
        Info "Env: BYGG_IFC_OUTPUT_PATH=$testOutputRvt"
        Info "Env: BYGG_IFC_RESULT_PATH=$resultPath"
        Info "Seed RVT (file list): $RbpSeedRvt"

        $taskScript = Join-Path $rbpLocal "graphisoft_import_rbp.py"
        if (-not (Test-Path -LiteralPath $taskScript)) {
            Fail "graphisoft_import_rbp.py not synced to $rbpLocal"
        }

        $fileListPath = Join-Path $TestDir "filelist_graphisoft.txt"
        [System.IO.File]::WriteAllText($fileListPath, $RbpSeedRvt, (New-Object System.Text.UTF8Encoding $false))
        $rbpLogFolder = Join-Path $TestDir "rbp_logs"
        New-Item -ItemType Directory -Path $rbpLogFolder -Force | Out-Null
        $batchRvtOut = Join-Path $TestDir "batchrvt_graphisoft_test.log"

        $rbpArgs = @(
            "--task_script", $taskScript,
            "--file_list",   $fileListPath,
            "--revit_version", $RevitYear,
            "--log_folder",  $rbpLogFolder
        )

        $startTime = Get-Date
        Info "Starting BatchRvt at $($startTime.ToString('HH:mm:ss')) ..."
        Info "Args: $($rbpArgs -join ' ')"

        $exitCode = 0
        try {
            & $BatchRvtExe @rbpArgs > $batchRvtOut 2>&1
            $exitCode = $LASTEXITCODE
        } catch {
            Fail "BatchRvt failed to start: $_"
            $exitCode = 99
        }

        Info "BatchRvt exit code: $exitCode"

        @("BYGG_IFC_PATH","BYGG_IFC_OUTPUT_PATH","BYGG_IFC_RESULT_PATH","BYGG_IFC_LOG_PATH",
          "BYGG_IFC_AUTO_JOIN","BYGG_IFC_CORRECT_OFF_AXIS","BYGG_IFC_IMPORT_ALL_PARAMS","BYGG_IFC_IMPORTER_DLL") | ForEach-Object {
            Remove-Item "Env:\$_" -ErrorAction SilentlyContinue
        }

        Check ($exitCode -eq 0) "BatchRvt exited with code 0" "BatchRvt exited with code $exitCode (see $batchRvtOut)"

        if (Test-Path $batchRvtOut) {
            Info "BatchRvt log (tail):"
            Get-Content $batchRvtOut -Tail 25 | ForEach-Object { Info "  $_" }
        }

        Info ""
        Info "--- ByggstyrningIFCImporter result JSON ---"
        if (Test-Path $resultPath) {
            $resultJson = Get-Content $resultPath -Raw | ConvertFrom-Json
            Check ($resultJson.success -eq $true) "Add-in reported success" "Add-in reported failure: $($resultJson.error)"
            if ($resultJson.graphisoft_applied -eq $true) {
                Pass "Graphisoft CorrectIFCImport was applied"
            } else {
                Warn "Graphisoft correction was NOT applied (native import only)"
            }
        } else {
            Fail "No result sidecar at $resultPath"
        }

        if (Test-Path $logPath) {
            $logLines = Get-Content $logPath
            Info "Add-in log ($($logLines.Count) lines):"
            $logLines | Select-Object -Last 15 | ForEach-Object { Info "  $_" }
        }

        Info ""
        Info "--- Output verification ---"
        if (Test-Path $testOutputRvt) {
            $outSizeMB = [math]::Round((Get-Item $testOutputRvt).Length / 1MB, 1)
            Pass "Output RVT created: $testOutputRvt ($outSizeMB MB)"
            Check ($outSizeMB -gt 10) "Output size > 10 MB (geometry present)" "Output too small ($outSizeMB MB) -- might be empty"
        } else {
            Fail "Output RVT NOT created at $testOutputRvt"
        }
    }
}

# =====================================================================
#  PHASE 4 -- Live test: Import rooms IFC via link + .ifc.RVT extract
# =====================================================================
if ($Phase -contains 4) {
    Header "Phase 4: Live test -- Import rooms IFC (link + extract .ifc.RVT)"

    if ($Phase -contains 3) {
        Info "Waiting for Revit to fully exit after Phase 3 (BatchRvt) ..."
        Start-Sleep -Seconds 15
        $waitTries = 0
        while ($waitTries -lt 24) {
            $stillRevit = Get-Process -Name "Revit" -ErrorAction SilentlyContinue
            if (-not $stillRevit) { break }
            Start-Sleep -Seconds 5
            $waitTries++
        }
        if ($stillRevit) {
            Info "Revit still present after wait (PIDs: $($stillRevit.Id -join ', ')) — Phase 4 may still fail; close Revit manually if needed."
        }
    }

    $revitProcs = Get-Process -Name "Revit" -ErrorAction SilentlyContinue
    if ($revitProcs) {
        Fail "Revit is running (PID: $($revitProcs.Id -join ', ')). Close it first."
    } else {
        # Copy IFC to temp dir so the .ifc.RVT cache is created there
        $ifcWorkDir = Join-Path $TestDir "ifc_import_work"
        New-Item -ItemType Directory -Path $ifcWorkDir -Force | Out-Null
        $tempIfc = Join-Path $ifcWorkDir ([System.IO.Path]::GetFileName($RoomsIfc))
        Copy-Item $RoomsIfc $tempIfc
        Info "Copied rooms IFC to: $tempIfc"

        $testImportRvt = Join-Path $TestDir "test_import_rooms.rvt"
        $journal = GenerateImportJournal -IfcPath $tempIfc -OutputRvt $testImportRvt
        $journalPath = Join-Path $TestDir "live_import_journal.txt"
        [System.IO.File]::WriteAllText($journalPath, $journal, (New-Object System.Text.UTF8Encoding $false))
        Info "Journal: $journalPath"

        $expectedCache = "$tempIfc.RVT"
        Info "Expected .ifc.RVT cache: $expectedCache"
        $hostRvt = [System.IO.Path]::ChangeExtension($testImportRvt, ".host.rvt")
        Info "Host project (throwaway): $hostRvt"
        Info "Final output: $testImportRvt"

        $startTime = Get-Date
        Info "Starting Revit at $($startTime.ToString('HH:mm:ss')) (timeout: $TimeoutMinutes min) ..."
        $proc = Start-Process -FilePath $RevitExe `
                              -ArgumentList "`"$journalPath`"" `
                              -PassThru

        Info "Revit PID: $($proc.Id)"

        $checkInterval = 10
        $elapsed = 0
        $lastStatus = ""

        while (-not $proc.HasExited -and $elapsed -lt ($TimeoutMinutes * 60)) {
            Start-Sleep -Seconds $checkInterval
            $elapsed += $checkInterval

            $newJournals = @()
            foreach ($dir in @($RevitJournalsDir, $TestDir)) {
                $newJournals += Get-ChildItem $dir -Filter "journal.*.txt" -ErrorAction SilentlyContinue |
                    Where-Object { $_.LastWriteTime -gt $startTime }
            }

            $status = "running ${elapsed}s"
            if ($newJournals) {
                $latest = $newJournals | Sort-Object LastWriteTime -Descending | Select-Object -First 1
                $status += " | journal: $($latest.Name) ($([math]::Round($latest.Length / 1KB)) KB)"
            }

            # Check if cache appeared
            if (Test-Path $expectedCache) {
                $cacheSizeMB = [math]::Round((Get-Item $expectedCache).Length / 1MB, 1)
                $status += " | .ifc.RVT: $cacheSizeMB MB"
            }

            if ($status -ne $lastStatus) {
                Info $status
                $lastStatus = $status
            }
        }

        if ($proc.HasExited) {
            $duration = ((Get-Date) - $startTime).TotalSeconds
            Info "Revit exited after $([math]::Round($duration))s with code $($proc.ExitCode)"
            Check ($proc.ExitCode -eq 0) "Revit exit code 0" "Revit exit code: $($proc.ExitCode)"
        } else {
            Fail "Revit did not exit within $TimeoutMinutes minutes -- killing"
            try { $proc.Kill() } catch {}
        }

        # Extract the .ifc.RVT cache as the imported rooms model
        Info ""
        Info "--- Extracting .ifc.RVT cache ---"
        if (Test-Path $expectedCache) {
            $cacheSizeMB = [math]::Round((Get-Item $expectedCache).Length / 1MB, 1)
            Pass ".ifc.RVT cache created: $expectedCache ($cacheSizeMB MB)"

            Copy-Item $expectedCache $testImportRvt -Force
            if (Test-Path $testImportRvt) {
                $outSizeMB = [math]::Round((Get-Item $testImportRvt).Length / 1MB, 1)
                Pass "Rooms RVT extracted: $testImportRvt ($outSizeMB MB)"
            } else {
                Fail "Failed to copy .ifc.RVT to output path"
            }
        } else {
            Fail ".ifc.RVT cache NOT created at $expectedCache"
            # Check if it was created in the original demo dir instead
            $altCache = "$RoomsIfc.RVT"
            if (Test-Path $altCache) {
                Warn "Found .ifc.RVT in original location: $altCache"
                Warn "This means Revit used the original path, not the temp copy."
            }
        }

        # Clean up throwaway host project
        if (Test-Path $hostRvt) {
            $hostSize = [math]::Round((Get-Item $hostRvt).Length / 1KB, 0)
            Info "Removing throwaway host project: $hostRvt ($hostSize KB)"
            Remove-Item $hostRvt -Force -ErrorAction SilentlyContinue
        }

        # Post-mortem
        Info ""
        Info "--- Post-mortem: Revit output journal analysis ---"
        $analysis = AnalyseRevitJournal -JournalDir @($RevitJournalsDir, $TestDir) -StartedAfter $startTime
        if ($analysis) {
            Info "Journal: $($analysis.TotalLines) lines ($($analysis.Path))"

            if ($analysis.JournalErrors.Count -gt 0) {
                Fail "Journal replay errors: $($analysis.JournalErrors.Count)"
                $analysis.JournalErrors | Select-Object -First 5 | ForEach-Object { Info "  $_" }
            } else {
                Pass "No journal replay errors detected"
            }

            if ($analysis.CrashIndicators.Count -gt 0) {
                Fail "Crash indicators found: $($analysis.CrashIndicators.Count)"
                $analysis.CrashIndicators | ForEach-Object { Info "  $_" }
            } else {
                Pass "No crash indicators"
            }

            if ($analysis.KeyEvents.Count -gt 0) {
                Info "Key events:"
                $analysis.KeyEvents | Select-Object -First 10 | ForEach-Object { Info "  $_" }
            }

            Copy-Item $analysis.Path (Join-Path $TestDir "revit_output_import.txt") -ErrorAction SilentlyContinue
        }
    }
}

# =====================================================================
#  Summary
# =====================================================================
Header "Test Summary"
Write-Host ""
Write-Host "  Passed: $PassCount" -ForegroundColor Green
Write-Host "  Failed: $FailCount" -ForegroundColor $(if ($FailCount -gt 0) { "Red" } else { "Green" })
Write-Host "  Warnings: $WarnCount" -ForegroundColor $(if ($WarnCount -gt 0) { "Yellow" } else { "Green" })
Write-Host ""
Write-Host "  Test artifacts: $TestDir" -ForegroundColor Gray
Write-Host ""

if ($FailCount -gt 0) {
    Write-Host "  RESULT: FAILURES DETECTED" -ForegroundColor Red
    exit 1
} else {
    Write-Host "  RESULT: ALL CHECKS PASSED" -ForegroundColor Green
    exit 0
}
