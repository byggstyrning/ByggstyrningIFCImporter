using System;
using System.IO;
using System.Reflection;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>
    /// Preloads xBIM satellite assemblies before <see cref="Xbim.Ifc.IfcStore"/> static initialization.
    /// Required for VSTest (shadow copy) and consistent probing next to the deployment folder.
    /// </summary>
    internal static class IfcXbimDependencies
    {
        private static readonly object LockObj = new object();
        private static bool _done;

        internal static void Ensure()
        {
            lock (LockObj)
            {
                if (_done) return;
                Run();
                _done = true;
            }
        }

        private static void Run()
        {
            var dirs = ResolveDependencyDirectories();
            foreach (var dir in dirs)
            {
                foreach (var pre in new[]
                         {
                             "Microsoft.Extensions.DependencyInjection.Abstractions.dll",
                             "Microsoft.Extensions.DependencyInjection.dll"
                         })
                {
                    try
                    {
                        var p = Path.Combine(dir, pre);
                        if (File.Exists(p))
                            Assembly.LoadFrom(p);
                    }
                    catch
                    {
                        /* ignore */
                    }
                }
            }

            AppDomain.CurrentDomain.AssemblyResolve += (_, args) =>
            {
                try
                {
                    var simple = new AssemblyName(args.Name).Name;
                    if (string.IsNullOrEmpty(simple)) return null;
                    foreach (var d in dirs)
                    {
                        var path = Path.Combine(d, simple + ".dll");
                        if (File.Exists(path))
                            return Assembly.LoadFrom(path);
                    }
                }
                catch
                {
                    /* ignore */
                }

                return null;
            };
        }

        private static System.Collections.Generic.List<string> ResolveDependencyDirectories()
        {
            var list = new System.Collections.Generic.List<string>();
            var baseDir = AppDomain.CurrentDomain.BaseDirectory ?? "";
            if (!string.IsNullOrEmpty(baseDir))
                list.Add(baseDir);
            var loc = typeof(IfcXbimDependencies).Assembly.Location;
            var asmDir = Path.GetDirectoryName(loc) ?? "";
            if (!string.IsNullOrEmpty(asmDir) && !list.Contains(asmDir))
                list.Add(asmDir);
            try
            {
                var ctx = AppContext.BaseDirectory;
                if (!string.IsNullOrEmpty(ctx) && !list.Contains(ctx))
                    list.Add(ctx);
            }
            catch
            {
                /* ignore */
            }

            return list;
        }
    }
}
