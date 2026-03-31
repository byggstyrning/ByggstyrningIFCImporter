using System;
using System.IO;
using System.Text;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Byggstyrning.RoomImporter.Ifc;

namespace Byggstyrning.RoomImporter
{
    /// <summary>Entry point for RBP / IronPython (mirrors ByggstyrningIFCImporter.ImportRunner pattern).</summary>
    public static class RoomImportRunner
    {
        public static Result Run(UIApplication uiApp)
        {
            string? msg = null;
            return Run(uiApp, ref msg);
        }

        public static Result Run(UIApplication uiApp, ref string? message)
        {
            string? ifcPath = Environment.GetEnvironmentVariable("BYGG_IFC_PATH");
            string? outputPath = Environment.GetEnvironmentVariable("BYGG_IFC_OUTPUT_PATH");
            string? resultPath = Environment.GetEnvironmentVariable("BYGG_IFC_RESULT_PATH");
            string? logPath = Environment.GetEnvironmentVariable("BYGG_IFC_LOG_PATH");

            if (string.IsNullOrWhiteSpace(ifcPath) || !File.Exists(ifcPath))
            {
                message = "BYGG_IFC_PATH must point to an existing IFC file.";
                WriteResult(resultPath, false, message, 0, 0, 0, "[]");
                return Result.Failed;
            }

            var doc = TryResolveOpenDocument(uiApp);
            if (doc == null)
            {
                message = "No open project document (BatchRvt seed RVT must be open; ActiveUIDocument is often null in batch — set BYGG_RBP_SEED_RVT to match the file list path).";
                WriteResult(resultPath, false, message, 0, 0, 0, "[]");
                return Result.Failed;
            }

            Log(logPath, "ByggstyrningRoomImporter (xBIM) starting");
            Log(logPath, "  IFC: " + ifcPath);
            Log(logPath, "  Doc: " + doc.PathName);

            try
            {
                var model = IfcRoomModel.Load(ifcPath);
                Log(logPath, $"  IFC storeys: {model.Storeys.Count}, spaces: {model.Spaces.Count}");

                using (var txBind = new Transaction(doc, "Byggstyrning IFC shared parameters (rooms)"))
                {
                    txBind.Start();
                    RoomSharedParameterBinding.EnsureRoomBindings(doc, uiApp.Application, ifcPath, s => Log(logPath, s));
                    txBind.Commit();
                }

                RevitRoomBuilder.BuildResult build;
                using (var txg = new TransactionGroup(doc, "Byggstyrning xBIM rooms import"))
                {
                    txg.Start();
                    using (var tx = new Transaction(doc, "Create rooms from IFC"))
                    {
                        tx.Start();
                        build = RevitRoomBuilder.Build(doc, model);
                        tx.Commit();
                    }

                    txg.Assimilate();
                }

                foreach (var w in build.Warnings)
                    Log(logPath, "  WARN: " + w);

                var warnJson = WarningsToJson(build.Warnings);
                WriteResult(resultPath, true, null, build.RoomsCreated, build.LevelsCreated, build.BoundaryLoopsApplied, warnJson);
                message = null;

                if (!string.IsNullOrWhiteSpace(outputPath))
                {
                    var dir = Path.GetDirectoryName(outputPath);
                    if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                        Directory.CreateDirectory(dir);
                    doc.SaveAs(outputPath, new SaveAsOptions { OverwriteExistingFile = true });
                    Log(logPath, "  Saved: " + outputPath);
                }

                Log(logPath, "ByggstyrningRoomImporter completed successfully");
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.ToString();
                Log(logPath, "FATAL: " + ex);
                WriteResult(resultPath, false, ex.Message, 0, 0, 0, "[]");
                return Result.Failed;
            }
        }

        private static string WarningsToJson(System.Collections.Generic.IReadOnlyList<string> warnings)
        {
            if (warnings == null || warnings.Count == 0) return "[]";
            var sb = new StringBuilder();
            sb.Append('[');
            for (var i = 0; i < warnings.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append('"').Append(EscapeJson(warnings[i])).Append('"');
            }

            sb.Append(']');
            return sb.ToString();
        }

        private static void Log(string? logPath, string line)
        {
            var text = $"[{DateTime.Now:HH:mm:ss.fff}] {line}";
            System.Diagnostics.Debug.WriteLine("[ByggstyrningRoomImporter] " + text);
            if (!string.IsNullOrEmpty(logPath))
            {
                try
                {
                    File.AppendAllText(logPath, text + Environment.NewLine, Encoding.UTF8);
                }
                catch
                {
                    /* ignore */
                }
            }
        }

        private static void WriteResult(string? path, bool success, string? error, int rooms, int levels, int boundaryLoopsApplied, string warningsJson)
        {
            if (string.IsNullOrEmpty(path)) return;
            try
            {
                var err = error == null ? "null" : "\"" + EscapeJson(error) + "\"";
                var json =
                    $"{{\"success\":{(success ? "true" : "false")},\"error\":{err},\"rooms_created\":{rooms},\"levels_created\":{levels},\"boundary_loops_applied\":{boundaryLoopsApplied},\"warnings\":{warningsJson}}}";
                File.WriteAllText(path, json, Encoding.UTF8);
            }
            catch
            {
                /* ignore */
            }
        }

        private static string EscapeJson(string s)
        {
            return s.Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\r", "")
                .Replace("\n", " ");
        }

        /// <summary>
        /// BatchRvt often has no <see cref="UIApplication.ActiveUIDocument"/> even when the seed
        /// <c>.rvt</c> from the file list is open. Prefer the active document, then a document whose
        /// path matches <c>BYGG_RBP_SEED_RVT</c>, then the first non–family document.
        /// </summary>
        private static Document? TryResolveOpenDocument(UIApplication uiApp)
        {
            var active = uiApp.ActiveUIDocument?.Document;
            if (active != null && !active.IsFamilyDocument)
                return active;

            string? seedHint = Environment.GetEnvironmentVariable("BYGG_RBP_SEED_RVT");
            if (!string.IsNullOrWhiteSpace(seedHint))
            {
                try
                {
                    seedHint = Path.GetFullPath(seedHint);
                }
                catch
                {
                    seedHint = null;
                }
            }

            Document? fallback = null;
            foreach (Document d in uiApp.Application.Documents)
            {
                if (d == null || d.IsFamilyDocument)
                    continue;

                if (!string.IsNullOrWhiteSpace(seedHint) && PathsEqual(d.PathName, seedHint))
                    return d;

                fallback ??= d;
            }

            return fallback;
        }

        private static bool PathsEqual(string? a, string? b)
        {
            if (string.IsNullOrWhiteSpace(a) || string.IsNullOrWhiteSpace(b))
                return false;
            try
            {
                return string.Equals(
                    Path.GetFullPath(a),
                    Path.GetFullPath(b),
                    StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return false;
            }
        }
    }
}
