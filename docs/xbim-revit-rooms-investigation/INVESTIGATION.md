# xBIM → Revit rooms: investigation notes

This document consolidates the discussion from a prior session about using **xBIM** (.NET) together with the **Revit API** to create Revit rooms from IFC spaces, as an alternative to the ArchiCAD “Improved IFC Import” path that relies on a non–journal-replayable dialog.

**Source:** Prior design sessions; authoritative paths and launcher behaviour are in `docs/README-pipeline.txt` and `powershell/Run-ByggPipelineSetup.ps1`.

**Status:** **ByggstyrningRoomImporter** is implemented (`tools/ByggstyrningRoomImporter/`). Full pipeline defaults: **Phase 1a** = Improved IFC Import via **ByggstyrningIFCImporter**; **Phase 1b** = rooms IFC via **xBIM** (`-RoomsImporter Xbim`). See **§10** below.

**See also:** [Graphisoft Revit plug-in — internal API notes](../graphisoft-revit-plugin-api-notes.md) (managed `RevitConnection` assembly, registry keys, decompilation workflow).

---

## 1. Problem being solved

- **Main IFC (link):** ArchiCAD “Link IFC” uses a standard file dialog; journal replay was considered workable.
- **Rooms IFC (import):** The ArchiCAD “Improved IFC Import” path exposes a **custom dialog** that does not automate reliably in a journal/RBP context.

A **rooms-only** pipeline that does not depend on that dialog can instead:

1. Parse the rooms IFC with xBIM (outside or inside a Revit-hosted .NET assembly).
2. Create **Level**, **Room**, and **room boundary** geometry in Revit via the Revit API.
3. Map IFC properties (e.g. `Pset_SpaceCommon`, project-specific psets) to Revit room parameters.

---

## 2. Why xBIM

- **C# / .NET** aligns with Revit add-ins and with loading a DLL from **IronPython** (`clr.AddReferenceToFileAndPath`) in RBP task scripts.
- xBIM provides **`IfcStore`** as the usual entry point for opening IFC models, and typed access to **`IfcSpace`**, **`IfcBuildingStorey`**, and relationships such as **`IfcRelSpaceBoundary`** (see xBIM docs: `IfcSpace.BoundedBy` → `IIfcRelSpaceBoundary`).
- Optional: **`Xbim.Geometry`** (or related geometry packages) if you need mesh/solid operations beyond raw relationships—scope depends on how clean your boundaries are.

Reference documentation:

- xBIM docs (IfcStore, IfcSpace): [https://docs.xbim.net/XbimDocs/](https://docs.xbim.net/XbimDocs/)
- Autodesk’s open-source Revit IFC importer (architecture reference, not required to fork): [https://github.com/Autodesk/revit-ifc](https://github.com/Autodesk/revit-ifc)

---

## 3. IFC → Revit mapping (rooms scope)

| IFC concept | Revit concept | Notes |
|-------------|---------------|--------|
| `IfcBuildingStorey` | `Level` | Match elevations; naming strategy (IFC `Name` vs index). |
| `IfcSpace` | `Room` | Placement / location; area from parameters or computed. |
| `IfcRelSpaceBoundary` / boundary curves | `Room` boundaries / `RoomBoundaryLines` | Coordinate transform IFC → Revit internal units (feet). |
| Property sets on space | Room instance / shared parameters | Map `Pset_SpaceCommon` and project psets explicitly. |

Full-building IFC import (walls, slabs, complex B-rep) was explicitly scoped **out** of the “rooms-only” idea; the main model could stay on **ArchiCAD link + journal** while rooms use this path.

---

## 4. Architecture options (from the transcript)

### A. `IIFCImporterServer`

Revit’s extension point used by Autodesk and third parties so that **standard IFC open/link** can invoke custom logic.

- **Pros:** Hooks into normal `Open` / link workflows; familiar to IFC tooling.
- **Cons:** Risk of **intercepting every IFC operation** unless you branch on filename, content, or delegate to the default handler. Conflicts with **ArchiCAD’s own registration** as an importer must be thought through (only one “active” behaviour at a time unless carefully delegated).

### B. Standalone C# class library + Revit API (called from IronPython)

A DLL (xBIM + RevitAPI) exposes a method such as “import rooms from this IFC path into the active document.”

- **Pros:** **No global hijack** of IFC import; clear RBP story: open a template RVT, call the DLL, save.
- **Cons:** Deploy **xBIM** and **Revit** assemblies (and dependencies) next to the DLL or install path; version alignment with Revit’s year.

### C. `IExternalCommand` / external application

UI or button-driven; same core logic as B, less ideal for headless RBP unless invoked programmatically.

**Practical lean in the transcript:** Prefer **B** (library + IronPython/RBP) for isolation, unless you explicitly need a system-wide IFC importer.

---

## 5. RBP / IronPython integration

- Open a **blank template** `.rvt` (or create one once) so BatchRvt has a document to open.
- In the task script: `clr.AddReference` to your DLL (and dependencies), then call your static entry point with the document and path to the rooms IFC.
- Write **sidecar results** (JSON/log) the same way as other RBP tasks for traceability.

---

## 6. Technical risks

- **Units and coordinates:** IFC often uses metres; Revit internal length is feet—convert consistently.
- **Boundary quality:** Missing or overlapping `IfcRelSpaceBoundary` data → incomplete Revit room loops.
- **Levels:** Spaces must align with storey elevation; mismatches vs existing Revit levels need a defined rule (create, merge, or map).
- **DLL deployment:** NuGet packages for xBIM must be copied to the runtime folder used by the add-in or RBP script.

---

## 7. Suggested next steps (implementation)

1. Proof-of-concept console or minimal add-in: open sample rooms IFC with **IfcStore**, list `IfcSpace` and `BoundedBy` boundaries.
2. In a Revit context, create one level and one room from a single space; verify units and location.
3. Generalize to all spaces, then add property mapping and boundary lines.
4. Package as DLL + document RBP script + template RVT.

---

## 8. Related Revit API concepts

- `Document.Create.NewRoom(Level, UV)` (or phase-aware variants as required).
- Room separation / boundary APIs appropriate to your Revit version.
- Shared parameters for IFC property mapping.

---

## 9. Implementation (in this repo)

| Component | Path |
|-----------|------|
| IFC DTO + loader (xBIM) | [`tools/ByggstyrningRoomImporter/ByggstyrningRoomImporter.Ifc/ByggstyrningRoomImporter.Ifc.csproj`](../../tools/ByggstyrningRoomImporter/ByggstyrningRoomImporter.Ifc/ByggstyrningRoomImporter.Ifc.csproj) |
| Revit builder + `RoomImportRunner` | [`tools/ByggstyrningRoomImporter/ByggstyrningRoomImporter/ByggstyrningRoomImporter.csproj`](../../tools/ByggstyrningRoomImporter/ByggstyrningRoomImporter/ByggstyrningRoomImporter.csproj) |
| RBP task | [`scripts/rbp/setup/xbim_rooms_import_rbp.py`](../../scripts/rbp/setup/xbim_rooms_import_rbp.py) |
| Launcher switch | `powershell\Run-ByggPipelineSetup.ps1` parameter **`-RoomsImporter`** — default **Xbim**; use **Graphisoft** for the same stack as main IFC |

**Build (Revit 2025 API paths on `C:\Program Files\Autodesk\Revit 2025\`):**

```text
dotnet build "tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\ByggstyrningRoomImporter.csproj" -c Release
```

Output: `tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\bin\Release\` (xBIM DLLs are copied next to `ByggstyrningRoomImporter.dll` for IronPython).

**Environment variables (RBP / `RoomImportRunner`):**

| Variable | Purpose |
|----------|---------|
| `BYGG_IFC_PATH` | Absolute path to rooms `.ifc` |
| `BYGG_IFC_OUTPUT_PATH` | Optional save-as `.rvt` |
| `BYGG_IFC_RESULT_PATH` | JSON result (`success`, `rooms_created`, `levels_created`, `warnings`) |
| `BYGG_IFC_LOG_PATH` | Optional log file |
| `BYGG_XBIM_ROOMS_DLL` | Absolute path to `ByggstyrningRoomImporter.dll` (set by launcher) |

**Tests:** `dotnet test tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter.Tests\ByggstyrningRoomImporter.Tests.csproj -c Release -f net8.0` — the IFC load test runs on **net8.0** (reliable xBIM + dependency resolution in `dotnet test`). The **net48** Revit add-in continues to use `ByggstyrningRoomImporter.Ifc` built for `net48`. Optional: `ByggstyrningRoomImporter.Tests.runsettings` sets NUnit `ShadowCopy` to false. Fixture `minimal_spaces.ifc` includes four `IfcRelSpaceBoundary` edges merged into one closed loop; golden snapshot: `Fixtures/minimal_spaces.boundaries.golden.json`.

**Smoke:** `powershell\Test-XbimRoomsImport.ps1` builds the DLL if missing and runs `-ImportRoomsIfcOnly -RoomsImporter Xbim`.

**Merge step:** `merge_rooms_core` collects `BuiltInCategory.OST_Rooms` — the xBIM importer creates native `Room` elements, so the same merge path as Graphisoft-imported rooms applies.

### Phase 2 — IFC space boundaries (current behaviour)

| Step | Behaviour |
|------|-----------|
| IFC | `IfcRelSpaceBoundary` with `IfcConnectionCurveGeometry` / `IfcCurveBoundedPlane` outer boundary; polylines and composite curves (Essentials-only). **Virtual** boundaries are skipped. Coordinates support IFC4 typed measures (e.g. `IfcLengthMeasure`). Open edge chains are merged into closed loops by endpoint proximity (2 mm). |
| Revit | For each space with a loop (≥3 vertices): `SketchPlane` on level, `NewRoomBoundaryLines`, interior `UV` from point-in-polygon / centroid / grid, then `NewRoom(Level, UV)`. If no usable loop or no floor plan view, **placement-only** `NewRoom` + warning. |
| Parameters | `Pset_SpaceCommon` dict + full **`SpaceProperties`** list (all `IfcPropertySet` single + enumerated values). Applied after room creation: built-ins / `ApplyPsetSpaceCommon`, then **`ApplyIfcPropertySets`** (`propertyName`, `PsetName : PropertyName`, `PsetName.PropertyName`). Bind shared parameters on rooms in the seed RVT for non-built-in IFC fields. |
| Results JSON | `BYGG_IFC_RESULT_PATH` includes `boundary_loops_applied` (count of spaces where boundary lines + enclosed `NewRoom` succeeded). |

**Limitations:** Curved boundary geometry is not approximated to arcs (only curve types handled in `IfcCurveBoundaryExtractor`). Multi-loop spaces (outer + holes) use the **first** loop with ≥3 vertices. Incomplete ArchiCAD boundaries still trigger warnings and placement fallback.

**Manual acceptance (after import):** Room is **enclosed** where boundaries were applied; compare **area** to Graphisoft export where relevant; run the usual merge step and confirm `OST_Rooms` are found.

---

## 10. E2E pipeline knowledge (main vs rooms model, merge, save)

This matches `powershell\Run-ByggPipelineSetup.ps1` and `powershell\Test-ByggPipelineFull.ps1` (operator runbook: `docs/README-pipeline.txt`).

| Phase | Default importer | Output (typical `demo/out/`) |
|-------|------------------|------------------------------|
| **1a** Main IFC | **Improved IFC Import** — `ByggstyrningIFCImporter` (`OpenIFCDocument` + Graphisoft `CorrectIFCImport`) | `main_model.rvt` |
| **1b** Rooms IFC | **xBIM** — `ByggstyrningRoomImporter` via `xbim_rooms_import_rbp.py` | `rooms_model.rvt` |
| **Setup** | `setup_model_rbp.py` | Updates **main** |
| **Merge** | `merge_rooms_rbp.py` → `merge_rooms_core.merge_rooms_from_model` | Copies `Room` + room separation lines from **rooms** doc into **main**; closes rooms doc with `Close(False)` (rooms file is **not** updated) |

**Where merged rooms live**

- **`rooms_model.rvt`** is only the **Phase 1b** sidecar (IFC → native rooms in an empty seed). It is **not** written to during merge.
- After **merge**, the rooms you care about for coordination are in **`main_model.rvt`** — but only after the **main document is saved** successfully.

**Merge sidecar: `target_saved`, `save_error`, `save_used_fallback`**

- After a successful copy, `merge_rooms_core` logs **`target_path_name`**, **`target_doc_readonly`**, **`target_doc_workshared`**, then tries **`Document.Save()`**.
- If save fails, **`save_error`** is the exception message (JSON sidecar + `RW_RESULT`). **`target_saved`** stays false until a save succeeds.
- **`BYGG_MERGE_SAVEAS_PATH`** (set by `powershell\Run-ByggPipelineSetup.ps1` to the main model path): if **`Save()`** fails, or if the document has **no** `PathName` yet, merge retries **`SaveAs`** to that path with overwrite. When **`save_used_fallback`** is true, the write used **`SaveAs`** instead of **`Save`**.
- Workshared central models may still refuse local **`Save`** without **Synchronize with Central**; use a non-workshared copy for BatchRvt or sync manually if you see **`save_error`** mentioning worksharing.

**Switching Phase 1b to Graphisoft:** pass `-RoomsImporter Graphisoft` so rooms IFC uses the same stack as 1a (larger RVT; different room/parameter behaviour).

---

## 11. IFC parameters: xBIM rooms vs Revit / Graphisoft IFC import

**Why xBIM rooms look “empty” on IFC metadata**

- **Phase 1a (main IFC)** uses Revit’s IFC open path plus Graphisoft **`CorrectIFCImport`**, with `BYGG_IFC_IMPORT_ALL_PARAMS` mapping IFC properties into Revit’s IFC-oriented **shared parameters** and built-ins (same family of behaviour as interactive Improved IFC Import).
- **ByggstyrningRoomImporter** reads IFC with xBIM and creates **native** `Room` elements. The loader collects **`Pset_SpaceCommon`** (legacy dict) plus **`SpaceProperties`** (all `IfcPropertySet` entries with single-value and enumerated properties). **`RoomPropertyMapping`** applies built-ins / `Pset_SpaceCommon`, then **`ApplyIfcPropertySets`** tries `LookupParameter(propertyName)`, qualified **`PsetName : PropertyName`**, and basic string/integer/double storage types. Parameters must still be **bound** to rooms in the seed RVT for Revit to accept values (same as any shared-parameter workflow).

**Remedies (pick one or combine)**

1. **Loader extension (done)** — All property sets on the space (single + enumerated values) are collected into **`IfcSpaceInfo.SpaceProperties`**; extend **`RoomPropertyMapping`** if you need custom IFC → Revit name rules or quantity sets.
2. **Bind parameters from a template** — Ensure the **seed RVT** used for xBIM import (e.g. `demo/in/empty_R2025.rvt`) already has the **same shared parameters** bound to rooms as your main model after IFC import (export a `.txt` shared-parameter file from a project that was imported with Revit/Graphisoft, then load + bind in the seed). Then `LookupParameter` in **`RoomPropertyMapping`** can set values when names align.
3. **Post-merge sync from main** — After merge, run a **small RBP script** that matches rooms by **number** or **GUID** (if stored) and copies parameter values from elements in the main model that came from the **architectural** IFC import into the merged room instances (only where names/types match).
4. **Reference implementation** — Autodesk’s open-source [revit-ifc](https://github.com/Autodesk/revit-ifc) shows how Revit maps IFC properties to parameters; use it as a naming reference, not as a hard dependency.

**Practical expectation:** Parity with **full** Revit IFC parameter coverage requires either **broadening** ByggstyrningRoomImporter’s extraction and mapping, or a **deliberate** shared-parameter strategy (2) plus optional post-merge (3).

---

*Earlier sections were research notes; sections 9–11 reflect the implemented pipeline and E2E behaviour.*
