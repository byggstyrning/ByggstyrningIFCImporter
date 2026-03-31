using System.IO;
using System.Linq;
using System.Text.Json;
using NUnit.Framework;
using Byggstyrning.RoomImporter.Ifc;

namespace Byggstyrning.RoomImporter.Tests
{
    [TestFixture]
    public sealed class IfcRoomModelLoaderTests
    {
        private static string FixturePath =>
            Path.Combine(TestContext.CurrentContext.TestDirectory, "Fixtures", "minimal_spaces.ifc");

        private static string GoldenPath =>
            Path.Combine(TestContext.CurrentContext.TestDirectory, "Fixtures", "minimal_spaces.boundaries.golden.json");

        [Test]
        public void Minimal_fixture_file_exists()
        {
            Assert.That(File.Exists(FixturePath), Is.True, "minimal_spaces.ifc must exist beside tests");
        }

        /// <summary>
        /// Full xBIM load (IfcRelSpaceBoundary → merged loops). Uses <see cref="IfcXbimDependencies"/> and
        /// <c>ByggstyrningRoomImporter.Tests.runsettings</c> (NUnit ShadowCopy=false) for CLI reliability.
        /// </summary>
        [Test]
        public void Load_minimal_fixture_has_one_storey_one_space_and_boundary_loop()
        {
            Assert.That(File.Exists(FixturePath), Is.True, "minimal_spaces.ifc must exist beside tests");

            var model = IfcRoomModel.Load(FixturePath);
            Assert.That(model.Storeys.Count, Is.GreaterThanOrEqualTo(1));
            Assert.That(model.Spaces.Count, Is.EqualTo(1));
            var sp = model.Spaces[0];
            Assert.That(sp.BoundaryLoops.Count, Is.GreaterThanOrEqualTo(1));
            Assert.That(sp.BoundaryLoops[0].Vertices.Count, Is.GreaterThanOrEqualTo(3));

            Assert.That(File.Exists(GoldenPath), Is.True);
            var golden = JsonSerializer.Deserialize<GoldenBoundary>(File.ReadAllText(GoldenPath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

            Assert.That(golden, Is.Not.Null);
            Assert.That(sp.BoundaryLoops.Count, Is.EqualTo(golden!.BoundaryLoopCount));
            Assert.That(sp.BoundaryLoops[0].Vertices.Count, Is.EqualTo(golden.FirstLoopVertexCount));
            Assert.That(sp.SpaceProperties.Count, Is.GreaterThanOrEqualTo(sp.PsetSpaceCommon.Count));
        }

        private sealed class GoldenBoundary
        {
            public int BoundaryLoopCount { get; set; }
            public int FirstLoopVertexCount { get; set; }
        }

        /// <summary>Walks up from <see cref="TestContext.CurrentContext.TestDirectory"/> until <c>demo/A1_2b_BIM_XXX_0003_00.ifc</c> exists.</summary>
        private static string? TryFindDemo0003Ifc()
        {
            var dir = TestContext.CurrentContext.TestDirectory;
            for (var depth = 0; depth < 20; depth++)
            {
                var candidate = Path.Combine(dir, "demo", "A1_2b_BIM_XXX_0003_00.ifc");
                if (File.Exists(candidate))
                    return Path.GetFullPath(candidate);
                var parent = Directory.GetParent(dir);
                if (parent == null)
                    break;
                dir = parent.FullName;
            }

            return null;
        }

        /// <summary>Loads real project demo IFC when present under <c>demo/</c>; ignores if missing (CI without demo).</summary>
        [Test]
        public void Load_demo_rooms_ifc_when_present()
        {
            var demo = TryFindDemo0003Ifc();
            if (demo == null)
                Assert.Ignore("Demo rooms IFC not found (walk up from test dir for demo/A1_2b_BIM_XXX_0003_00.ifc).");

            var model = IfcRoomModel.Load(demo);
            Assert.That(model.Spaces.Count, Is.GreaterThan(0));
            var withLoops = model.Spaces.Count(s => s.BoundaryLoops.Count > 0);
            Assert.That(withLoops, Is.EqualTo(model.Spaces.Count),
                "ArchiCAD 0003 demo has FootPrint polylines (no IfcRelSpaceBoundary); every space should get a boundary loop.");

            var distinctStoreyKeys = model.Spaces.Select(s => s.StoreyKey).Where(k => k != null).Distinct().Count();
            Assert.That(distinctStoreyKeys, Is.GreaterThan(1),
                "ArchiCAD 0003 links spaces to storeys via IfcRelAggregates; spaces must not all map to one storey.");

            Assert.That(model.Storeys.Count, Is.EqualTo(6));
            Assert.That(model.Storeys.Select(s => s.ElevationMeters).Distinct().Count(), Is.EqualTo(6),
                "Each building storey needs a distinct elevation for Revit levels; if xBIM omits Elevation, placement Z must be used.");

            var sample = model.Spaces[0];
            Assert.That(sample.SpaceProperties.Count, Is.GreaterThanOrEqualTo(sample.PsetSpaceCommon.Count));
            Assert.That(
                model.Spaces.Any(s => s.SpaceProperties.Select(p => p.PsetName).Distinct().Count() > 1),
                Is.True,
                "Demo IFC should attach multiple property sets to at least one space (not only Pset_SpaceCommon).");
        }
    }
}
