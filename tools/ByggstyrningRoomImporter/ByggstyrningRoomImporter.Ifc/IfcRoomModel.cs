using System.Collections.Generic;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>2D point in IFC length units (metres) for horizontal room boundaries.</summary>
    public sealed class IfcVec2
    {
        public double X { get; set; }
        public double Y { get; set; }

        public IfcVec2()
        {
        }

        public IfcVec2(double x, double y)
        {
            X = x;
            Y = y;
        }
    }

    /// <summary>One closed boundary loop (XY, metres) for a space, CCW or CW.</summary>
    public sealed class IfcBoundaryLoop2d
    {
        /// <summary>Vertices in order; first vertex is not repeated at the end.</summary>
        public List<IfcVec2> Vertices { get; } = new List<IfcVec2>();
    }

    /// <summary>One building storey from IFC (IfcBuildingStorey).</summary>
    public sealed class IfcStoreyInfo
    {
        public string Key { get; set; } = "";
        public string? Name { get; set; }
        public string? LongName { get; set; }
        /// <summary>Elevation in metres (IFC length measure).</summary>
        public double ElevationMeters { get; set; }
    }

    /// <summary>One IFC property on a space (from an <c>IfcPropertySet</c>).</summary>
    public sealed class IfcSpaceProperty
    {
        public string PsetName { get; set; } = "";
        public string PropertyName { get; set; } = "";
        public string Value { get; set; } = "";
    }

    /// <summary>One space (IfcSpace) to map to a Revit Room.</summary>
    public sealed class IfcSpaceInfo
    {
        public string Key { get; set; } = "";
        public string? Name { get; set; }
        public string? LongName { get; set; }
        public string? Number { get; set; }
        /// <summary>Storey key matching <see cref="IfcStoreyInfo.Key"/>.</summary>
        public string? StoreyKey { get; set; }
        /// <summary>Placement XY in metres (world), Z ignored for level assignment.</summary>
        public double XMetres { get; set; }
        public double YMetres { get; set; }
        public double ZMetres { get; set; }
        public int BoundaryCount { get; set; }

        /// <summary>
        /// Closed loops in world XY (metres): from <c>IfcRelSpaceBoundary</c> when present, otherwise from
        /// <c>FootPrint</c> / <c>GeometricCurveSet</c> / <c>IfcPolyline</c> on the space (e.g. ArchiCAD).
        /// </summary>
        public List<IfcBoundaryLoop2d> BoundaryLoops { get; } = new List<IfcBoundaryLoop2d>();

        /// <summary>Properties from <c>Pset_SpaceCommon</c> (name → nominal string).</summary>
        public Dictionary<string, string> PsetSpaceCommon { get; } =
            new Dictionary<string, string>(System.StringComparer.OrdinalIgnoreCase);

        /// <summary>All property sets on the space (single + enumerated values); use for Revit shared-parameter mapping.</summary>
        public List<IfcSpaceProperty> SpaceProperties { get; } = new List<IfcSpaceProperty>();
    }

    /// <summary>DTO produced from an IFC rooms file (xBIM only, no Revit).</summary>
    public sealed class IfcRoomModel
    {
        public List<IfcStoreyInfo> Storeys { get; } = new List<IfcStoreyInfo>();
        public List<IfcSpaceInfo> Spaces { get; } = new List<IfcSpaceInfo>();

        /// <summary>Non-fatal loader issues (missing geometry, merge failures, etc.).</summary>
        public List<string> LoadWarnings { get; } = new List<string>();

        /// <summary>Opens the IFC and extracts storeys and spaces (xBIM only).</summary>
        public static IfcRoomModel Load(string ifcPath)
        {
            IfcXbimDependencies.Ensure();
            return IfcRoomModelLoader.Load(ifcPath);
        }
    }
}
