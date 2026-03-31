# ByggstyrningIFCImporter

Headless **Improved IFC Import** pipeline: `OpenIFCDocument` + Graphisoft `RevitConnectionManaged.CorrectIFCImport` (no Graphisoft UI). Same stack as ribbon **Import IFC** / RBP `graphisoft_import_rbp.py`.

## Build

```powershell
dotnet build "ByggstyrningIFCImporter.csproj" -c Release
```

Expects Revit API and Graphisoft assemblies at `HintPath` locations in `ByggstyrningIFCImporter.csproj` (adjust for your Revit year).

## Environment

See **[`docs/graphisoft-revit-plugin-api-notes.md`](../../docs/graphisoft-revit-plugin-api-notes.md)** §1 (pipeline, env vars, registry, preflight).

## Deploy

`Deploy-ToProgramFiles.ps1` / `powershell\Run-ByggPipelineSetup.ps1` (`Deploy-ByggstyrningIFCImporter`) copy `ByggstyrningIFCImporter.dll` and `.addin` to `%APPDATA%\Autodesk\Revit\Addins\{year}\`.

## Acceptance testing

[`docs/ACCEPTANCE-ByggstyrningIFCImporter.md`](../../docs/ACCEPTANCE-ByggstyrningIFCImporter.md)
