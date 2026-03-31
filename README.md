# ByggstyrningIFCImporter

Revit add-ins used in **Byggstyrning** workflows to bring Archicad-oriented IFC into Revit:

| Component | Role |
|-----------|------|
| **ByggstyrningIFCImporter** | Headless Graphisoft path: `OpenIFCDocument` + `CorrectIFCImport` (no Graphisoft UI). |
| **ByggstyrningRoomImporter** | xBIM-based rooms IFC import; loaded at runtime by BatchRvt / IronPython via `BYGG_XBIM_ROOMS_DLL`. |

## Prerequisites

- **Windows**, **Revit** (projects reference Revit API under `C:\Program Files\Autodesk\Revit 2025\` — edit `.csproj` HintPaths if you use another year).
- **.NET SDK** that can build **net48**.
- **ByggstyrningIFCImporter:** Graphisoft **IFC Model Exchange with Archicad for Revit** (same year as Revit). Paths in `ByggstyrningIFCImporter.csproj` must match your install.
- **ByggstyrningRoomImporter:** NuGet restores **Xbim.Essentials** (no Graphisoft required for this component).

## Build

From the repository root:

```powershell
dotnet build "tools\ByggstyrningIFCImporter\ByggstyrningIFCImporter.csproj" -c Release
dotnet build "tools\ByggstyrningRoomImporter\ByggstyrningRoomImporter\ByggstyrningRoomImporter.csproj" -c Release
```

## Install (from source build)

**IFC importer:** copy `ByggstyrningIFCImporter.dll` and `ByggstyrningIFCImporter.addin` to:

`%APPDATA%\Autodesk\Revit\Addins\<year>\`

Prefer **AppData** over Program Files for unsigned builds (see comments in `Deploy-ToProgramFiles.ps1`).

**Room importer:** deploy the **entire** `bin\Release` output folder; set `BYGG_XBIM_ROOMS_DLL` to the full path of `ByggstyrningRoomImporter.dll`.

## GitHub Releases

Maintainers can produce zip artifacts for a given Revit year on a machine with Revit + Graphisoft installed:

```powershell
.\scripts\Package-Release.ps1 -RevitYear 2025
```

Outputs go to `dist/`:

- `ByggstyrningIFCImporter-RVT2025.zip` — DLL, `.addin`, short `INSTALL.txt`
- `ByggstyrningRoomImporter-RVT2025.zip` — full room-importer Release output + `INSTALL.txt`

Publish a release and attach those zips, or use the GitHub CLI:

```powershell
gh release create v1.0.0 dist\*.zip --title "v1.0.0" --notes "Built for Revit 2025."
```

**Note:** GitHub-hosted runners do not include Revit; CI here only runs the **xBIM unit tests** (`ByggstyrningRoomImporter.Tests`). Full add-in builds are local or self-hosted.

## Related

Full pipeline orchestration (BatchRvt, merge rooms, ACC) lives in the internal **NobelDCATools** / Byggstyrning extension repository.

## License

See [LICENSE](LICENSE).
