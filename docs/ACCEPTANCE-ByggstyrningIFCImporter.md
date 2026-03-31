# Manual acceptance: ByggstyrningIFCImporter vs interactive Improved IFC Import

Use this checklist to confirm that a **headless** run matches a **known-good interactive** Graphisoft import for the same IFC and effective settings.

## Prerequisites

- Graphisoft **IFC Model Exchange with Archicad** installed for your Revit year; EULA accepted at least once via the add-in (if correction misbehaves).
- `ByggstyrningIFCImporter` built (`Release`) and deployed if using RBP.
- Same machine or same registry profile when comparing registry-driven options.

## Steps

1. **Interactive baseline**  
   - In Revit, use **Improved IFC Import** from the Graphisoft add-in with your desired options (auto join, off-axis, import IFC parameters, door/window 2D, true north).  
   - Note registry values under `HKCU\Software\GRAPHISOFT\IFC Model Exchange with Archicad for Revit {year}` if you rely on them, or set the same behaviour using `BYGG_IFC_*` overrides (`BYGG_IFC_REMOVE_DOOR_WINDOW_2D`, `BYGG_IFC_TRUE_NORTH_FROM_GEOM`, etc.).

2. **Headless run**  
   - Run `ImportRunner` with `BYGG_IFC_PATH` / `BYGG_IFC_OUTPUT_PATH` and matching `BYGG_IFC_*` / `BYGG_GRAPHISOFT_*` flags so **effective** `IFCImportOptions` and **effective** `CorrectIFCImport` arguments match step 1.  
   - Or call `Invoke-RBPGraphisoftImport` from `powershell\Run-ByggPipelineSetup.ps1` with optional `-GraphisoftDir`, `-GraphisoftRevitYear`, `-GraphisoftVerbose` as needed.

3. **Compare**  
   - Open both resulting `.rvt` files (or compare element counts / spot-check floors, rooms, grids, project north).  
   - Read `BYGG_IFC_RESULT_PATH` JSON: `graphisoft_applied` should be `true`; `corrected_floors` / `corrected_rooms` should be non-null after a successful `CorrectIFCImport`.

4. **Failure modes**  
   - If `preflight_error` is set in the JSON, fix Graphisoft install path, EDM folder permissions, or `BYGG_GRAPHISOFT_DIR` before comparing geometry.  
   - If `graphisoft_applied` is `false` but preflight passed, inspect `BYGG_IFC_LOG_PATH` and enable `BYGG_IFC_VERBOSE=1` for Graphisoft step logging.

## Reference

Full environment list: [graphisoft-revit-plugin-api-notes.md](graphisoft-revit-plugin-api-notes.md) §1.2.
