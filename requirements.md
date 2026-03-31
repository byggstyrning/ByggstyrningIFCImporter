# Requirements

This document lists **software, build, and runtime** prerequisites for the Bygg IFC pipeline. It is **not** a Python `pip` requirements file: RBP task scripts run **IronPython inside Revit / BatchRvt** with `clr` and the Revit API.

## 1. Host OS

- **Windows** (Revit, Revit Batch Processor, and PowerShell orchestration).

## 2. Autodesk

- **Revit** — Default target year is **2025**; use `-RevitYear` in [`powershell/Run-ByggPipelineSetup.ps1`](powershell/Run-ByggPipelineSetup.ps1) to match your installation.
- **ACC publish (optional)** — Only if you use `-PublishAcc`. You need valid hub (account), project, and folder IDs for `SaveAsCloudModel`; see the launcher’s parameter help.

## 3. Revit Batch Processor

- **BatchRvt.exe** — Typically under `%LOCALAPPDATA%\RevitBatchProcessor\` (see [`docs/README-pipeline.txt`](docs/README-pipeline.txt)).

## 4. Graphisoft

- **IFC Model Exchange for Archicad for Revit** (provides **CorrectIFCImport** and related assemblies).
- Revit year must match the installed add-in. The [ByggstyrningIFCImporter](tools/ByggstyrningIFCImporter/ByggstyrningIFCImporter.csproj) project references Graphisoft assemblies under `Program Files\Graphisoft\...` via `HintPath`; adjust if your install path differs.

## 5. Build toolchain

- **.NET SDK** capable of building **net48** projects.
- Build release add-ins, for example:

  ```powershell
  dotnet build "tools\ByggstyrningIFCImporter\ByggstyrningIFCImporter.csproj" -c Release
  ```

- **[ByggstyrningRoomImporter](tools/ByggstyrningRoomImporter/)** — Same Revit API `HintPath` convention (e.g. `C:\Program Files\Autodesk\Revit 2025\...`); update `.csproj` if you use another year.

## 6. Deploy

- Copy built **`.dll`** and **`.addin`** into `%APPDATA%\Autodesk\Revit\Addins\{year}\` (see [`tools/ByggstyrningIFCImporter/README.md`](tools/ByggstyrningIFCImporter/README.md), [`tools/ByggstyrningIFCImporter/Deploy-ToProgramFiles.ps1`](tools/ByggstyrningIFCImporter/Deploy-ToProgramFiles.ps1), and the orchestrator’s deploy steps).

## 7. Pipeline inputs

- **Seed `.rvt`** — A minimal metric project used as the BatchRvt file list for Phase 1; name it `demo/in/empty_R{RevitYear}.rvt` (e.g. `empty_R2025.rvt`). See [`docs/empty-rvt-seed-README.txt`](docs/empty-rvt-seed-README.txt). Pass `-RbpSeedRvt` if the default path is missing.
- **Demo IFCs** — Under `demo\in\` for trials; outputs can be directed next to the IFC or to a temp folder (see runbook).

## 8. Python runtime

- **IronPython 2.7** — Supplied with Revit / BatchRvt; no separate virtual environment.
- Some modules under `lib/revit/` import **pyrevit** (e.g. UI helpers). **Production RBP paths** rely on core setup/merge logic that does not require pyrevit; use pyrevit-dependent code only in interactive or pyRevit-hosted contexts.
