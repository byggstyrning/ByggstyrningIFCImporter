using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Byggstyrning.RoomImporter.Ifc;

namespace Byggstyrning.RoomImporter
{
    /// <summary>Creates Revit levels and rooms from an <see cref="IfcRoomModel"/>.</summary>
    public static class RevitRoomBuilder
    {
        private const double TolMetres = 0.002;

        public sealed class BuildResult
        {
            public int LevelsCreated { get; set; }
            public int RoomsCreated { get; set; }
            public int BoundaryLoopsApplied { get; set; }
            public List<string> Warnings { get; } = new List<string>();
        }

        public static BuildResult Build(Document doc, IfcRoomModel model)
        {
            var result = new BuildResult();
            if (model.Spaces.Count == 0)
            {
                result.Warnings.Add("No IfcSpace entities found in IFC.");
                return result;
            }

            foreach (var w in model.LoadWarnings)
                result.Warnings.Add(w);

            var existingLevels = new FilteredElementCollector(doc)
                .OfClass(typeof(Level))
                .Cast<Level>()
                .ToList();

            var storeyKeyToLevel = new Dictionary<string, Level>(StringComparer.Ordinal);

            foreach (var st in model.Storeys)
            {
                var elevInt = UnitUtils.ConvertToInternalUnits(st.ElevationMeters, UnitTypeId.Meters);
                var match = existingLevels.FirstOrDefault(
                    l => Math.Abs(l.Elevation - elevInt) < UnitUtils.ConvertToInternalUnits(TolMetres, UnitTypeId.Meters));
                if (match != null)
                {
                    storeyKeyToLevel[st.Key] = match;
                    continue;
                }

                var name = string.IsNullOrWhiteSpace(st.Name)
                    ? $"IFC Level {result.LevelsCreated + 1}"
                    : st.Name.Trim();
                match = existingLevels.FirstOrDefault(l => l.Name == name);
                if (match == null && !string.IsNullOrWhiteSpace(st.Name))
                    match = existingLevels.FirstOrDefault(l => l.Name == $"IFC {st.Name}");
                if (match != null)
                {
                    storeyKeyToLevel[st.Key] = match;
                    continue;
                }

                var level = Level.Create(doc, elevInt);
                try
                {
                    level.Name = name;
                }
                catch
                {
                    /* name conflict — keep default */
                }

                existingLevels.Add(level);
                storeyKeyToLevel[st.Key] = level;
                result.LevelsCreated++;
            }

            Level? defaultLevel = existingLevels.OrderBy(l => l.Elevation).FirstOrDefault();

            var floorPlanByLevel = new Dictionary<ElementId, ViewPlan?>();
            var warnedMissingFloorPlan = new HashSet<ElementId>();
            var canCreateFloorPlan = HasFloorPlanViewFamilyType(doc);
            if (!canCreateFloorPlan)
            {
                result.Warnings.Add(
                    "No ViewFamilyType with ViewFamily.FloorPlan in the document; cannot auto-create floor plan views for room boundaries.");
            }

            foreach (var lvl in storeyKeyToLevel.Values.GroupBy(l => l.Id).Select(g => g.First()))
            {
                GetOrCreateFloorPlanForLevel(
                    doc, lvl, result, floorPlanByLevel, warnedMissingFloorPlan, canCreateFloorPlan);
            }

            foreach (var sp in model.Spaces)
            {
                Level? level = null;
                if (sp.StoreyKey != null && storeyKeyToLevel.TryGetValue(sp.StoreyKey, out var lv))
                    level = lv;
                level ??= defaultLevel;
                if (level == null)
                {
                    result.Warnings.Add($"No level for space {sp.Key}; skipped.");
                    continue;
                }

                try
                {
                    Room? room = null;
                    if (TryCreateRoomWithBoundaryLoop(
                            doc, level, sp, result, floorPlanByLevel, warnedMissingFloorPlan, canCreateFloorPlan,
                            out var createdWithBoundary))
                    {
                        room = createdWithBoundary;
                    }

                    if (room == null)
                    {
                        var x = UnitUtils.ConvertToInternalUnits(sp.XMetres, UnitTypeId.Meters);
                        var y = UnitUtils.ConvertToInternalUnits(sp.YMetres, UnitTypeId.Meters);
                        if (Math.Abs(x) < 1e-9 && Math.Abs(y) < 1e-9)
                        {
                            x = y = 1.0;
                        }

                        if (sp.BoundaryLoops.Count > 0)
                            result.Warnings.Add($"Space {sp.Key}: using placement-only NewRoom (boundary loop failed or no floor plan).");

                        room = doc.Create.NewRoom(level, new UV(x, y));
                    }

                    if (room == null)
                    {
                        result.Warnings.Add($"Space {sp.Key}: NewRoom returned null.");
                        continue;
                    }

                    ApplyRoomIdentity(room, sp);
                    result.RoomsCreated++;
                }
                catch (Exception ex)
                {
                    result.Warnings.Add($"Space {sp.Key}: {ex.Message}");
                }
            }

            return result;
        }

        private static bool TryCreateRoomWithBoundaryLoop(
            Document doc,
            Level level,
            IfcSpaceInfo sp,
            BuildResult result,
            Dictionary<ElementId, ViewPlan?> floorPlanByLevel,
            HashSet<ElementId> warnedMissingFloorPlan,
            bool canCreateFloorPlan,
            out Room? room)
        {
            room = null;
            var loop = sp.BoundaryLoops.FirstOrDefault(l => l.Vertices.Count >= 3);
            if (loop == null)
                return false;

            var view = GetOrCreateFloorPlanForLevel(
                doc, level, result, floorPlanByLevel, warnedMissingFloorPlan, canCreateFloorPlan);
            if (view == null)
                return false;

            SketchPlane? sketch = null;
            try
            {
                sketch = SketchPlane.Create(doc, level.Id);
            }
            catch
            {
                try
                {
                    var pref = level.GetPlaneReference();
                    if (pref != null)
                        sketch = SketchPlane.Create(doc, pref);
                }
                catch
                {
                    /* ignore */
                }
            }

            if (sketch == null)
            {
                try
                {
                    var z = level.Elevation;
                    var plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, new XYZ(0, 0, z));
                    sketch = SketchPlane.Create(doc, plane);
                }
                catch
                {
                    result.Warnings.Add($"Space {sp.Key}: could not create SketchPlane for level {level.Name}.");
                    return false;
                }
            }

            var zLevel = level.Elevation;
            var ring = new List<XYZ>(loop.Vertices.Count);
            foreach (var v in loop.Vertices)
            {
                var xi = UnitUtils.ConvertToInternalUnits(v.X, UnitTypeId.Meters);
                var yi = UnitUtils.ConvertToInternalUnits(v.Y, UnitTypeId.Meters);
                ring.Add(new XYZ(xi, yi, zLevel));
            }

            var curves = new CurveArray();
            for (var i = 0; i < ring.Count; i++)
            {
                var a = ring[i];
                var b = ring[(i + 1) % ring.Count];
                curves.Append(Line.CreateBound(a, b));
            }

            ModelCurveArray? mca = null;
            try
            {
                mca = doc.Create.NewRoomBoundaryLines(sketch, curves, view);
            }
            catch (Exception ex)
            {
                result.Warnings.Add($"Space {sp.Key}: NewRoomBoundaryLines failed: {ex.Message}");
                return false;
            }

            var nlines = ModelCurveArrayCount(mca);
            if (mca == null || nlines < 1)
            {
                result.Warnings.Add($"Space {sp.Key}: NewRoomBoundaryLines produced no curves.");
                return false;
            }

            var uv = RoomInteriorUv.TryInteriorUv(ring);
            if (uv == null)
            {
                result.Warnings.Add($"Space {sp.Key}: could not compute interior UV for boundary loop.");
                return false;
            }

            try
            {
                room = doc.Create.NewRoom(level, uv);
            }
            catch (Exception ex)
            {
                result.Warnings.Add($"Space {sp.Key}: NewRoom after boundaries failed: {ex.Message}");
                return false;
            }

            if (room != null)
                result.BoundaryLoopsApplied++;
            return room != null;
        }

        private static int ModelCurveArrayCount(ModelCurveArray? mca)
        {
            if (mca == null)
                return 0;
            try
            {
                return mca.Size;
            }
            catch
            {
                return 0;
            }
        }

        /// <summary>Prefer an existing floor plan for the level; otherwise create one via <see cref="ViewPlan.Create"/>.</summary>
        private static bool HasFloorPlanViewFamilyType(Document doc)
        {
            foreach (var vft in new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType)).ToElements().Cast<ViewFamilyType>())
            {
                try
                {
                    if (vft.ViewFamily == ViewFamily.FloorPlan)
                        return true;
                }
                catch
                {
                    /* ignore */
                }
            }

            return false;
        }

        private static ViewPlan? GetOrCreateFloorPlanForLevel(
            Document doc,
            Level level,
            BuildResult result,
            Dictionary<ElementId, ViewPlan?> floorPlanByLevel,
            HashSet<ElementId> warnedMissingFloorPlan,
            bool canCreateFloorPlan)
        {
            if (floorPlanByLevel.TryGetValue(level.Id, out var cached))
                return cached;

            var existing = FindExistingFloorPlanForLevel(doc, level);
            if (existing != null)
            {
                floorPlanByLevel[level.Id] = existing;
                return existing;
            }

            if (!canCreateFloorPlan)
            {
                floorPlanByLevel[level.Id] = null;
                return null;
            }

            var created = CreateFloorPlanView(doc, level, result);
            floorPlanByLevel[level.Id] = created;
            if (created == null && warnedMissingFloorPlan.Add(level.Id))
            {
                result.Warnings.Add(
                    $"Cannot create a floor plan view for level {level.Name}; rooms on this level use placement-only NewRoom.");
            }

            return created;
        }

        private static ViewPlan? CreateFloorPlanView(Document doc, Level level, BuildResult result)
        {
            ViewFamilyType? floorPlanType = null;
            foreach (var vft in new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType)).ToElements().Cast<ViewFamilyType>())
            {
                try
                {
                    if (vft.ViewFamily == ViewFamily.FloorPlan)
                    {
                        floorPlanType = vft;
                        break;
                    }
                }
                catch
                {
                    /* ignore */
                }
            }

            if (floorPlanType == null)
                return null;

            try
            {
                var vp = ViewPlan.Create(doc, floorPlanType.Id, level.Id);
                try
                {
                    var baseName = FloorPlanViewDisplayName(level);
                    vp.Name = GetUniqueViewName(doc, baseName);
                }
                catch
                {
                    /* keep default generated name */
                }

                return vp;
            }
            catch (Exception ex)
            {
                result.Warnings.Add($"ViewPlan.Create failed for level {level.Name}: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Floor plan tab name: matches IFC building storey title (e.g. <c>010 Quay Level +1.90m</c>);
        /// strips legacy <c>IFC </c> prefix if the level was named that way in older imports.
        /// </summary>
        private static string FloorPlanViewDisplayName(Level level)
        {
            var n = level.Name ?? "";
            if (n.StartsWith("IFC ", StringComparison.Ordinal))
                return n.Substring(4).TrimStart();
            return n;
        }

        private static string GetUniqueViewName(Document doc, string baseName)
        {
            var used = new HashSet<string>(StringComparer.Ordinal);
            foreach (var v in new FilteredElementCollector(doc).OfClass(typeof(View)).ToElements())
            {
                try
                {
                    var n = v.Name;
                    if (!string.IsNullOrEmpty(n))
                        used.Add(n);
                }
                catch
                {
                    /* ignore */
                }
            }

            if (!used.Contains(baseName))
                return baseName;
            for (var i = 2; i < 10000; i++)
            {
                var candidate = $"{baseName} ({i})";
                if (!used.Contains(candidate))
                    return candidate;
            }

            return baseName + " " + Guid.NewGuid().ToString("N").Substring(0, 8);
        }

        private static ViewPlan? FindExistingFloorPlanForLevel(Document doc, Level level)
        {
            var candidates = new List<(int rank, ViewPlan vp)>();
            foreach (var vp in new FilteredElementCollector(doc).OfClass(typeof(ViewPlan)).ToElements().Cast<ViewPlan>())
            {
                try
                {
                    if (vp.GenLevel == null || vp.GenLevel.Id != level.Id)
                        continue;
                    if (vp.ViewType == ViewType.FloorPlan)
                        candidates.Add((0, vp));
                    else
                        candidates.Add((1, vp));
                }
                catch
                {
                    /* ignore */
                }
            }

            candidates.Sort((a, b) => a.rank.CompareTo(b.rank));
            if (candidates.Count > 0)
                return candidates[0].vp;

            foreach (var vp in new FilteredElementCollector(doc).OfClass(typeof(ViewPlan)).ToElements().Cast<ViewPlan>())
            {
                try
                {
                    if (vp.GenLevel != null && vp.GenLevel.Id == level.Id)
                        return vp;
                }
                catch
                {
                    /* ignore */
                }
            }

            return null;
        }

        private static void ApplyRoomIdentity(Room room, IfcSpaceInfo sp)
        {
            if (!string.IsNullOrWhiteSpace(sp.LongName))
                room.Name = sp.LongName!;
            else if (!string.IsNullOrWhiteSpace(sp.Name))
                room.Name = sp.Name!;

            if (!string.IsNullOrWhiteSpace(sp.Number))
            {
                var p = room.get_Parameter(BuiltInParameter.ROOM_NUMBER);
                if (p != null && !p.IsReadOnly)
                    p.Set(sp.Number);
            }

            RoomPropertyMapping.ApplyPsetSpaceCommon(room, sp);
            RoomPropertyMapping.ApplyIfcPropertySets(room, sp);
        }
    }
}
