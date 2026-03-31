This folder holds the latest outputs from powershell\Test-ByggPipelineFull.ps1 (default):

  main_model.rvt   — Phase 1a: Improved IFC Import (ByggstyrningIFCImporter: OpenIFCDocument + CorrectIFCImport)
  rooms_model.rvt  — Phase 1b: rooms IFC via xBIM ByggstyrningRoomImporter (default E2E)

Phase 2 step "setup" (setup_model_rbp.py + bygg_setup_core) runs on main_model.rvt: purge IFC openings,
worksets, rotate to project north, link config, etc. Proof and counts are in:
  main_model.rbp_setup_result.json (openings_deleted, elements_rotated, worksharing_enabled, model_saved, …)
The launcher also prints a one-line "Setup RBP summary" to the console/diag log.

If doc.Save() fails on the main path (read-only / lock), setup uses SaveAs to a temp file and the launcher
copies it over main_model.rvt (same idea as merge_rooms). Check setup_os_copy_done and setup_temp_saved_path
in the sidecar / RW_RESULT when model_saved is true after a failed in-place save.

Worksharing from setup is a LOCAL workshared file (EnableWorksharing), not a Revit Server / ACC Central
model. You will not see a "central" until you Save As Central to a network path yourself.

If you expect IFC-style room parameters on xBIM-created rooms, place the IFC next to the optional file
  A1_2b_BIM_XXX_0003_00.ifc.sharedparameters.txt (same base name + .sharedparameters.txt)
or set NOBEL_SHARED_PARAMETERS_PATH. ByggstyrningRoomImporter binds those definitions to Rooms before creating rooms.

After merge (pipeline step merge_rooms), native rooms copied from the rooms file are intended to live in
main_model.rvt. rooms_model.rvt is not updated by merge (source doc is closed without saving).

If merged rooms seem missing when you open main_model.rvt from disk, check demo/out/main_model.rbp_rooms_result.json:
  target_saved should be true. If false, read save_error (Save/SaveAs failure). powershell\Run-ByggPipelineSetup.ps1 sets BYGG_MERGE_SAVEAS_PATH so merge can retry SaveAs to the main path. See INVESTIGATION.md section 10.

Each run overwrites these files. Large *.rvt files are gitignored.

To regenerate: from the repository root, run:
  .\powershell\Test-ByggPipelineFull.ps1

To use a temp folder instead: .\powershell\Test-ByggPipelineFull.ps1 -UseTempOutput

Phase 1b Graphisoft instead of xBIM: -RoomsImporter Graphisoft on powershell\Run-ByggPipelineSetup.ps1 or powershell\Test-ByggPipelineFull.ps1

--- Optional Phase 3: ACC cloud publish ---

After Phase 2, powershell\Run-ByggPipelineSetup.ps1 can run an extra BatchRvt step
(publish_acc_rbp.py) that calls Document.SaveAsCloudModel to publish the workshared local main
model to Autodesk Docs / ACC.

Prerequisites:
  * The Windows user running Revit must be signed in to Autodesk with access to the target hub/project.
  * Obtain hub (account) GUID, project GUID, and Data Management folder id outside this repo (ACC UI,
    Postman, APS, team wiki). If an id string starts with b., the launcher strips it before parsing GUIDs.
  * The document must not already be a cloud model; Revit must be able to complete SaveAsCloudModel.

PowerShell (example):
  .\powershell\Run-ByggPipelineSetup.ps1 `
    -MainIfcPath "demo\in\A1_2b_BIM_XXX_0001_00.ifc" `
    -RoomsIfcPath "demo\in\A1_2b_BIM_XXX_0003_00.ifc" `
    -RevitYear 2025 `
    -PublishAcc `
    -AccAccountId "<hub-guid>" `
    -AccProjectId "<project-guid>" `
    -AccFolderId "<folder-urn-or-id>"

Default cloud file name is {IFC base name}.ifc_yyyy-MM-dd.rvt derived from -MainIfcPath. Override with
-CloudModelName "MyName.ifc_2026-03-28.rvt". If you use -SkipImport without -MainIfcPath, you must pass
-CloudModelName.

Publish-only on an already-prepared main_model.rvt (skip setup, rooms): use
-SkipImport -MainModelPath -SkipRooms -SkipSetup -PublishAcc (plus ACC ids and
-MainIfcPath or -CloudModelName). Phase 2 step "setup" is recorded as skipped in RW_RESULT.

Results: main_model.rbp_publish_acc_result.json next to the RVT; RW_RESULT includes steps.publish_acc.
Common API failures include duplicate name in folder (RevitServerModelAlreadyExistsException), naming
convention (RevitServerModelNameBreaksConventionException), and auth (RevitServerUnauthenticatedUserException /
RevitServerUnauthorizedException).
