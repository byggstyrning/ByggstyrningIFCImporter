Bygg IFC pipeline — operator runbook
=====================================

Single orchestrator: powershell\Run-ByggPipelineSetup.ps1 (run from repository root, or cd powershell and use .\Run-ByggPipelineSetup.ps1).

Flow (see script .SYNOPSIS for all parameters):
  Phase 1a  BatchRvt + graphisoft_import_rbp.py + ByggstyrningIFCImporter  → main IFC → main .RVT
  Phase 1b  BatchRvt + xbim_rooms_import_rbp.py + ByggstyrningRoomImporter (default -RoomsImporter Xbim);
            or BatchRvt + graphisoft_import_rbp.py (-RoomsImporter Graphisoft)  → rooms IFC → rooms .RVT
  Phase 2   Two BatchRvt runs on main model: setup → merge rooms
  Phase 3   Optional: -PublishAcc — BatchRvt + publish_acc_rbp.py (ACC / SaveAsCloudModel)

Where things live (repo root = parent of .\powershell\)
--------------------------------------------------------
  RBP task scripts     scripts\rbp\setup\*_rbp.py, merge_rooms\, publish_acc\
  Shared Python library lib\
  Settings copy        settings.json (synced with scripts for RBP)
  Journal templates    archive\journal-automation\journal_templates\  (diagnostics only; default Phase 1 is not journal replay)
  PowerShell tools     powershell\Run-ByggPipelineSetup.ps1, Verify-ByggPipelinePrereqs.ps1, Test-JournalPipeline.ps1, Test-ByggPipelineFull.ps1, Capture-ArchiCADJournal.ps1

  (Legacy journal notes: archive/journal-automation/NOTES.md.)

Prerequisites
-------------
- Revit 2025 (or match -RevitYear)
- Revit Batch Processor: BatchRvt.exe under %LOCALAPPDATA%\RevitBatchProcessor\
- Graphisoft IFC Model Exchange for Revit 2025 (CorrectIFCImport)
- ByggstyrningIFCImporter built: dotnet build -c Release
  tools\ByggstyrningIFCImporter\ByggstyrningIFCImporter.csproj
- Seed .RVT for Phase 1 BatchRvt file list (minimal metric project; see docs\empty-rvt-seed-README.txt).
  Use demo\in\empty_R{RevitYear}.rvt (e.g. empty_R2025.rvt) saved from that Revit version.
  Committed demo IFCs are under demo\in\; seed .rvt files may be local-only — create or pass -RbpSeedRvt.

Quick check (PowerShell, from repo root): powershell\Verify-ByggPipelinePrereqs.ps1
  Add -Build to compile both add-ins in Release if DLLs are missing.

Full example (demo IFCs → outputs under %TEMP% so demo folder is not overwritten)
-----------------------------------------------------------------------------------
  $out = Join-Path $env:TEMP "bygg_ifc_run"
  New-Item -ItemType Directory -Path $out -Force | Out-Null
  cd <path-to-repo-root>

  .\powershell\Run-ByggPipelineSetup.ps1 `
    -MainIfcPath  "demo\in\A1_2b_BIM_XXX_0001_00.ifc" `
    -RoomsIfcPath "demo\in\A1_2b_BIM_XXX_0003_00.ifc" `
    -MainModelPath  "C:\Users\...\bygg_ifc_run\main_model.rvt" `
    -RoomsModelPath "C:\Users\...\bygg_ifc_run\rooms_model.rvt" `
    -RbpSeedRvt "demo\in\empty_R2025.rvt" `
    -RevitYear 2025

Or use defaults next to IFC (omit -MainModelPath / -RoomsModelPath) — writes .RVT
same folder as each IFC.

Partial reruns
--------------
  -SkipImport     requires -MainModelPath (use existing main RVT)
  -SkipRooms      skips merge_rooms RBP step only

Output: RW_RESULT JSON on stdout; diag log path printed at end; step sidecars under %TEMP%\rbp_bygg_pipeline\<JobId>\.

Automated E2E wrapper (optional): powershell\Test-ByggPipelineFull.ps1
