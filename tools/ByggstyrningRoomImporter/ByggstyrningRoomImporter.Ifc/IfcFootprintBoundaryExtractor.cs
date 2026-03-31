using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using Xbim.Ifc4.Interfaces;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>
    /// ArchiCAD (and others) often omit <c>IfcRelSpaceBoundary</c> but attach a <c>FootPrint</c>
    /// <see cref="IIfcShapeRepresentation"/> with <c>GeometricCurveSet</c> containing an <see cref="IIfcPolyline"/>.
    /// This extracts that loop and maps local XY to world XY using <see cref="IfcPlacementMath"/>.
    /// </summary>
    internal static class IfcFootprintBoundaryExtractor
    {
        internal static bool TryGetFootprintLoopWorld2D(IIfcSpace space, out IfcBoundaryLoop2d loop)
        {
            loop = new IfcBoundaryLoop2d();
            if (space.Representation is not IIfcProductDefinitionShape pds)
                return false;

            IIfcPolyline? poly = null;
            foreach (var rep in pds.Representations ?? Enumerable.Empty<IIfcRepresentation>())
            {
                if (rep is not IIfcShapeRepresentation shapeRep)
                    continue;
                if (!string.Equals(Label(shapeRep.RepresentationIdentifier), "FootPrint", StringComparison.OrdinalIgnoreCase))
                    continue;
                if (!string.Equals(Label(shapeRep.RepresentationType), "GeometricCurveSet", StringComparison.OrdinalIgnoreCase))
                    continue;

                foreach (var item in shapeRep.Items ?? Enumerable.Empty<IIfcRepresentationItem>())
                {
                    if (item is IIfcGeometricCurveSet gcs)
                    {
                        foreach (var el in gcs.Elements)
                        {
                            if (el is IIfcPolyline pl)
                            {
                                poly = pl;
                                break;
                            }
                        }
                    }
                    else if (item is IIfcPolyline pl2)
                    {
                        poly = pl2;
                    }

                    if (poly != null)
                        break;
                }

                if (poly != null)
                    break;
            }

            if (poly?.Points == null)
                return false;

            var local = new List<(double x, double y)>();
            foreach (var p in poly.Points)
            {
                if (p is not IIfcCartesianPoint cp || cp.Coordinates == null)
                    continue;
                var c = cp.Coordinates.ToList();
                var x = c.Count > 0 ? CoordinateToDouble(c[0]) : 0;
                var y = c.Count > 1 ? CoordinateToDouble(c[1]) : 0;
                local.Add((x, y));
            }

            if (local.Count < 3)
                return false;

            if (Dist2(local[0], local[local.Count - 1]) <= 1e-8 * 1e-8)
                local.RemoveAt(local.Count - 1);

            if (local.Count < 3)
                return false;

            var m = IfcPlacementMath.GetLocalPlacement(space.ObjectPlacement);
            foreach (var q in local)
            {
                IfcPlacementMath.TransformPoint(m, q.x, q.y, 0, out var wx, out var wy, out _);
                loop.Vertices.Add(new IfcVec2(wx, wy));
            }

            return loop.Vertices.Count >= 3;
        }

        private static string? Label(object? o)
        {
            if (o == null)
                return null;
            return Convert.ToString(o, CultureInfo.InvariantCulture);
        }

        private static double Dist2((double x, double y) a, (double x, double y) b)
        {
            var dx = a.x - b.x;
            var dy = a.y - b.y;
            return dx * dx + dy * dy;
        }

        /// <summary>Same rules as <see cref="IfcCurveBoundaryExtractor"/> (IfcLengthMeasure, etc.).</summary>
        private static double CoordinateToDouble(object item)
        {
            if (item == null)
                return 0;
            if (item is double d)
                return d;
            if (item is float f)
                return f;
            if (item is int i)
                return i;
            if (item is IConvertible c)
                return Convert.ToDouble(c, CultureInfo.InvariantCulture);

            var p = item.GetType().GetProperty("Value", BindingFlags.Public | BindingFlags.Instance);
            if (p != null)
            {
                var v = p.GetValue(item);
                if (v is IConvertible c2)
                    return Convert.ToDouble(c2, CultureInfo.InvariantCulture);
            }

            return double.Parse(Convert.ToString(item, CultureInfo.InvariantCulture)!, CultureInfo.InvariantCulture);
        }
    }
}
