using System;
using System.Globalization;
using System.Linq;
using System.Reflection;
using Xbim.Ifc4.Interfaces;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>
    /// Builds 4×4 transforms from IFC placements, aligned with <c>ifcopenshell.util.placement.get_local_placement</c>
    /// (parent · axis2placement chain).
    /// </summary>
    internal static class IfcPlacementMath
    {
        /// <summary>Row-major 4×4: p′ = M · (px,py,pz,1)ᵀ (same convention as numpy row display).</summary>
        internal static double[,] GetLocalPlacement(IIfcObjectPlacement? placement)
        {
            if (placement == null)
                return Identity();

            if (placement is IIfcLocalPlacement lp)
            {
                var parent = GetLocalPlacement(lp.PlacementRelTo);
                var local = GetAxis2Placement3D(lp.RelativePlacement as IIfcAxis2Placement3D);
                return Multiply(parent, local);
            }

            return Identity();
        }

        internal static void TransformPoint(double[,] m, double lx, double ly, double lz, out double wx, out double wy, out double wz)
        {
            wx = m[0, 0] * lx + m[0, 1] * ly + m[0, 2] * lz + m[0, 3];
            wy = m[1, 0] * lx + m[1, 1] * ly + m[1, 2] * lz + m[1, 3];
            wz = m[2, 0] * lx + m[2, 1] * ly + m[2, 2] * lz + m[2, 3];
        }

        private static double[,] Identity()
        {
            var m = new double[4, 4];
            m[0, 0] = m[1, 1] = m[2, 2] = m[3, 3] = 1.0;
            return m;
        }

        private static double[,] Multiply(double[,] a, double[,] b)
        {
            var r = new double[4, 4];
            for (var i = 0; i < 4; i++)
            for (var j = 0; j < 4; j++)
            {
                r[i, j] = a[i, 0] * b[0, j] + a[i, 1] * b[1, j] + a[i, 2] * b[2, j] + a[i, 3] * b[3, j];
            }

            return r;
        }

        /// <summary>Matches ifcopenshell <c>a2p</c> + transpose: columns x,y,z and translation.</summary>
        private static double[,] GetAxis2Placement3D(IIfcAxis2Placement3D? ap)
        {
            if (ap == null)
                return Identity();

            var ox = 0.0;
            var oy = 0.0;
            var oz = 0.0;
            if (ap.Location is IIfcCartesianPoint cp && cp.Coordinates != null)
            {
                var c = cp.Coordinates.ToList();
                if (c.Count > 0) ox = ToDouble(c[0]);
                if (c.Count > 1) oy = ToDouble(c[1]);
                if (c.Count > 2) oz = ToDouble(c[2]);
            }

            DirectionOrDefault(ap.Axis, 0, 0, 1, out var zx, out var zy, out var zz);
            DirectionOrDefault(ap.RefDirection, 1, 0, 0, out var xx, out var xy, out var xz);
            Normalize(ref zx, ref zy, ref zz);
            Normalize(ref xx, ref xy, ref xz);
            OrthogonalizeRefToZ(ref xx, ref xy, ref xz, zx, zy, zz);
            Normalize(ref xx, ref xy, ref xz);
            Cross(zx, zy, zz, xx, xy, xz, out var yx, out var yy, out var yz);
            Normalize(ref yx, ref yy, ref yz);

            // Row-major M: wx = M[0,0]*lx + ... + M[0,3]
            var m = new double[4, 4];
            m[0, 0] = xx;
            m[0, 1] = yx;
            m[0, 2] = zx;
            m[0, 3] = ox;
            m[1, 0] = xy;
            m[1, 1] = yy;
            m[1, 2] = zy;
            m[1, 3] = oy;
            m[2, 0] = xz;
            m[2, 1] = yz;
            m[2, 2] = zz;
            m[2, 3] = oz;
            m[3, 3] = 1.0;
            return m;
        }

        private static void OrthogonalizeRefToZ(ref double xx, ref double xy, ref double xz, double zx, double zy, double zz)
        {
            // X' = X - Z * dot(X,Z)
            var d = xx * zx + xy * zy + xz * zz;
            xx -= d * zx;
            xy -= d * zy;
            xz -= d * zz;
        }

        private static void DirectionOrDefault(IIfcDirection? d, double dx, double dy, double dz, out double x, out double y, out double z)
        {
            if (d?.DirectionRatios == null)
            {
                x = dx;
                y = dy;
                z = dz;
                return;
            }

            var list = d.DirectionRatios.ToList();
            x = list.Count > 0 ? ToDouble(list[0]) : dx;
            y = list.Count > 1 ? ToDouble(list[1]) : dy;
            z = list.Count > 2 ? ToDouble(list[2]) : dz;
        }

        private static void Cross(
            double ax, double ay, double az,
            double bx, double by, double bz,
            out double cx, out double cy, out double cz)
        {
            cx = ay * bz - az * by;
            cy = az * bx - ax * bz;
            cz = ax * by - ay * bx;
        }

        private static void Normalize(ref double x, ref double y, ref double z)
        {
            var len = Math.Sqrt(x * x + y * y + z * z);
            if (len < 1e-12)
                return;
            x /= len;
            y /= len;
            z /= len;
        }

        private static double ToDouble(object item)
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
