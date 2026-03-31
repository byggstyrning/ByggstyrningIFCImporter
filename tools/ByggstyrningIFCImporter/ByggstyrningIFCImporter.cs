using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.DB.IFC;
using Autodesk.Revit.UI;
using Microsoft.Win32;
using RevitConnection;

namespace Byggstyrning.IFCImporter
{
    /// <summary>
    /// Registers a ribbon button with a stable ID so journal replay can invoke it
    /// via: Jrn.RibbonEvent "Execute external command:CustomCtrl_%CustomCtrl_%Add-Ins%Byggstyrning-IFC-Importer%ByggstyrningImportIFC:Byggstyrning.IFCImporter.ImportCommand"
    /// </summary>
    public class ImporterApp : IExternalApplication
    {
        public const string PanelName  = "Byggstyrning-IFC-Importer";
        public const string ButtonName = "Import IFC";

        public Result OnStartup(UIControlledApplication app)
        {
            try
            {
                var panel = app.CreateRibbonPanel(PanelName);
                var data  = new PushButtonData(
                    "ByggstyrningImportIFC", ButtonName,
                    typeof(ImportCommand).Assembly.Location,
                    typeof(ImportCommand).FullName);
                data.ToolTip = "Automated IFC import with Graphisoft geometry correction. Reads config from BYGG_IFC_* env vars.";
                panel.AddItem(data);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[ByggstyrningIFC] OnStartup error: {ex.Message}");
            }
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication app) => Result.Succeeded;
    }

    /// <summary>
    /// Outcome details written to BYGG_IFC_RESULT_PATH JSON (extended fields).
    /// </summary>
    internal sealed class ImportOutcome
    {
        public bool GraphisoftApplied;
        public uint? CorrectedFloors;
        public uint? CorrectedRooms;
        public bool? ProjectInfoImported;
        public bool? PhaseMapping;
        public string GraphisoftDir;
        public string EdmDatabasePath;
        public string RevitVersion;
        public string AddinName;
        public string AddinVersion;
        public string PreflightError;
    }

    /// <summary>
    /// Core import logic callable from IExternalCommand and from IronPython (BatchRvt) via clr.
    /// </summary>
    public static class ImportRunner
    {
        private const string DefaultRevitYear = "2025";

        [ThreadStatic]
        private static HashSet<ElementId> _roomsNotEnclosed;

        /// <summary>
        /// Runs the full Graphisoft-style import pipeline. Reads BYGG_IFC_* environment variables.
        /// </summary>
        public static Result Run(UIApplication uiApp)
        {
            string msg = null;
            return Run(uiApp, ref msg);
        }

        /// <summary>
        /// Runs the full Graphisoft-style import pipeline. Reads BYGG_IFC_* environment variables.
        /// </summary>
        public static Result Run(UIApplication uiApp, ref string message)
        {
            string ifcPath    = Environment.GetEnvironmentVariable("BYGG_IFC_PATH");
            string outputPath = Environment.GetEnvironmentVariable("BYGG_IFC_OUTPUT_PATH");
            string resultPath = Environment.GetEnvironmentVariable("BYGG_IFC_RESULT_PATH");

            if (string.IsNullOrEmpty(ifcPath) || string.IsNullOrEmpty(outputPath))
            {
                message = "BYGG_IFC_PATH and BYGG_IFC_OUTPUT_PATH environment variables are required.";
                WriteResult(resultPath, false, message, false, null);
                return Result.Failed;
            }

            if (!File.Exists(ifcPath))
            {
                message = $"IFC file not found: {ifcPath}";
                WriteResult(resultPath, false, message, false, null);
                return Result.Failed;
            }

            bool autoJoin  = GetEnvBool("BYGG_IFC_AUTO_JOIN", false);
            bool offAxis   = GetEnvBool("BYGG_IFC_CORRECT_OFF_AXIS", false);
            bool allParams = GetEnvBool("BYGG_IFC_IMPORT_ALL_PARAMS", true);

            var app = uiApp.Application;
            var outcome = new ImportOutcome
            {
                RevitVersion = app.VersionNumber ?? "",
                AddinName    = typeof(ImportRunner).Assembly.GetName().Name,
                AddinVersion = typeof(ImportRunner).Assembly.GetName().Version?.ToString() ?? ""
            };

            Log($"ByggstyrningIFCImporter starting");
            Log($"  IFC:    {ifcPath}");
            Log($"  Output: {outputPath}");
            Log($"  AutoJoin={autoJoin}, OffAxis={offAxis}, AllParams={allParams}");

            if (!ResolveGraphisoftPaths(out string graphisoftDir, out string registrySubKey, out string preflightErr))
            {
                outcome.PreflightError = preflightErr;
                message = preflightErr;
                Log($"PREFLIGHT FAILED: {preflightErr}");
                WriteResult(resultPath, false, preflightErr, false, outcome);
                return Result.Failed;
            }

            outcome.GraphisoftDir = graphisoftDir;

            string edmFolder = GetEdmDatabaseFolder(registrySubKey, out string edmErr);
            if (edmFolder == null)
            {
                outcome.PreflightError = edmErr ?? "EDM database folder could not be created or accessed.";
                message = outcome.PreflightError;
                Log($"PREFLIGHT FAILED: {outcome.PreflightError}");
                WriteResult(resultPath, false, outcome.PreflightError, false, outcome);
                return Result.Failed;
            }

            outcome.EdmDatabasePath = edmFolder;
            Log($"Preflight OK: Graphisoft dir={graphisoftDir}");
            Log($"  EDM: {edmFolder}");

            try
            {
                var importOpts = new IFCImportOptions
                {
                    Action                 = IFCImportAction.Open,
                    AutoJoin               = autoJoin,
                    AutocorrectOffAxisLines = offAxis,
                    CreateLinkInstanceOnly = false,
                    ForceImport            = true,
                    Intent                 = IFCImportIntent.Reference,
                    RevitLinkFileName      = ""
                };

                _roomsNotEnclosed = new HashSet<ElementId>();
                app.FailuresProcessing += OnFailuresProcessing;

                Log("Opening IFC document via Revit API ...");
                Document doc = app.OpenIFCDocument(ifcPath, importOpts);

                if (doc == null)
                {
                    message = "OpenIFCDocument returned null.";
                    WriteResult(resultPath, false, message, false, outcome);
                    return Result.Failed;
                }
                Log($"IFC opened: {doc.Title} ({new FilteredElementCollector(doc).WhereElementIsNotElementType().GetElementCount()} elements)");

                bool gsSuccess = RunGraphisoftCorrection(
                    app, doc, ifcPath, allParams, graphisoftDir, registrySubKey, edmFolder, outcome);

                if (gsSuccess)
                    Log("Graphisoft CorrectIFCImport completed successfully");
                else
                    Log("WARNING: Graphisoft correction skipped or failed -- model saved with native import only");

                CorrectViews(doc);
                Log("View correction completed");

                var dir = Path.GetDirectoryName(outputPath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                    Directory.CreateDirectory(dir);

                var saveOpts = new SaveAsOptions { OverwriteExistingFile = true };
                doc.SaveAs(outputPath, saveOpts);
                Log($"Saved: {outputPath} ({new FileInfo(outputPath).Length / 1048576.0:F1} MB)");

                doc.Close(false);
                doc.Dispose();

                app.FailuresProcessing -= OnFailuresProcessing;
                _roomsNotEnclosed = null;

                outcome.GraphisoftApplied = gsSuccess;
                WriteResult(resultPath, true, null, gsSuccess, outcome);
                Log("ByggstyrningIFCImporter completed successfully");
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.ToString();
                Log($"FATAL: {ex}");
                WriteResult(resultPath, false, ex.Message, false, outcome);
                try { app.FailuresProcessing -= OnFailuresProcessing; } catch { }
                _roomsNotEnclosed = null;
                return Result.Failed;
            }
        }

        /// <summary>
        /// BYGG_GRAPHISOFT_DIR → folder containing RevitConnectionManaged.dll;
        /// else BYGG_REVIT_YEAR (default 2025) → Program Files\Graphisoft\...\{year}\{year}.
        /// </summary>
        private static bool ResolveGraphisoftPaths(out string graphisoftDir, out string registrySubKey, out string error)
        {
            graphisoftDir = null;
            registrySubKey = ResolveGraphisoftRegistrySubKey();
            error = null;

            var envDir = Environment.GetEnvironmentVariable("BYGG_GRAPHISOFT_DIR")?.Trim();
            if (!string.IsNullOrEmpty(envDir))
            {
                if (!Directory.Exists(envDir))
                {
                    error = $"BYGG_GRAPHISOFT_DIR does not exist: {envDir}";
                    return false;
                }
                string rcm = Path.Combine(envDir, "RevitConnectionManaged.dll");
                if (!File.Exists(rcm))
                {
                    error = $"RevitConnectionManaged.dll not found under BYGG_GRAPHISOFT_DIR: {envDir}";
                    return false;
                }
                graphisoftDir = Path.GetFullPath(envDir);
                return true;
            }

            string year = Environment.GetEnvironmentVariable("BYGG_REVIT_YEAR")?.Trim();
            if (string.IsNullOrEmpty(year))
                year = DefaultRevitYear;

            string conventional = $@"C:\Program Files\Graphisoft\IFC Model Exchange with Archicad for Revit {year}\{year}";
            string rcmPath = Path.Combine(conventional, "RevitConnectionManaged.dll");
            if (!File.Exists(rcmPath))
            {
                error =
                    $"Graphisoft add-in not found at expected path for year {year}: {rcmPath}. " +
                    "Install IFC Model Exchange with Archicad for Revit or set BYGG_GRAPHISOFT_DIR to the folder containing RevitConnectionManaged.dll.";
                return false;
            }
            graphisoftDir = Path.GetFullPath(conventional);
            return true;
        }

        /// <summary>
        /// HKCU subkey for Graphisoft settings. Override with BYGG_GRAPHISOFT_REGISTRY_KEY (full path under HKCU, no HKEY_CURRENT_USER prefix).
        /// </summary>
        private static string ResolveGraphisoftRegistrySubKey()
        {
            var full = Environment.GetEnvironmentVariable("BYGG_GRAPHISOFT_REGISTRY_KEY")?.Trim();
            if (!string.IsNullOrEmpty(full))
                return full;
            string year = Environment.GetEnvironmentVariable("BYGG_REVIT_YEAR")?.Trim();
            if (string.IsNullOrEmpty(year))
                year = DefaultRevitYear;
            return $@"Software\GRAPHISOFT\IFC Model Exchange with Archicad for Revit {year}";
        }

        private static bool RunGraphisoftCorrection(
            Autodesk.Revit.ApplicationServices.Application app,
            Document doc,
            string ifcPath,
            bool importAllParams,
            string graphisoftDir,
            string registrySubKey,
            string edmFolder,
            ImportOutcome outcome)
        {
            string rcmPath = Path.Combine(graphisoftDir, "RevitConnectionManaged.dll");
            if (!File.Exists(rcmPath))
            {
                Log($"RevitConnectionManaged.dll not found at {rcmPath}");
                return false;
            }

            Log($"Loading Graphisoft engine from {graphisoftDir}");
            Log($"EDM database: {edmFolder}");

            bool removeDoorWindow2D = ResolveRemoveDoorWindow2D(registrySubKey);
            bool trueNorth = ResolveTrueNorthFromGeom(registrySubKey);

            bool verbose = GetEnvBool("BYGG_IFC_VERBOSE", false);
            ImportProgressStepChangeDelegate onImportStep = null;
            ExportProgressStepChangeDelegate onExportStep = null;
            if (verbose)
            {
                onImportStep = step => Log($"  Graphisoft import step: {step}");
                onExportStep = step => Log($"  Graphisoft export step: {step}");
            }

            using (var rcm = new RevitConnectionManaged(
                graphisoftDir, edmFolder,
                onImportStep ?? (_ => { }),
                onExportStep ?? (_ => { }),
                () => { },
                _ => ""
            ))
            {
                uint numFloors, numRooms;
                bool projectInfoImported, phaseMapping;
                Phase preferredPhase = null;

                rcm.CorrectIFCImport(
                    ifcPath, doc,
                    "Improve IFC Import",
                    out numFloors, out numRooms,
                    out projectInfoImported, out phaseMapping,
                    ref preferredPhase,
                    removeDoorWindow2D, importAllParams,
                    _roomsNotEnclosed, trueNorth
                );

                outcome.CorrectedFloors = numFloors;
                outcome.CorrectedRooms = numRooms;
                outcome.ProjectInfoImported = projectInfoImported;
                outcome.PhaseMapping = phaseMapping;

                Log($"  Floors corrected: {numFloors}");
                Log($"  Rooms corrected:  {numRooms}");
                Log($"  Project info:     {projectInfoImported}");
                Log($"  Phase mapping:    {phaseMapping}");
            }

            return true;
        }

        /// <summary>
        /// removeAllDoorWindow2D: BYGG_IFC_REMOVE_DOOR_WINDOW_2D overrides registry if set (true = remove 2D door/window).
        /// </summary>
        private static bool ResolveRemoveDoorWindow2D(string registrySubKey)
        {
            var o = Environment.GetEnvironmentVariable("BYGG_IFC_REMOVE_DOOR_WINDOW_2D");
            if (!string.IsNullOrEmpty(o))
                return GetEnvBool("BYGG_IFC_REMOVE_DOOR_WINDOW_2D", false);
            return !GetDoorWindow2DEnabled(registrySubKey);
        }

        /// <summary>
        /// trueNorthFromGeomRepContext: BYGG_IFC_TRUE_NORTH_FROM_GEOM overrides registry if set.
        /// </summary>
        private static bool ResolveTrueNorthFromGeom(string registrySubKey)
        {
            var o = Environment.GetEnvironmentVariable("BYGG_IFC_TRUE_NORTH_FROM_GEOM");
            if (!string.IsNullOrEmpty(o))
                return GetEnvBool("BYGG_IFC_TRUE_NORTH_FROM_GEOM", false);
            return GetRegistryInt(registrySubKey, "ImportAngleToTrueNorthAs", 1) == 2;
        }

        private static void OnFailuresProcessing(object sender, FailuresProcessingEventArgs e)
        {
            var accessor = e.GetFailuresAccessor();
            foreach (var fm in accessor.GetFailureMessages())
            {
                var defId = fm.GetFailureDefinitionId();
                if (defId == BuiltInFailures.RoomFailures.RoomNotEnclosed ||
                    defId == BuiltInFailures.RoomFailures.RoomsInSameRegionRooms)
                {
                    try
                    {
                        _roomsNotEnclosed?.UnionWith(fm.GetFailingElementIds());
                        accessor.DeleteWarning(fm);
                    }
                    catch { }
                }
            }
        }

        private static void CorrectViews(Document doc)
        {
            using (var tx = new Transaction(doc, "Correct Views"))
            {
                tx.Start();

                PhaseFilter showComplete = FindOrCreateShowCompleteFilter(doc);
                ElementId phaseId = GetFirstElementPhaseCreated(doc);

                bool has3D = false;
                foreach (View v in new FilteredElementCollector(doc).OfClass(typeof(View)))
                {
                    try
                    {
                        if (v.Name == "{3D}") has3D = true;
                        SetViewParams(v, showComplete, phaseId);
                    }
                    catch { }
                }

                if (!has3D)
                {
                    try
                    {
                        ElementId vftId = null;
                        foreach (ViewFamilyType vft in new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType)))
                        {
                            if (vft.ViewFamily == ViewFamily.ThreeDimensional) { vftId = vft.Id; break; }
                        }
                        if (vftId != null)
                        {
                            var v3d = View3D.CreateIsometric(doc, vftId);
                            v3d.Name = "{3D}";
                            SetViewParams(v3d, showComplete, phaseId);
                        }
                    }
                    catch { }
                }

                tx.Commit();
            }
        }

        private static PhaseFilter FindOrCreateShowCompleteFilter(Document doc)
        {
            foreach (PhaseFilter pf in new FilteredElementCollector(doc).OfClass(typeof(PhaseFilter)))
            {
                try
                {
                    if (pf.GetPhaseStatusPresentation(ElementOnPhaseStatus.New) == PhaseStatusPresentation.ShowByCategory &&
                        pf.GetPhaseStatusPresentation(ElementOnPhaseStatus.Existing) == PhaseStatusPresentation.ShowByCategory &&
                        pf.GetPhaseStatusPresentation(ElementOnPhaseStatus.Demolished) == PhaseStatusPresentation.DontShow &&
                        pf.GetPhaseStatusPresentation(ElementOnPhaseStatus.Future) == PhaseStatusPresentation.DontShow)
                    {
                        return pf;
                    }
                }
                catch (Exception)
                {
                    continue;
                }
            }
            try
            {
                var newPf = PhaseFilter.Create(doc, "Show Complete");
                newPf.SetPhaseStatusPresentation(ElementOnPhaseStatus.New, PhaseStatusPresentation.ShowByCategory);
                newPf.SetPhaseStatusPresentation(ElementOnPhaseStatus.Existing, PhaseStatusPresentation.ShowByCategory);
                newPf.SetPhaseStatusPresentation(ElementOnPhaseStatus.Demolished, PhaseStatusPresentation.DontShow);
                newPf.SetPhaseStatusPresentation(ElementOnPhaseStatus.Future, PhaseStatusPresentation.DontShow);
                return newPf;
            }
            catch (Exception)
            {
                return null;
            }
        }

        private static ElementId GetFirstElementPhaseCreated(Document doc)
        {
            foreach (Element e in new FilteredElementCollector(doc)
                         .WherePasses(new LogicalOrFilter(
                             new ElementClassFilter(typeof(Wall)),
                             new ElementClassFilter(typeof(Wall), true))))
            {
                var p = e.get_Parameter(BuiltInParameter.PHASE_CREATED);
                if (p != null)
                {
                    var id = p.AsElementId();
                    if (id != null && id != ElementId.InvalidElementId)
                        return id;
                }
            }
            return null;
        }

        private static void SetViewParams(View v, PhaseFilter pf, ElementId phaseId)
        {
            v.Discipline  = ViewDiscipline.Coordination;
            v.DetailLevel = ViewDetailLevel.Fine;
            v.DisplayStyle = DisplayStyle.ShadingWithEdges;
            if (phaseId != null)
            {
                var p = v.get_Parameter(BuiltInParameter.VIEW_PHASE);
                if (p != null && !p.IsReadOnly) p.Set(phaseId);
            }
            if (pf != null)
            {
                var p = v.get_Parameter(BuiltInParameter.VIEW_PHASE_FILTER);
                if (p != null && !p.IsReadOnly) p.Set(pf.Id);
            }
        }

        private static string GetEdmDatabaseFolder(string registrySubKey, out string error)
        {
            error = null;
            string folder = null;
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(registrySubKey))
                {
                    if (key?.GetValue("EDMDatabasePath") is string v)
                        folder = v;
                }
            }
            catch (Exception ex)
            {
                error = $"Registry read failed for EDM path ({registrySubKey}): {ex.Message}";
                return null;
            }

            if (string.IsNullOrEmpty(folder))
                folder = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    @"Graphisoft\EDMDB");

            try
            {
                if (!Directory.Exists(folder))
                    Directory.CreateDirectory(folder);
            }
            catch (Exception ex)
            {
                error = $"Could not create EDM database folder '{folder}': {ex.Message}";
                return null;
            }

            try
            {
                string probe = Path.Combine(folder, ".bygg_edm_write_probe");
                File.WriteAllText(probe, "ok");
                File.Delete(probe);
            }
            catch (Exception ex)
            {
                error = $"EDM database folder is not writable '{folder}': {ex.Message}";
                return null;
            }

            return folder;
        }

        private static bool GetDoorWindow2DEnabled(string registrySubKey)
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(registrySubKey))
                {
                    if (key?.GetValue("EnableDoorWindow2DHandling") != null)
                        return Convert.ToBoolean(key.GetValue("EnableDoorWindow2DHandling"));
                }
            }
            catch { }
            return true;
        }

        private static int GetRegistryInt(string registrySubKey, string name, int def)
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(registrySubKey))
                {
                    if (key?.GetValue(name) != null)
                        return Convert.ToInt32(key.GetValue(name));
                }
            }
            catch { }
            return def;
        }

        private static bool GetEnvBool(string name, bool def)
        {
            var v = Environment.GetEnvironmentVariable(name);
            if (string.IsNullOrEmpty(v)) return def;
            return v == "1" || v.Equals("true", StringComparison.OrdinalIgnoreCase);
        }

        private static void Log(string msg)
        {
            var logPath = Environment.GetEnvironmentVariable("BYGG_IFC_LOG_PATH");
            var line = $"[{DateTime.Now:HH:mm:ss.fff}] {msg}";
            System.Diagnostics.Debug.WriteLine($"[ByggstyrningIFC] {line}");
            if (!string.IsNullOrEmpty(logPath))
            {
                try { File.AppendAllText(logPath, line + Environment.NewLine); }
                catch { }
            }
        }

        private static void WriteResult(string path, bool success, string error, bool gsApplied, ImportOutcome details)
        {
            if (string.IsNullOrEmpty(path)) return;
            try
            {
                var sb = new StringBuilder(512);
                sb.Append("{\"success\":").Append(success ? "true" : "false");
                sb.Append(",\"graphisoft_applied\":").Append(gsApplied ? "true" : "false");
                sb.Append(",\"error\":").Append(error == null ? "null" : "\"" + Escape(error) + "\"");
                if (details != null)
                {
                    sb.Append(",\"corrected_floors\":").Append(details.CorrectedFloors.HasValue ? details.CorrectedFloors.Value.ToString() : "null");
                    sb.Append(",\"corrected_rooms\":").Append(details.CorrectedRooms.HasValue ? details.CorrectedRooms.Value.ToString() : "null");
                    sb.Append(",\"project_info_imported\":").Append(!details.ProjectInfoImported.HasValue ? "null" : (details.ProjectInfoImported.Value ? "true" : "false"));
                    sb.Append(",\"phase_mapping\":").Append(!details.PhaseMapping.HasValue ? "null" : (details.PhaseMapping.Value ? "true" : "false"));
                    sb.Append(",\"graphisoft_dir\":").Append(details.GraphisoftDir == null ? "null" : "\"" + Escape(details.GraphisoftDir) + "\"");
                    sb.Append(",\"edm_database_path\":").Append(details.EdmDatabasePath == null ? "null" : "\"" + Escape(details.EdmDatabasePath) + "\"");
                    sb.Append(",\"revit_version\":").Append(string.IsNullOrEmpty(details.RevitVersion) ? "null" : "\"" + Escape(details.RevitVersion) + "\"");
                    sb.Append(",\"addin_name\":").Append(string.IsNullOrEmpty(details.AddinName) ? "null" : "\"" + Escape(details.AddinName) + "\"");
                    sb.Append(",\"addin_version\":").Append(string.IsNullOrEmpty(details.AddinVersion) ? "null" : "\"" + Escape(details.AddinVersion) + "\"");
                    sb.Append(",\"preflight_error\":").Append(details.PreflightError == null ? "null" : "\"" + Escape(details.PreflightError) + "\"");
                }
                sb.Append("}");
                File.WriteAllText(path, sb.ToString());
            }
            catch { }
        }

        private static string Escape(string s) =>
            s?.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "").Replace("\n", " ");
    }

    [Transaction(TransactionMode.Manual)]
    [Regeneration(RegenerationOption.Manual)]
    public class ImportCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            return ImportRunner.Run(commandData.Application, ref message);
        }
    }
}
