# Journal-based IFC automation — lessons (archived route)

**Sources:** In-repo docs and scripts (`docs/xbim-revit-rooms-investigation/INVESTIGATION.md`, `archive/journal-automation/journal_templates/README.md`, `powershell/Run-ByggPipelineSetup.ps1`, `powershell/Test-JournalPipeline.ps1`). This file captures the same technical conclusions as the investigation doc (no dependency on local Cursor transcript files).

**Status:** **Not used for the default bygg IFC pipeline today.** Phase 1 runs through **BatchRvt** + Python task scripts (`graphisoft_import_rbp.py`, `xbim_rooms_import_rbp.py`). Rooms IFC defaults to **xBIM / ByggstyrningRoomImporter**, not journal replay.

---

## What we tried to use journals for

1. **Link IFC (main model)** — `Graphisoft.IFCLinker` → standard Revit file dialog → journal can inject `Jrn.Data "FileDialog"` with a path. **This path is parameterizable** and was considered reliable for automation.

2. **Improved IFC Import (rooms / full import)** — `Graphisoft.IFCImporter` opens a **custom ArchiCAD dialog**. Revit’s journal only records the ribbon launch, **not** the plugin’s internal dialog sequence. **IFC path cannot be injected** via placeholders alone; teams relied on **re-recording** per IFC (see `archive/journal-automation/journal_templates/README.md`, capture workflow with `powershell/Capture-ArchiCADJournal.ps1`).

3. **Workarounds discussed in-repo:** link both IFCs and bind; **custom C# / xBIM** importer; UI automation — the approach that stuck for rooms was **ByggstyrningRoomImporter (xBIM + Revit API)** inside RBP, documented in INVESTIGATION.md §1–2.

---

## Why the production launcher moved away from “journal-first” Phase 1

| Issue | Lesson |
|--------|--------|
| Graphisoft **Improved IFC Import** UI | Not replay-friendly; brittle without per-file capture. |
| Need for **headless, repeatable** CI-style runs | **BatchRvt + add-in** avoids ribbon/dialog surface: ByggstyrningIFCImporter calls `OpenIFCDocument` + `CorrectIFCImport` directly (see `docs/graphisoft-revit-plugin-api-notes.md`). |
| Rooms model | Default **`-RoomsImporter Xbim`** avoids Graphisoft import dialog entirely for Phase 1b; optional **`-RoomsImporter Graphisoft`** still uses **RBP + `graphisoft_import_rbp.py`**, not a standalone journal file. |
| **Revit journal replay** | Fragile across Revit/plugin updates; output journals show desync / skipped `JournalData` — `powershell/Test-JournalPipeline.ps1` includes analysis helpers for that class of failure. |

---

## Dead code still in `powershell/Run-ByggPipelineSetup.ps1` (as of consolidation)

These functions exist but **are not invoked** by the main Phase 1 flow (grep shows no call sites outside their definitions):

- **`Invoke-GraphisoftImport`** — starts Revit with `archive/journal-automation/journal_templates/ifc_graphisoft_import.template.txt` + env vars for ByggstyrningIFCImporter.
- **`Invoke-JournalImport`** — `ifc_open_import.template.txt`: link IFC, use `.ifc.RVT` cache as rooms output.

The **live** paths are **`Invoke-RBPGraphisoftImport`** and **`Invoke-RBPXbimRoomsImport`**.

Keeping this note avoids re-wiring the launcher to journal-only flows without remembering why RBP won.

---

## What remains useful

- **`powershell/Test-JournalPipeline.ps1`** — dry-run / live diagnostics for templates and recorded journals.
- **`archive/journal-automation/journal_templates/`** — reference for **Link IFC** automation and for understanding Graphisoft command structure.
- **`Wait-RevitAfterBatchRvtForJournal`** — naming is historical; it **sleeps after BatchRvt** so the next Revit process does not collide with lingering work (not “we run a journal next” in the default path).

---

## Cross-references

- Current pipeline: `powershell/Run-ByggPipelineSetup.ps1` synopsis; operator runbook `docs/README-pipeline.txt` (keep in sync with script).
- xBIM rooms rationale: `docs/xbim-revit-rooms-investigation/INVESTIGATION.md`.
- Graphisoft internals: `docs/graphisoft-revit-plugin-api-notes.md`.
