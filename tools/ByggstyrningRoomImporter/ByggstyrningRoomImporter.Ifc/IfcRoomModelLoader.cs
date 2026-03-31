using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Xbim.Ifc;
using Xbim.Ifc4.Interfaces;

namespace Byggstyrning.RoomImporter.Ifc
{
    /// <summary>Loads <see cref="IfcRoomModel"/> from disk using xBIM (no Revit).</summary>
    public static class IfcRoomModelLoader
    {
        public static IfcRoomModel Load(string ifcPath)
        {
            if (string.IsNullOrWhiteSpace(ifcPath))
                throw new ArgumentException("IFC path is required.", nameof(ifcPath));

            IfcXbimDependencies.Ensure();

            var model = new IfcRoomModel();
            using (var store = IfcStore.Open(ifcPath, null, null))
            {
                var storeyMap = new Dictionary<string, IfcStoreyInfo>();

                foreach (var st in store.Instances.OfType<IIfcBuildingStorey>())
                {
                    var key = KeyFor(st);
                    // IFC2x3 via xBIM often leaves IIfcBuildingStorey.Elevation unset; STEP still has Elevation on the
                    // entity and/or local placement Z on ObjectPlacement. Without distinct elevations, RevitRoomBuilder
                    // matches every storey to the same existing Level (e.g. 0 m).
                    var elev = GetStoreyElevationMetres(st);

                    var info = new IfcStoreyInfo
                    {
                        Key = key,
                        Name = st.Name,
                        LongName = st.LongName,
                        ElevationMeters = elev
                    };
                    storeyMap[key] = info;
                    model.Storeys.Add(info);
                }

                model.Storeys.Sort((a, b) => a.ElevationMeters.CompareTo(b.ElevationMeters));

                foreach (var rel in store.Instances.OfType<IIfcRelContainedInSpatialStructure>())
                {
                    if (!(rel.RelatingStructure is IIfcBuildingStorey storey))
                        continue;

                    var storeyKey = KeyFor(storey);

                    foreach (var def in rel.RelatedElements)
                    {
                        if (!(def is IIfcSpace space))
                            continue;

                        var spaceInfo = MapSpace(space, storeyKey);
                        model.Spaces.Add(spaceInfo);
                    }
                }

                // ArchiCAD (and some IFC2x3 exports) nest IfcSpace under IfcBuildingStorey via IfcRelAggregates,
                // not IfcRelContainedInSpatialStructure — STEP has IFCRELAGGREGATES, not IFCRELCONTAINEDINSPATIALSTRUCTURE.
                var seenSpaceKeys = new HashSet<string>(model.Spaces.Select(s => s.Key), StringComparer.Ordinal);
                foreach (var rel in store.Instances.OfType<IIfcRelAggregates>())
                {
                    if (!(rel.RelatingObject is IIfcBuildingStorey storey))
                        continue;

                    var storeyKey = KeyFor(storey);

                    foreach (var def in rel.RelatedObjects ?? Enumerable.Empty<IIfcObjectDefinition>())
                    {
                        if (!(def is IIfcSpace space))
                            continue;

                        var spaceKey = KeyFor(space);
                        if (!seenSpaceKeys.Add(spaceKey))
                            continue;

                        model.Spaces.Add(MapSpace(space, storeyKey));
                    }
                }

                var contained = new HashSet<string>(model.Spaces.Select(s => s.Key), StringComparer.Ordinal);
                foreach (var space in store.Instances.OfType<IIfcSpace>())
                {
                    var key = KeyFor(space);
                    if (contained.Contains(key))
                        continue;

                    var storeyKey = FindStoreyKeyForSpace(store, space);
                    model.Spaces.Add(MapSpace(space, storeyKey));
                }

                EnrichSpaceBoundaries(store, model);
                EnrichFootprintLoops(store, model);
            }

            return model;
        }

        private const double BoundaryTolMetres = 0.002;

        /// <summary>
        /// When <see cref="EnrichSpaceBoundaries"/> finds nothing (e.g. ArchiCAD with &quot;IFC Space boundaries: Off&quot;),
        /// use <c>FootPrint</c> / <c>GeometricCurveSet</c> / <c>IfcPolyline</c> on <see cref="IIfcSpace"/> representation.
        /// </summary>
        private static void EnrichFootprintLoops(IfcStore store, IfcRoomModel model)
        {
            var byKey = model.Spaces.ToDictionary(s => s.Key, StringComparer.Ordinal);
            foreach (var space in store.Instances.OfType<IIfcSpace>())
            {
                var sk = KeyFor(space);
                if (!byKey.TryGetValue(sk, out var info))
                    continue;
                if (info.BoundaryLoops.Count > 0)
                    continue;
                if (!IfcFootprintBoundaryExtractor.TryGetFootprintLoopWorld2D(space, out var loop))
                    continue;
                if (loop.Vertices.Count < 3)
                {
                    model.LoadWarnings.Add($"Space {sk}: FootPrint polyline has fewer than 3 vertices after transform.");
                    continue;
                }

                info.BoundaryLoops.Add(loop);
            }
        }

        private static void EnrichSpaceBoundaries(IfcStore store, IfcRoomModel model)
        {
            var byKey = model.Spaces.ToDictionary(s => s.Key, StringComparer.Ordinal);
            var segmentsBySpace = new Dictionary<string, List<((double x, double y) a, (double x, double y) b)>>(StringComparer.Ordinal);

            foreach (var rsb in store.Instances.OfType<IIfcRelSpaceBoundary>())
            {
                if (!(rsb.RelatingSpace is IIfcSpace relating))
                    continue;
                var sk = KeyFor(relating);
                if (!byKey.TryGetValue(sk, out _))
                    continue;

                if (IsVirtualBoundary(rsb))
                    continue;

                if (!IfcCurveBoundaryExtractor.TryExtractPolyline2D(rsb, out var pts) || pts.Count < 2)
                {
                    model.LoadWarnings.Add($"Space {sk}: IfcRelSpaceBoundary #{rsb.EntityLabel} has no usable curve geometry.");
                    continue;
                }

                if (!segmentsBySpace.TryGetValue(sk, out var segList))
                {
                    segList = new List<((double x, double y) a, (double x, double y) b)>();
                    segmentsBySpace[sk] = segList;
                }

                if (pts.Count >= 3 &&
                    Dist2(pts[0], pts[pts.Count - 1]) <= BoundaryTolMetres * BoundaryTolMetres)
                {
                    var loop = new IfcBoundaryLoop2d();
                    for (var i = 0; i < pts.Count - 1; i++)
                        loop.Vertices.Add(new IfcVec2(pts[i].x, pts[i].y));
                    byKey[sk].BoundaryLoops.Add(loop);
                    continue;
                }

                for (var i = 0; i < pts.Count - 1; i++)
                    segList.Add((pts[i], pts[i + 1]));
            }

            foreach (var kv in segmentsBySpace)
            {
                if (kv.Value.Count == 0)
                    continue;
                var merged = IfcBoundarySegmentMerger.MergeSegmentsToClosedLoops(kv.Value);
                if (merged.Count == 0)
                {
                    model.LoadWarnings.Add($"Space {kv.Key}: could not merge {kv.Value.Count} boundary segments into a closed loop.");
                    continue;
                }

                foreach (var loopPts in merged)
                {
                    if (loopPts.Count < 3)
                        continue;
                    var loop = new IfcBoundaryLoop2d();
                    foreach (var p in loopPts)
                        loop.Vertices.Add(new IfcVec2(p.x, p.y));
                    byKey[kv.Key].BoundaryLoops.Add(loop);
                }
            }
        }

        private static bool IsVirtualBoundary(IIfcRelSpaceBoundary rsb)
        {
            try
            {
                return rsb.PhysicalOrVirtualBoundary == IfcPhysicalOrVirtualEnum.VIRTUAL;
            }
            catch
            {
                return false;
            }
        }

        private static double Dist2((double x, double y) a, (double x, double y) b)
        {
            var dx = a.x - b.x;
            var dy = a.y - b.y;
            return dx * dx + dy * dy;
        }

        private static string? FindStoreyKeyForSpace(IfcStore store, IIfcSpace space)
        {
            foreach (var rel in store.Instances.OfType<IIfcRelContainedInSpatialStructure>())
            {
                if (!(rel.RelatingStructure is IIfcBuildingStorey storey))
                    continue;
                foreach (var el in rel.RelatedElements)
                {
                    if (IsSameSpace(space, el))
                        return KeyFor(storey);
                }
            }

            foreach (var rel in store.Instances.OfType<IIfcRelAggregates>())
            {
                if (!(rel.RelatingObject is IIfcBuildingStorey storey))
                    continue;
                foreach (var el in rel.RelatedObjects ?? Enumerable.Empty<IIfcObjectDefinition>())
                {
                    if (IsSameSpace(space, el))
                        return KeyFor(storey);
                }
            }

            return NearestStoreyKeyByElevation(store, space);
        }

        /// <summary>Match space reference from a relationship (entity id or GlobalId).</summary>
        private static bool IsSameSpace(IIfcSpace space, IIfcObjectDefinition? el)
        {
            if (el is not IIfcSpace other)
                return false;
            if (space.EntityLabel == other.EntityLabel)
                return true;
            var a = space.GlobalId != null ? space.GlobalId.ToString() : null;
            var b = other.GlobalId != null ? other.GlobalId.ToString() : null;
            return !string.IsNullOrEmpty(a) && !string.IsNullOrEmpty(b) &&
                   string.Equals(a, b, StringComparison.Ordinal);
        }

        /// <summary>When spatial containment/aggregation is missing, pick the storey whose elevation is closest to the space placement Z.</summary>
        private static string? NearestStoreyKeyByElevation(IfcStore store, IIfcSpace space)
        {
            TryGetPlacementMetres(space.ObjectPlacement, out _, out _, out var z);
            var storeys = store.Instances.OfType<IIfcBuildingStorey>().ToList();
            if (storeys.Count == 0)
                return null;
            IIfcBuildingStorey? best = null;
            var bestDist = double.MaxValue;
            foreach (var st in storeys)
            {
                var elev = GetStoreyElevationMetres(st);
                var d = Math.Abs(elev - z);
                if (d < bestDist)
                {
                    bestDist = d;
                    best = st;
                }
            }

            return best == null ? null : KeyFor(best);
        }

        private static string KeyFor(IIfcRoot root) =>
            root.GlobalId != null ? root.GlobalId.ToString() : "#" + root.EntityLabel;

        private static IfcSpaceInfo MapSpace(IIfcSpace space, string? storeyKey)
        {
            TryGetPlacementMetres(space.ObjectPlacement, out var x, out var y, out var z);
            var number = GetPsetValue(space, "Pset_SpaceCommon", "Reference") ??
                         GetPsetValue(space, "Pset_SpaceCommon", "Name");

            var info = new IfcSpaceInfo
            {
                Key = KeyFor(space),
                Name = space.Name,
                LongName = space.LongName,
                Number = number,
                StoreyKey = storeyKey,
                XMetres = x,
                YMetres = y,
                ZMetres = z,
                BoundaryCount = space.BoundedBy?.Count() ?? 0
            };
            CollectPsetSpaceCommon(space, info);
            CollectAllPropertySets(space, info);
            return info;
        }

        /// <summary>All <see cref="IIfcPropertySet"/> properties (single value + enumerated) for Revit shared-parameter mapping.</summary>
        private static void CollectAllPropertySets(IIfcSpace space, IfcSpaceInfo info)
        {
            foreach (var relDef in space.IsDefinedBy ?? Enumerable.Empty<IIfcRelDefines>())
            {
                if (!(relDef is IIfcRelDefinesByProperties rdp))
                    continue;
                if (!(rdp.RelatingPropertyDefinition is IIfcPropertySet pset))
                    continue;

                var psetName = pset.Name != null
                    ? Convert.ToString(pset.Name.Value, CultureInfo.InvariantCulture)
                    : null;
                if (string.IsNullOrEmpty(psetName))
                    continue;

                foreach (var prop in pset.HasProperties ?? Enumerable.Empty<IIfcProperty>())
                {
                    if (prop.Name == null)
                        continue;
                    var propName = Convert.ToString(prop.Name.Value, CultureInfo.InvariantCulture);
                    if (string.IsNullOrEmpty(propName))
                        continue;

                    string? val = null;
                    if (prop is IIfcPropertySingleValue psv)
                        val = FormatNominal(psv.NominalValue);
                    else if (prop is IIfcPropertyEnumeratedValue pev)
                    {
                        var ev = pev.EnumerationValues;
                        if (ev != null)
                        {
                            var parts = new List<string>();
                            foreach (var v in ev)
                            {
                                var s = FormatNominal(v);
                                if (!string.IsNullOrEmpty(s))
                                    parts.Add(s);
                            }

                            if (parts.Count > 0)
                                val = string.Join(",", parts);
                        }
                    }

                    if (val == null)
                        continue;

                    info.SpaceProperties.Add(new IfcSpaceProperty
                    {
                        PsetName = psetName,
                        PropertyName = propName,
                        Value = val
                    });
                }
            }
        }

        private static void CollectPsetSpaceCommon(IIfcSpace space, IfcSpaceInfo info)
        {
            foreach (var relDef in space.IsDefinedBy ?? Enumerable.Empty<IIfcRelDefines>())
            {
                if (!(relDef is IIfcRelDefinesByProperties rdp))
                    continue;
                if (!(rdp.RelatingPropertyDefinition is IIfcPropertySet pset))
                    continue;
                if (pset.Name == null ||
                    !string.Equals(
                        Convert.ToString(pset.Name.Value, CultureInfo.InvariantCulture),
                        "Pset_SpaceCommon",
                        StringComparison.OrdinalIgnoreCase))
                    continue;

                foreach (var prop in pset.HasProperties ?? Enumerable.Empty<IIfcProperty>())
                {
                    if (!(prop is IIfcPropertySingleValue psv) || psv.Name == null)
                        continue;
                    var key = Convert.ToString(psv.Name.Value, CultureInfo.InvariantCulture);
                    if (string.IsNullOrEmpty(key))
                        continue;
                    var val = FormatNominal(psv.NominalValue);
                    if (val != null)
                        info.PsetSpaceCommon[key] = val;
                }
            }
        }

        private static string? GetPsetValue(IIfcSpace space, string psetName, string propName)
        {
            foreach (var relDef in space.IsDefinedBy ?? Enumerable.Empty<IIfcRelDefines>())
            {
                if (!(relDef is IIfcRelDefinesByProperties rdp))
                    continue;
                if (!(rdp.RelatingPropertyDefinition is IIfcPropertySet pset))
                    continue;
                if (pset.Name == null || !string.Equals(Convert.ToString(pset.Name.Value, CultureInfo.InvariantCulture), psetName, StringComparison.OrdinalIgnoreCase))
                    continue;
                foreach (var prop in pset.HasProperties ?? Enumerable.Empty<IIfcProperty>())
                {
                    if (!(prop is IIfcPropertySingleValue psv))
                        continue;
                    if (psv.Name == null || !string.Equals(Convert.ToString(psv.Name.Value, CultureInfo.InvariantCulture), propName, StringComparison.OrdinalIgnoreCase))
                        continue;
                    return FormatNominal(psv.NominalValue);
                }
            }

            return null;
        }

        private static string? FormatNominal(IIfcValue? v)
        {
            if (v == null) return null;
            var o = v.Value;
            return Convert.ToString(o, CultureInfo.InvariantCulture);
        }

        private static bool TryGetPlacementMetres(IIfcObjectPlacement? placement, out double x, out double y, out double z)
        {
            x = y = z = 0;
            if (placement is IIfcLocalPlacement lp)
            {
                if (lp.RelativePlacement is IIfcAxis2Placement3D ap3)
                {
                    if (ap3.Location is IIfcCartesianPoint cp && cp.Coordinates != null)
                    {
                        var coords = cp.Coordinates.ToList();
                        if (coords.Count >= 1) x = coords[0];
                        if (coords.Count >= 2) y = coords[1];
                        if (coords.Count >= 3) z = coords[2];
                        return true;
                    }
                }
            }

            return false;
        }

        /// <summary>Storey height for level creation: explicit Elevation, else local placement Z (IFC2x3 / ArchiCAD).</summary>
        private static double GetStoreyElevationMetres(IIfcBuildingStorey st)
        {
            if (st.Elevation != null)
                return st.Elevation.Value;
            if (TryGetPlacementMetres(st.ObjectPlacement, out _, out _, out var z))
                return z;
            return 0;
        }
    }
}
