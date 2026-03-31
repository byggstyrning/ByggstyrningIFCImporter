using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace Byggstyrning.RoomImporter
{
    /// <summary>Interior <see cref="UV"/> for <c>NewRoom(Level, UV)</c> from a closed polygon (Revit internal units).</summary>
    internal static class RoomInteriorUv
    {
        internal static UV? TryInteriorUv(IReadOnlyList<XYZ> ring)
        {
            if (ring == null || ring.Count < 3)
                return null;

            var poly = new List<(double x, double y)>(ring.Count);
            foreach (var p in ring)
                poly.Add((p.X, p.Y));

            if (TryInteriorFromPolygon(poly, out var u, out var v))
                return new UV(u, v);
            return null;
        }

        private static bool TryInteriorFromPolygon(IReadOnlyList<(double x, double y)> poly, out double u, out double v)
        {
            u = v = 0;
            if (poly.Count < 3)
                return false;

            double cx = 0, cy = 0;
            foreach (var p in poly)
            {
                cx += p.x;
                cy += p.y;
            }

            cx /= poly.Count;
            cy /= poly.Count;
            if (PointInPolygon(cx, cy, poly))
            {
                u = cx;
                v = cy;
                return true;
            }

            if (TryShoelaceCentroid(poly, out var cxa, out var cya) && PointInPolygon(cxa, cya, poly))
            {
                u = cxa;
                v = cya;
                return true;
            }

            var xmin = double.MaxValue;
            var xmax = double.MinValue;
            var ymin = double.MaxValue;
            var ymax = double.MinValue;
            foreach (var p in poly)
            {
                xmin = Math.Min(xmin, p.x);
                xmax = Math.Max(xmax, p.x);
                ymin = Math.Min(ymin, p.y);
                ymax = Math.Max(ymax, p.y);
            }

            const int steps = 8;
            for (var ix = 1; ix < steps; ix++)
            {
                for (var iy = 1; iy < steps; iy++)
                {
                    var tx = xmin + (xmax - xmin) * ix / steps;
                    var ty = ymin + (ymax - ymin) * iy / steps;
                    if (PointInPolygon(tx, ty, poly))
                    {
                        u = tx;
                        v = ty;
                        return true;
                    }
                }
            }

            u = (xmin + xmax) * 0.5;
            v = (ymin + ymax) * 0.5;
            return true;
        }

        private static bool TryShoelaceCentroid(IReadOnlyList<(double x, double y)> poly, out double cx, out double cy)
        {
            cx = cy = 0;
            double a = 0;
            var n = poly.Count;
            for (var i = 0; i < n; i++)
            {
                var j = (i + 1) % n;
                var cross = poly[i].x * poly[j].y - poly[j].x * poly[i].y;
                a += cross;
                cx += (poly[i].x + poly[j].x) * cross;
                cy += (poly[i].y + poly[j].y) * cross;
            }

            if (Math.Abs(a) < 1e-18)
                return false;
            a *= 0.5;
            cx /= 6.0 * a;
            cy /= 6.0 * a;
            return true;
        }

        private static bool PointInPolygon(double x, double y, IReadOnlyList<(double x, double y)> poly)
        {
            var inside = false;
            var n = poly.Count;
            var j = n - 1;
            for (var i = 0; i < n; i++)
            {
                var xi = poly[i].x;
                var yi = poly[i].y;
                var xj = poly[j].x;
                var yj = poly[j].y;
                if (((yi > y) != (yj > y)) &&
                    (x < (xj - xi) * (y - yi) / (yj - yi + 1e-18) + xi))
                    inside = !inside;
                j = i;
            }

            return inside;
        }
    }
}
