using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Xbim.Ifc;
using Xbim.Ifc4.Interfaces;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>
    /// Explains why <see cref="IfcRoomModelLoader"/> may find no boundary loops: counts
    /// <c>IfcRelSpaceBoundary</c> in the file and, per relation, what connection geometry exists
    /// and whether <see cref="IfcCurveBoundaryExtractor"/> can turn it into 2D points.
    /// </summary>
    public static class IfcSpaceBoundaryDiagnostics
    {
        public sealed class IfcSpaceBoundaryFileSummary
        {
            public int IfcSpaceCount { get; set; }
            public int IfcRelSpaceBoundaryCount { get; set; }
            /// <summary>True when FILE_DESCRIPTION (or header text) contains ArchiCAD-style "IFC Space boundaries: Off".</summary>
            public bool ArchicadSpaceBoundariesExportOff { get; set; }
            /// <summary>Short excerpt around FILE_DESCRIPTION when found.</summary>
            public string? FileDescriptionExcerpt { get; set; }
        }

        public sealed class SpaceBoundaryRow
        {
            public int EntityLabel { get; set; }
            public string ExpressType { get; set; } = "";
            public string PhysicalOrVirtual { get; set; } = "";
            public string ConnectionGeometrySummary { get; set; } = "";
            public bool ExtractOk { get; set; }
            public int PointCount { get; set; }
            public string? PointPreview { get; set; }
            public string? Detail { get; set; }
        }

        public static IfcSpaceBoundaryFileSummary SummarizeFile(string ifcPath)
        {
            if (string.IsNullOrWhiteSpace(ifcPath))
                throw new ArgumentException("IFC path is required.", nameof(ifcPath));

            ReadHeaderHints(ifcPath, out var archOff, out var excerpt);

            IfcXbimDependencies.Ensure();
            using var store = IfcStore.Open(ifcPath, null, null);
            return new IfcSpaceBoundaryFileSummary
            {
                IfcSpaceCount = store.Instances.OfType<IIfcSpace>().Count(),
                IfcRelSpaceBoundaryCount = store.Instances.OfType<IIfcRelSpaceBoundary>().Count(),
                ArchicadSpaceBoundariesExportOff = archOff,
                FileDescriptionExcerpt = excerpt
            };
        }

        /// <summary>
        /// Lists every <see cref="IIfcRelSpaceBoundary"/> whose <c>RelatingSpace</c> matches the given
        /// <see cref="IIfcSpace"/> (by GlobalId if set, otherwise the first IfcSpace in the file).
        /// </summary>
        public static IReadOnlyList<SpaceBoundaryRow> ListBoundariesForSpace(string ifcPath, string? spaceGlobalId)
        {
            if (string.IsNullOrWhiteSpace(ifcPath))
                throw new ArgumentException("IFC path is required.", nameof(ifcPath));

            IfcXbimDependencies.Ensure();
            var rows = new List<SpaceBoundaryRow>();
            using var store = IfcStore.Open(ifcPath, null, null);

            var space = ResolveSpace(store, spaceGlobalId);
            if (space == null)
            {
                rows.Add(new SpaceBoundaryRow
                {
                    Detail = string.IsNullOrWhiteSpace(spaceGlobalId)
                        ? "No IfcSpace in file."
                        : $"IfcSpace with GlobalId '{spaceGlobalId}' not found."
                });
                return rows;
            }

            var sk = space.GlobalId != null ? space.GlobalId.ToString() : "#" + space.EntityLabel;
            foreach (var rsb in store.Instances.OfType<IIfcRelSpaceBoundary>())
            {
                if (!(rsb.RelatingSpace is IIfcSpace rel))
                    continue;
                if (rel.EntityLabel != space.EntityLabel)
                    continue;

                var cg = rsb.ConnectionGeometry;
                var summary = DescribeConnectionGeometry(cg);
                var ok = IfcCurveBoundaryExtractor.TryExtractPolyline2D(rsb, out var pts);
                string? preview = null;
                if (pts != null && pts.Count > 0)
                {
                    var n = Math.Min(4, pts.Count);
                    preview = string.Join("; ", pts.Take(n).Select(p => $"({p.x:F3},{p.y:F3})"));
                    if (pts.Count > n)
                        preview += $" … +{pts.Count - n} pts";
                }

                rows.Add(new SpaceBoundaryRow
                {
                    EntityLabel = rsb.EntityLabel,
                    ExpressType = rsb.ExpressType.Name,
                    PhysicalOrVirtual = SafePhysicalVirtual(rsb),
                    ConnectionGeometrySummary = summary,
                    ExtractOk = ok,
                    PointCount = pts?.Count ?? 0,
                    PointPreview = preview,
                    Detail = ok ? null : ExplainExtractFailure(cg, summary)
                });
            }

            if (rows.Count == 0)
            {
                rows.Add(new SpaceBoundaryRow
                {
                    Detail =
                        $"No IfcRelSpaceBoundary references IfcSpace '{sk}' ({space.Name ?? space.LongName ?? "?"}). " +
                        "If the file summary shows 0 relations globally, the exporter did not write space boundaries " +
                        "(e.g. ArchiCAD: enable \"IFC Space boundaries\" in export options)."
                });
            }

            return rows;
        }

        private static IIfcSpace? ResolveSpace(IfcStore store, string? globalId)
        {
            if (!string.IsNullOrWhiteSpace(globalId))
            {
                return store.Instances.OfType<IIfcSpace>().FirstOrDefault(s =>
                    s.GlobalId != null &&
                    string.Equals(s.GlobalId.ToString(), globalId, StringComparison.OrdinalIgnoreCase));
            }

            return store.Instances.OfType<IIfcSpace>().FirstOrDefault();
        }

        private static string SafePhysicalVirtual(IIfcRelSpaceBoundary rsb)
        {
            try
            {
                return rsb.PhysicalOrVirtualBoundary.ToString();
            }
            catch
            {
                return "?";
            }
        }

        private static string DescribeConnectionGeometry(object? cg)
        {
            if (cg == null)
                return "null (no ConnectionGeometry)";

            if (cg is IIfcConnectionCurveGeometry)
                return "IfcConnectionCurveGeometry";

            if (cg is IIfcConnectionSurfaceGeometry csg)
            {
                var surf = csg.SurfaceOnRelatingElement ?? csg.SurfaceOnRelatedElement;
                if (surf is IIfcCurveBoundedPlane)
                    return "IfcConnectionSurfaceGeometry → IfcCurveBoundedPlane";
                return surf == null
                    ? "IfcConnectionSurfaceGeometry → (no surface)"
                    : $"IfcConnectionSurfaceGeometry → {surf.ExpressType.Name}";
            }

            return cg.GetType().Name;
        }

        private static string? ExplainExtractFailure(object? cg, string summary)
        {
            if (cg == null)
                return "Extractor needs IfcConnectionCurveGeometry or IfcConnectionSurfaceGeometry with IfcCurveBoundedPlane + OuterBoundary.";

            if (cg is IIfcConnectionSurfaceGeometry &&
                summary.IndexOf("IfcCurveBoundedPlane", StringComparison.Ordinal) < 0)
                return "Surface is not IfcCurveBoundedPlane, or OuterBoundary is not a supported curve (polyline / trimmed / composite).";

            return "Curve type not supported by IfcCurveBoundaryExtractor (see IfcCurveBoundaryExtractor).";
        }

        private static void ReadHeaderHints(string path, out bool archicadSpaceBoundariesOff, out string? excerpt)
        {
            archicadSpaceBoundariesOff = false;
            excerpt = null;
            try
            {
                var text = File.ReadAllText(path, Encoding.UTF8);
                if (text.Length > 64_000)
                    text = text.Substring(0, 64_000);

                archicadSpaceBoundariesOff =
                    text.IndexOf("IFC Space boundaries: Off", StringComparison.OrdinalIgnoreCase) >= 0;

                var idx = text.IndexOf("FILE_DESCRIPTION", StringComparison.Ordinal);
                if (idx >= 0)
                {
                    var end = text.IndexOf("ENDSEC;", idx, StringComparison.Ordinal);
                    if (end > idx)
                    {
                        var len = Math.Min(end - idx, 5000);
                        excerpt = text.Substring(idx, len).Replace('\r', ' ').Replace('\n', ' ');
                    }
                }
            }
            catch
            {
                /* ignore */
            }
        }
    }
}
