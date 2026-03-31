using System;
using System.IO;
using Autodesk.Revit.ApplicationServices;
using Autodesk.Revit.DB;

namespace Byggstyrning.RoomImporter
{
    /// <summary>
    /// Binds shared parameters from a Revit shared-parameter text file to <see cref="BuiltInCategory.OST_Rooms"/>
    /// so <see cref="RoomPropertyMapping"/> can set IFC values by name (same workflow as Graphisoft IFC import).
    /// </summary>
    internal static class RoomSharedParameterBinding
    {
        private const string IfcParametersGroupName = "IFC Parameters";

        /// <summary>
        /// Optional env: absolute path to a <c>.txt</c> shared-parameter file.
        /// If unset, uses <c>{ifcPath}.sharedparameters.txt</c> when that file exists (e.g. export next to IFC).
        /// </summary>
        internal static void EnsureRoomBindings(
            Document doc,
            Application app,
            string ifcPath,
            Action<string>? log)
        {
            string? path = Environment.GetEnvironmentVariable("BYGG_SHARED_PARAMETERS_PATH");
            if (string.IsNullOrWhiteSpace(path))
                path = ifcPath + ".sharedparameters.txt";

            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                log?.Invoke("Shared parameters file not found (optional); room IFC custom params may stay empty: " + path);
                return;
            }

            try
            {
                path = Path.GetFullPath(path);
            }
            catch
            {
                return;
            }

            string? previous = app.SharedParametersFilename;
            try
            {
                app.SharedParametersFilename = path;
                var defFile = app.OpenSharedParameterFile();
                if (defFile == null)
                {
                    log?.Invoke("OpenSharedParameterFile returned null for: " + path);
                    return;
                }

                var roomCat = Category.GetCategory(doc, BuiltInCategory.OST_Rooms);
                var catSet = app.Create.NewCategorySet();
                catSet.Insert(roomCat);
                var instanceBinding = app.Create.NewInstanceBinding(catSet);
                var map = doc.ParameterBindings;

                var bound = 0;
                foreach (DefinitionGroup g in defFile.Groups)
                {
                    if (!string.Equals(g.Name, IfcParametersGroupName, StringComparison.Ordinal))
                        continue;

                    foreach (Definition d in g.Definitions)
                    {
                        if (d is not ExternalDefinition ext)
                            continue;
                        if (map.Contains(ext))
                            continue;
                        try
                        {
                            if (map.Insert(ext, instanceBinding, GroupTypeId.Ifc))
                                bound++;
                        }
                        catch
                        {
                            /* ignore single def */
                        }
                    }
                }

                log?.Invoke($"Shared parameters: bound {bound} definition(s) to Rooms from {path}");
            }
            finally
            {
                try
                {
                    if (!string.IsNullOrEmpty(previous))
                        app.SharedParametersFilename = previous;
                }
                catch
                {
                    /* ignore */
                }
            }
        }
    }
}
