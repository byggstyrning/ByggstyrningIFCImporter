using System;
using Byggstyrning.RoomImporter.Ifc;

namespace Byggstyrning.RoomImporter.Inspect;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length == 0 || args[0] is "-h" or "--help" or "/?")
        {
            Console.WriteLine("ByggstyrningRoomImporter.Inspect — IFC space boundary diagnostics (xBIM, no Revit).");
            Console.WriteLine();
            Console.WriteLine("Usage:");
            Console.WriteLine("  ByggstyrningRoomImporter.Inspect <path-to.ifc> [--space <IfcSpace GlobalId>]");
            Console.WriteLine();
            Console.WriteLine("Without --space, the first IfcSpace in the file is used.");
            return args.Length == 0 ? 1 : 0;
        }

        var ifc = args[0];
        string? spaceId = null;
        for (var i = 1; i < args.Length - 1; i++)
        {
            if (string.Equals(args[i], "--space", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                spaceId = args[++i];
        }

        var summary = IfcSpaceBoundaryDiagnostics.SummarizeFile(ifc);
        Console.WriteLine("=== File summary ===");
        Console.WriteLine($"IfcSpace count:              {summary.IfcSpaceCount}");
        Console.WriteLine($"IfcRelSpaceBoundary count:   {summary.IfcRelSpaceBoundaryCount}");
        if (summary.ArchicadSpaceBoundariesExportOff)
            Console.WriteLine("Header hint:                 FILE_DESCRIPTION contains \"IFC Space boundaries: Off\" (ArchiCAD).");
        if (!string.IsNullOrEmpty(summary.FileDescriptionExcerpt))
            Console.WriteLine($"FILE_DESCRIPTION excerpt:  {TruncateOneLine(summary.FileDescriptionExcerpt, 240)}");
        Console.WriteLine();

        var rows = IfcSpaceBoundaryDiagnostics.ListBoundariesForSpace(ifc, spaceId);
        Console.WriteLine(spaceId == null
            ? "=== IfcRelSpaceBoundary rows (first IfcSpace) ==="
            : $"=== IfcRelSpaceBoundary rows (IfcSpace GlobalId = {spaceId}) ===");

        foreach (var r in rows)
        {
            if (!string.IsNullOrEmpty(r.Detail) && string.IsNullOrEmpty(r.ExpressType))
            {
                Console.WriteLine(r.Detail);
                continue;
            }

            Console.WriteLine($"  #{r.EntityLabel} {r.ExpressType}  {r.PhysicalOrVirtual}");
            Console.WriteLine($"    ConnectionGeometry: {r.ConnectionGeometrySummary}");
            Console.WriteLine($"    TryExtractPolyline2D: {(r.ExtractOk ? "OK" : "FAIL")}  points={r.PointCount}");
            if (!string.IsNullOrEmpty(r.PointPreview))
                Console.WriteLine($"    Points: {r.PointPreview}");
            if (!string.IsNullOrEmpty(r.Detail))
                Console.WriteLine($"    Note: {r.Detail}");
        }

        return 0;
    }

    private static string TruncateOneLine(string s, int max)
    {
        var one = s.Replace('\r', ' ').Replace('\n', ' ');
        return one.Length <= max ? one : one.Substring(0, max) + "…";
    }
}
