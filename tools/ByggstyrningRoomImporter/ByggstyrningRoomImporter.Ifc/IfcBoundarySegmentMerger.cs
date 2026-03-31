using System;
using System.Collections.Generic;
using System.Linq;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>Merges 2D line segments into closed loops (metres).</summary>
    internal static class IfcBoundarySegmentMerger
    {
        private const double TolMetres = 0.002;

        internal static List<List<(double x, double y)>> MergeSegmentsToClosedLoops(
            IReadOnlyList<((double x, double y) a, (double x, double y) b)> segments)
        {
            var loops = new List<List<(double, double)>>();
            if (segments == null || segments.Count == 0)
                return loops;

            var unused = segments.Select(s => (s.a, s.b)).ToList();
            var tol = TolMetres * TolMetres;

            while (unused.Count > 0)
            {
                var seg = unused[unused.Count - 1];
                unused.RemoveAt(unused.Count - 1);
                var chain = new List<(double x, double y)> { seg.a, seg.b };

                var extended = true;
                while (extended)
                {
                    extended = false;
                    for (var i = unused.Count - 1; i >= 0; i--)
                    {
                        var s = unused[i];
                        var first = chain[0];
                        var last = chain[chain.Count - 1];

                        if (Dist2(s.b, last) <= tol)
                        {
                            chain.Add(s.a);
                            unused.RemoveAt(i);
                            extended = true;
                            break;
                        }

                        if (Dist2(s.a, last) <= tol)
                        {
                            chain.Add(s.b);
                            unused.RemoveAt(i);
                            extended = true;
                            break;
                        }

                        if (Dist2(s.a, first) <= tol)
                        {
                            chain.Insert(0, s.b);
                            unused.RemoveAt(i);
                            extended = true;
                            break;
                        }

                        if (Dist2(s.b, first) <= tol)
                        {
                            chain.Insert(0, s.a);
                            unused.RemoveAt(i);
                            extended = true;
                            break;
                        }
                    }
                }

                if (chain.Count < 3)
                    continue;

                if (Dist2(chain[0], chain[chain.Count - 1]) <= tol)
                {
                    chain.RemoveAt(chain.Count - 1);
                    if (chain.Count >= 3)
                        DeduplicateColinear(chain);
                    if (chain.Count >= 3)
                        loops.Add(chain);
                }
            }

            return loops;
        }

        private static void DeduplicateColinear(List<(double x, double y)> ring)
        {
            if (ring.Count < 4)
                return;
            for (var pass = 0; pass < ring.Count && pass < 8; pass++)
            {
                var removed = false;
                for (var i = ring.Count - 1; i >= 0; i--)
                {
                    var prev = ring[(i - 1 + ring.Count) % ring.Count];
                    var cur = ring[i];
                    var next = ring[(i + 1) % ring.Count];
                    if (IsColinear(prev, cur, next))
                    {
                        ring.RemoveAt(i);
                        removed = true;
                        break;
                    }
                }

                if (!removed)
                    break;
            }
        }

        private static bool IsColinear((double x, double y) a, (double x, double y) b, (double x, double y) c)
        {
            var cross = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
            return cross * cross < 1e-16;
        }

        private static double Dist2((double x, double y) a, (double x, double y) b)
        {
            var dx = a.x - b.x;
            var dy = a.y - b.y;
            return dx * dx + dy * dy;
        }
    }
}
