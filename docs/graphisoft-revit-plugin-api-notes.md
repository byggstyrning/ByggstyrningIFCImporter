# Graphisoft “IFC Model Exchange with Archicad for Revit” — internal API notes

These notes support the Byggstyrning IFC importer that calls into Graphisoft’s Revit add-in (see [`tools/ByggstyrningIFCImporter/ByggstyrningIFCImporter.cs`](../tools/ByggstyrningIFCImporter/ByggstyrningIFCImporter.cs)). They are derived from **public metadata**, **documented call sites in this repo**, and **optional local decompilation** for your own reference — not a substitute for Graphisoft documentation or support.

**Related:** [xBIM → Revit rooms investigation](xbim-revit-rooms-investigation/INVESTIGATION.md) (why an alternative to the “Improve IFC Import” path exists for automation, **E2E defaults**, merge/save, **IFC parameter parity** for xBIM-created rooms).

### E2E split (full pipeline)

- **Main IFC (Phase 1a)** uses **`ByggstyrningIFCImporter`** here — same stack as Graphisoft **Improved IFC Import** (`OpenIFCDocument` + `CorrectIFCImport`), including `BYGG_IFC_IMPORT_ALL_PARAMS` for IFC parameter mapping in Revit.
- **Rooms IFC (Phase 1b)** defaults to **xBIM** (`ByggstyrningRoomImporter`) in `powershell\Run-ByggPipelineSetup.ps1`; use **`-RoomsImporter Graphisoft`** to import the rooms IFC with the same Graphisoft path as 1a instead.
- Merged rooms for coordination are copied into **`main_model.rvt`** during **`merge_rooms`**; see INVESTIGATION §10–11 for save semantics (`target_saved`) and how to close the **IFC parameter gap** on xBIM rooms.

---

## 1. Byggstyrning IFC integration in this repo (`ByggstyrningIFCImporter`)

Implementation: [`tools/ByggstyrningIFCImporter/ByggstyrningIFCImporter.cs`](../tools/ByggstyrningIFCImporter/ByggstyrningIFCImporter.cs).

### 1.1 Pipeline (order of operations)

1. Read `BYGG_IFC_*`, `BYGG_GRAPHISOFT_*`, and `BYGG_REVIT_YEAR` environment variables (see table below).
2. Build `IFCImportOptions` and call `Application.OpenIFCDocument(ifcPath, importOpts)` (Revit native IFC import first).
3. Instantiate `RevitConnection.RevitConnectionManaged` with the Graphisoft install directory and EDM database path.
4. Call `CorrectIFCImport` (transaction name `"Improve IFC Import"` in Graphisoft’s add-in).
5. Run `CorrectViews` (phase filters, `{3D}` view, discipline/display).
6. `SaveAs` to `BYGG_IFC_OUTPUT_PATH`, close document, write JSON result (including whether Graphisoft correction ran).

RBP entry points live under `scripts/rbp/setup/` (e.g. `graphisoft_import_rbp.py`).

### 1.2 Environment variables

| Variable | Role |
|----------|------|
| `BYGG_IFC_PATH` | Input `.ifc` (required). |
| `BYGG_IFC_OUTPUT_PATH` | Output `.rvt` path (required). |
| `BYGG_IFC_RESULT_PATH` | Optional JSON sidecar: `success`, `graphisoft_applied`, `error`, plus `corrected_floors`, `corrected_rooms`, `project_info_imported`, `phase_mapping`, `graphisoft_dir`, `edm_database_path`, `revit_version`, `addin_name`, `addin_version`, `preflight_error` (when applicable). |
| `BYGG_IFC_LOG_PATH` | Optional append-only log file. |
| `BYGG_IFC_AUTO_JOIN` | Passed to `IFCImportOptions.AutoJoin` (`1` / `true`). |
| `BYGG_IFC_CORRECT_OFF_AXIS` | `IFCImportOptions.AutocorrectOffAxisLines`. |
| `BYGG_IFC_IMPORT_ALL_PARAMS` | Passed through to Graphisoft as `importIFCParameters` (default true). |
| `BYGG_GRAPHISOFT_DIR` | Absolute path to the Graphisoft plugin folder that contains `RevitConnectionManaged.dll` (overrides default `Program Files\...\{year}\{year}`). |
| `BYGG_REVIT_YEAR` | e.g. `2025` — used to build default Graphisoft install path and registry subkey when `BYGG_GRAPHISOFT_DIR` / `BYGG_GRAPHISOFT_REGISTRY_KEY` are not set (default `2025`). |
| `BYGG_GRAPHISOFT_REGISTRY_KEY` | Full `HKCU` subkey for Graphisoft settings (e.g. `Software\GRAPHISOFT\IFC Model Exchange with Archicad for Revit 2025`). Overrides the key derived from `BYGG_REVIT_YEAR`. |
| `BYGG_IFC_REMOVE_DOOR_WINDOW_2D` | If set (`1` / `true`), passed as `removeAllDoorWindow2D` to `CorrectIFCImport`. If **unset**, the importer uses **`!` `EnableDoorWindow2DHandling`** from registry (see §1.3). |
| `BYGG_IFC_TRUE_NORTH_FROM_GEOM` | If set (`1` / `true`), enables true-north-from-geometry for `CorrectIFCImport`. If **unset**, the importer uses registry: `ImportAngleToTrueNorthAs == 2`. |
| `BYGG_IFC_VERBOSE` | If `1` / `true`, logs Graphisoft `ImportProgressStepIds` / `ExportProgressStepIds` to `BYGG_IFC_LOG_PATH`. |

**Preflight:** Before `OpenIFCDocument`, the importer verifies the Graphisoft install (or `BYGG_GRAPHISOFT_DIR`) contains `RevitConnectionManaged.dll`, and that the EDM folder exists and is writable.

### 1.3 Registry (`HKCU\Software\GRAPHISOFT\IFC Model Exchange with Archicad for Revit {year}`)

The `{year}` suffix matches `BYGG_REVIT_YEAR` (default `2025`) unless `BYGG_GRAPHISOFT_REGISTRY_KEY` sets the full subkey explicitly.

Read by `ByggstyrningIFCImporter` when env overrides (§1.2) are not provided — not an exhaustive list of everything Graphisoft may store:

| Value | Use in this importer |
|-------|----------------|
| `EDMDatabasePath` | Folder for Graphisoft EDM data; if missing, this code falls back to `%LocalAppData%\Graphisoft\EDMDB` (created if needed; must be writable). |
| `EnableDoorWindow2DHandling` | Boolean; when `BYGG_IFC_REMOVE_DOOR_WINDOW_2D` is unset, the importer passes **`!`** this value as `removeAllDoorWindow2D` into `CorrectIFCImport`. |
| `ImportAngleToTrueNorthAs` | Integer; when `BYGG_IFC_TRUE_NORTH_FROM_GEOM` is unset, the importer sets **true north from geometry** when this value **`== 2`**. |

**EULA:** The interactive Graphisoft command checks EULA before import; this automated path does not. If correction fails unexpectedly, ensure the add-in has been opened once and EULA accepted (documented prerequisite).

Other Graphisoft UI options may exist only in the interactive add-in; this importer does not mirror all of them.

---

## 2. Install layout (typical)

| Item | Example path (Revit 2025) |
|------|---------------------------|
| Plugin root | `C:\Program Files\Graphisoft\IFC Model Exchange with Archicad for Revit 2025\2025\` |
| Managed bridge | `RevitConnectionManaged.dll` |
| Native engine | `RevitConnectionNative.dll` (and many GS/IFC support DLLs) |
| Registry (settings) | e.g. `HKCU\Software\GRAPHISOFT\IFC Model Exchange with Archicad for Revit 2025` |

Use `BYGG_GRAPHISOFT_DIR` / `BYGG_REVIT_YEAR` when the install is not under the default `Program Files\Graphisoft\…\2025` layout.

---

## 3. Managed API in `RevitConnectionManaged.dll` (namespace `RevitConnection`)

Observed from **Revit 2025** Graphisoft install; names may be stable across years but verify after upgrades.

### 3.1 `RevitConnectionManaged`

| Member | Purpose |
|--------|---------|
| **Constructor** | `(applicationPlace, databasePlace, importProgressStepChange, exportProgressStepChange, progressUpdateUI, getLocalizedString)` — initializes native bridge + localization map. This importer passes no-op delegates except the string delegate (returns `""`). |
| **`CorrectIFCImport`** | Post-processes a document opened from IFC. Typical signature (decompiler): `fileName`, `document`, `transactionName`, `out correctedFloors`, `out correctedRooms`, `out projectInfoImported`, `out phaseMapping`, `ref preferredPhaseForViews`, `removeAllDoorWindow2D`, `importIFCParameters`, `revitRoomsNotProperlyEnclosed`, `trueNorthFromGeomRepContext`. |
| **`CorrectIFCExport`** | Exports Revit → IFC with counts and toggles (shared coordinates, empty stories, custom MEP properties, etc.). Not used by this import path. |
| **`FailuresProcessing`** | Instance method suitable for wiring to Revit failure events (Graphisoft’s own handler). |
| **`ChangeProgressStep`**, **`UpdateProgressUI`** | Progress reporting when delegates are implemented. |

Decompiled **private** helpers (names only — behaviour inferred): `CorrectFloor`, `CorrectRooms`, `ConvertFootPrint`, `CreateRoomSeparationLines` — relevant when comparing to **ByggstyrningRoomImporter** footprint / boundary logic.

### 3.2 Delegates (for progress / localization)

| Delegate | Signature |
|----------|-----------|
| `ImportProgressStepChangeDelegate` | `void(ImportProgressStepIds stepId)` |
| `ExportProgressStepChangeDelegate` | `void(ExportProgressStepIds stepId)` |
| `ProgressUpdateUIDelegate` | `void()` |
| `GetLocalizedStringDelegate` | `string(LocalizedIFCStringIds stringId)` |

### 3.3 `ImportProgressStepIds` (complete)

1. `STEP_IMPORT_OPENINGDATABASE`  
2. `STEP_IMPORT_CORRECTING_SLABS`  
3. `STEP_IMPORT_CORRECTING_PROJECTNORTH`  
4. `STEP_IMPORT_CORRECTING_PROJECTINFO`  
5. `STEP_IMPORT_CORRECTING_PROJECTBASEPOINT`  
6. `STEP_IMPORT_CREATING_SHAREDPARAMETERS`  
7. `STEP_IMPORT_CORRECTING_RENOVATIONANDPHASING`  

### 3.4 `ExportProgressStepIds` (complete)

1. `STEP_EXPORT_COLLECTING_DATAFROMMODEL`  
2. `STEP_EXPORT_EXPORTING_EMPTYSTORIES`  
3. `STEP_EXPORT_EXPORTING_GRIDS`  
4. `STEP_EXPORT_EXPORTING_RENOVATIONANDPHASING`  
5. `STEP_EXPORT_EXPORTING_MEPELEMENTS`  
6. `STEP_CORRECTING_ROTATION_OF_STRUCTURAL_ELEMENTS`  

### 3.5 Other **public** types in the same assembly

Useful if you extend automation beyond this import path:

- `MEPExporter`, `MEPElementCollector`, `MEPConnector` — MEP-oriented export helpers.  
- `Utility` — string/UTF-8 helpers used internally.  
- `FamilyLoadOptions` — `IFamilyLoadOptions` implementation.  
- `TransactionFailuresPreprocessor` — `IFailuresPreprocessor` implementation.  
- `CreateRoomSeparationLinesFunctionObject` — room-separation workflow (primary ctor).  

`RevitConnection.Common` contains mostly **internal** native-interop structs in the shipped DLL; rely on the public `RevitConnection` surface unless you own matching native headers.

---

## 4. Decompiling locally (optional)

The assemblies are **.NET**; tools such as **ILSpy** or **`ilspycmd`** (global .NET tool) can export C# for inspection.

Example (output stays **outside git** — do not commit decompiled third-party source):

```powershell
$src = "C:\Program Files\Graphisoft\IFC Model Exchange with Archicad for Revit 2025\2025\RevitConnectionManaged.dll"
$out = Join-Path $env:TEMP "graphisoft-revitconnection-decompile"
ilspycmd $src -o $out -p
```

**Expectations**

- **`RevitConnectionManaged`** is largely **C++/CLI**; decompiled C# is often noisy (mangled STL types, `unsafe`, huge `-Module-.cs`). The **public methods and enums** are still easy to read; private methods may be hard to follow.
- Heavy lifting may sit in **`RevitConnectionNative.dll`** (native) — use the managed layer as your map, or vendor docs/debug symbols if available.
- **Legal:** use decompilation only under your organisation’s policies and the Graphisoft license; treat output as **internal reference**, not something to redistribute.

---

## 5. What “deeper” decompilation buys you

| Goal | Useful? |
|------|--------|
| Confirm **parameter meanings** for `CorrectIFCImport` / export | Yes — cross-check flags with registry (`ImportAngleToTrueNorthAs`, door/window 2D, etc.). |
| See **high-level import phases** (slabs, north, project info, phasing) | Yes — aligns with `ImportProgressStepIds` and explains logs. |
| Understand **room boundary / footprint** handling vs xBIM path | Partly — compare to `ByggstyrningRoomImporter` footprint extraction. |
| Eliminate **UI/dialog** issues in journal/RBP | **Partially** — see §7 (`ArchicadConnection.dll` shows dialogs, journal keys, and `executeSilent`). A headless path still needs this importer, xBIM, or vendor support. |
| Full readable source | No — mixed native/managed and C++/CLI limits fidelity. |

---

## 6. Safer documentation sources to combine

- This repo: `ByggstyrningIFCImporter`, `graphisoft_import_rbp.py`, `powershell/Capture-ArchiCADJournal.ps1`, `archive/journal-automation/journal_templates/`.
- Revit journals: which commands and transactions run when the add-in is used interactively.
- Graphisoft release notes / help for the same major version as your install.

---

## 7. Going further down the stack (what decompiles, what does not)

The add-in is layered. **`ilspycmd` / ILSpy only recover readable C# from pure .NET assemblies.**

| Assembly | Kind | “Further decompile”? |
|----------|------|----------------------|
| **`ArchicadConnection.dll`** | Managed (C# / WinForms) | **Yes — best readability.** Namespace `Graphisoft`: `IFCImporter` (`IExternalCommand`), `ImportDialog`, `ImproveIFCExchange`, `IFCExporter`, link helpers, telemetry, EULA. This is where **file dialogs**, **journal `JournalData`** keys (e.g. `FILEPATH_DATASTRING`), and the **`executeSilent`** flag are implemented. Interactive import ends up in `ImproveIFCExchange.Execute` → `RevitConnectionManaged`. |
| **`RevitConnectionManaged.dll`** | Managed (C++/CLI) | **Yes**, but output is **noisy** (see §4). Good for signatures and enums; poor for step-by-step logic. |
| **`RevitConnectionNative.dll`**, **`IFC.dll`**, most `GS*.dll`, **`InteroperabilitySupport.dll`**, etc. | **Native** (or mixed) | **No** useful C# — use **`dumpbin /exports`** / **Dependencies** for entry points, or a **disassembler** (Ghidra, IDA) if you need pseudocode. Expect heavy lifting and IFC parsing here. |

### 7.1 “Link IFC” ribbon button (`Graphisoft.IFCLinker`) — what it actually does

Decompiled `IFCLinker` (`IExternalCommand`) is a **thin wrapper** — not a second linking engine:

1. Require EULA accepted (`EULAUtility`).
2. Send telemetry (`Utility.SendTelemetryData`).
3. **`UIApplication.PostCommand(RevitCommandId.LookupPostableCommandId((PostableCommand)<id>))`** — i.e. fire Revit’s **built‑in** “Link IFC” / “Link IFC File” workflow (same as the core Revit UI), **not** `OpenIFCDocument`, **not** `ImproveIFCExchange`, **not** `RevitConnectionManaged`.

So the initial intuition was **directionally right**: ArchiCAD’s **Link IFC** does **not** apply Graphisoft’s “Improved IFC Import” / `CorrectIFCImport` geometry correction. Anything special about linking is whatever **Revit** does for linked IFCs in that version — plus Graphisoft’s EULA gate and telemetry on button press.

**Contrast — Import / Improved path:** `Graphisoft.IFCImporter` opens the custom import dialog, calls `OpenIFCDocument`, then `ImproveIFCExchange.Execute` → **`RevitConnectionManaged.CorrectIFCImport`** (and optional result dialogs). That is the path tied to **Graphisoft-specific post-processing**.

This matches the repo’s journal notes: templates can **`PostCommand` the same link command** without going through the ribbon class (`archive/journal-automation/journal_templates/ifc_link.template.txt`, `.../journal_templates/README.md`).

**Why this importer bypasses the top layer:** `ByggstyrningIFCImporter` calls `OpenIFCDocument` and `RevitConnectionManaged.CorrectIFCImport` directly — it does not load `Graphisoft.IFCImporter` / `ImproveIFCExchange`, so you avoid `ImportDialog` and much of the journal surface area (you still rely on Graphisoft’s correction engine and EDM paths).

**Command (local temp only):**

```powershell
$gs = "C:\Program Files\Graphisoft\IFC Model Exchange with Archicad for Revit 2025\2025"
ilspycmd (Join-Path $gs "ArchicadConnection.dll") -o (Join-Path $env:TEMP "graphisoft-archicadconnection-decompile") -p
```

---

*Last updated: 2026-03-30 — §7.1 `IFCLinker` = `PostCommand` native Link IFC; §7 stack table.*
