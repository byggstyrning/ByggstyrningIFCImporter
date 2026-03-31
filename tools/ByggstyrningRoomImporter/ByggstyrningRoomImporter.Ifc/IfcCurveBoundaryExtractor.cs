using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using Xbim.Ifc4.Interfaces;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>Extracts 2D polylines (metres, XY) from IFC connection geometry and curves (Essentials-only).</summary>
    internal static class IfcCurveBoundaryExtractor
    {
        /// <summary>Try to get 2D points from <see cref="IIfcRelSpaceBoundary.ConnectionGeometry"/>.</summary>
        internal static bool TryExtractPolyline2D(IIfcRelSpaceBoundary rsb, out List<(double x, double y)> points)
        {
            points = new List<(double, double)>();
            var cg = rsb.ConnectionGeometry;
            if (cg == null)
                return false;

            if (cg is IIfcConnectionCurveGeometry ccg)
            {
                var curve = AsIfcCurve(ccg.CurveOnRelatingElement ?? ccg.CurveOnRelatedElement);
                if (TryExtractCurve2D(curve, points))
                    return points.Count >= 2;
                return false;
            }

            if (cg is IIfcConnectionSurfaceGeometry csg)
            {
                var surf = csg.SurfaceOnRelatingElement ?? csg.SurfaceOnRelatedElement;
                if (surf is IIfcCurveBoundedPlane cbp && cbp.OuterBoundary != null)
                {
                    if (TryExtractCurve2D(cbp.OuterBoundary, points))
                        return points.Count >= 2;
                }

                return false;
            }

            return false;
        }

        internal static bool TryExtractCurve2D(IIfcCurve? curve, List<(double x, double y)> points)
        {
            if (curve == null)
                return false;

            if (curve is IIfcPolyline pl)
            {
                AppendPolylinePoints(pl, points);
                return points.Count >= 2;
            }

            if (curve is IIfcTrimmedCurve tc)
            {
                if (tc.BasisCurve is IIfcPolyline pl2)
                {
                    var tmp = new List<(double, double)>();
                    AppendPolylinePoints(pl2, tmp);
                    if (tmp.Count < 2)
                        return false;
                    if (TryTrimPolyline(tc, tmp, out var seg) && seg.Count >= 2)
                    {
                        points.AddRange(seg);
                        return true;
                    }
                }

                return TryExtractCurve2D(tc.BasisCurve, points);
            }

            if (curve is IIfcCompositeCurve cc)
            {
                foreach (var seg in cc.Segments ?? Enumerable.Empty<IIfcCompositeCurveSegment>())
                {
                    if (seg?.ParentCurve == null)
                        continue;
                    var before = points.Count;
                    TryExtractCurve2D(seg.ParentCurve, points);
                    if (points.Count > before && before > 0)
                    {
                        var a = points[before - 1];
                        var b = points[before];
                        if (Dist2(a, b) < 1e-12)
                            points.RemoveAt(points.Count - 1);
                    }
                }

                return points.Count >= 2;
            }

            return false;
        }

        private static IIfcCurve? AsIfcCurve(IIfcCurveOrEdgeCurve? c)
        {
            if (c == null)
                return null;
            if (c is IIfcCurve curve)
                return curve;
            if (c is IIfcEdgeCurve ec)
                return ec.EdgeGeometry;
            return null;
        }

        private static void AppendPolylinePoints(IIfcPolyline pl, List<(double x, double y)> points)
        {
            foreach (var p in pl.Points ?? Enumerable.Empty<IIfcCartesianPoint>())
                points.Add(CartesianToXY(p));
        }

        private static (double x, double y) CartesianToXY(IIfcCartesianPoint cp)
        {
            if (cp.Coordinates == null)
                return (0, 0);
            var list = cp.Coordinates.ToList();
            var x = list.Count > 0 ? CoordinateToDouble(list[0]) : 0;
            var y = list.Count > 1 ? CoordinateToDouble(list[1]) : 0;
            return (x, y);
        }

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

        private static bool TryTrimPolyline(IIfcTrimmedCurve tc, IReadOnlyList<(double x, double y)> poly,
            out List<(double x, double y)> result)
        {
            result = new List<(double, double)>();
            if (poly.Count < 2)
                return false;

            var i0 = 0;
            var i1 = poly.Count - 1;
            var trim1 = tc.Trim1?.FirstOrDefault();
            var trim2 = tc.Trim2?.FirstOrDefault();
            if (trim1 is IIfcCartesianPoint cp1)
            {
                var t = CartesianToXY(cp1);
                i0 = NearestVertexIndex(poly, t);
            }

            if (trim2 is IIfcCartesianPoint cp2)
            {
                var t = CartesianToXY(cp2);
                i1 = NearestVertexIndex(poly, t);
            }

            if (i0 > i1)
                (i0, i1) = (i1, i0);

            for (var i = i0; i <= i1; i++)
                result.Add(poly[i]);

            return result.Count >= 2;
        }

        private static int NearestVertexIndex(IReadOnlyList<(double x, double y)> poly, (double x, double y) t)
        {
            var best = 0;
            var bestD = double.MaxValue;
            for (var i = 0; i < poly.Count; i++)
            {
                var d = Dist2(poly[i], t);
                if (d < bestD)
                {
                    bestD = d;
                    best = i;
                }
            }

            return best;
        }

        private static double Dist2((double x, double y) a, (double x, double y) b)
        {
            var dx = a.x - b.x;
            var dy = a.y - b.y;
            return dx * dx + dy * dy;
        }
    }
}
