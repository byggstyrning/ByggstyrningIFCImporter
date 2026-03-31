# Journal Templates for ArchiCAD IFC Import

These templates automate IFC-to-RVT conversion using Revit journal replay.
Revit is launched with a journal file (`Revit.exe "path\to\journal.txt"`)
which replays the recorded UI interactions headlessly.

## Templates

| File | Operation | ArchiCAD command | Parameterizable? |
|------|-----------|-----------------|------------------|
| `ifc_link.template.txt` | Link IFC | `Graphisoft.IFCLinker` | **Yes** -- IFC path via standard Revit `FileDialog` |
| `ifc_import.template.txt` | Improved IFC Import | `Graphisoft.IFCImporter` | **Partial** -- plugin uses a custom dialog (see below) |

### Placeholders

| Placeholder | Used in | Description |
|-------------|---------|-------------|
| `{{IFC_FILE_PATH}}` | link template | Absolute path to the `.ifc` file |
| `{{IFC_FILENAME}}` | link template | Basename only (e.g. `A1_2b_BIM_XXX_0001_00.ifc`) |
| `{{OUTPUT_RVT_PATH}}` | both | Absolute path for the output `.rvt` file |
| `{{REVIT_VERSION}}` | both | Revit version string (e.g. `2025.000`) |
| `{{ARCHICAD_IMPORT_COMMANDS}}` | import template | Captured plugin commands block |

## How it works

### Link IFC (main model -- fully automated)

The ArchiCAD **Link IFC** command (`Graphisoft.IFCLinker`) internally posts
Revit's built-in `ID_IFC_LINK` command, which opens a **standard Revit file
dialog**. This means the journal player can provide the IFC path through
`Jrn.Data "FileDialog"` -- no custom UI automation is needed.

Pipeline:
1. Create new empty Metric project
2. Invoke the ArchiCAD Link IFC command
3. Standard file dialog → IFC path injected from placeholder
4. Wait for link processing
5. Save As → output RVT path from placeholder
6. Exit Revit

### Improved IFC Import (rooms -- requires one-time recording)

The ArchiCAD **Improved IFC Import** command (`Graphisoft.IFCImporter`)
shows its **own custom dialog** for file selection and import settings.
This dialog is **not recorded** by Revit's journal system -- the journal
only captures the `RibbonEvent` that launches the command.

This means:
- The IFC file path **cannot** be injected at runtime via placeholders
- The import commands must be **re-recorded** each time the IFC file changes
- The captured commands file (`archicad_import_commands.txt`) must contain
  the full sequence including the plugin's internal dialog interactions

## One-time capture procedure

This must be done once for each IFC file, and repeated if the ArchiCAD
plugin or Revit is upgraded.

### Step 1: Clear old journals

```powershell
Remove-Item "$env:LOCALAPPDATA\Autodesk\Revit\Autodesk Revit 2025\Journals\journal.*.txt"
```

### Step 2: Record the import manually

1. Open Revit 2025
2. Create a **new empty project** (File → New → Project, template = `<None>`, Metric)
3. Switch to the **Add-Ins** ribbon tab
4. Click **Improved IFC Import** in the "IFC Exchange with Archicad" panel
5. In the ArchiCAD plugin dialog, select the target `.ifc` file
6. Accept default settings and click OK
7. Wait for import to complete
8. Dismiss any "Document Opened" warning dialog
9. **Save** the resulting model (File → Save As → pick your output path)
10. Close Revit

### Step 3: Extract the captured commands

Run the provided capture helper:

```powershell
.\powershell\Capture-ArchiCADJournal.ps1 -RevitYear 2025
```

This extracts the plugin-specific lines from the latest journal and writes
them to `archive\journal-automation\journal_templates\archicad_import_commands.txt` (under the repo root).

### Step 4: Verify

Review `archicad_import_commands.txt` to ensure it contains:
- The `Jrn.RibbonEvent` for the Improved IFC Import command
- Any `Jrn.Data "APIStringStringMapJournalData"` entries
- The `Jrn.PushButton` for the DocWarnDialog dismissal

## Workarounds for the import dialog limitation

If re-recording per IFC file is impractical, consider these alternatives:

1. **Use Link IFC for both models** -- Link IFC uses a standard dialog and
   is fully parameterizable. The linked IFC can then be "bound" to convert
   it to native Revit elements if needed.

2. **Custom C# IFC importer** -- Build a Revit API add-in that parses the
   IFC (e.g. using xBIM) and creates native Revit elements directly. This
   bypasses the ArchiCAD plugin entirely for the rooms model.

3. **UI Automation** -- Use `System.Windows.Automation` or `SendKeys` from
   a parallel PowerShell process to interact with the ArchiCAD plugin's
   custom dialog while Revit replays the journal.

## Version compatibility

- Revit: 2025 (version string `2025.000`)
- ArchiCAD IFC Exchange plugin: v28.0.0.3014
- Plugin assembly: `C:\Program Files\Graphisoft\IFC Model Exchange with Archicad for Revit 2025\2025\ArchicadConnection.dll`
- Plugin must be installed and enabled (check via DiRoots AppManager)

Re-capture is required after any plugin or Revit update.
