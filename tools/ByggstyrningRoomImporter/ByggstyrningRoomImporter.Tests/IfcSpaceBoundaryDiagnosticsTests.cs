using System.IO;
using System.Linq;
using NUnit.Framework;
using Byggstyrning.RoomImporter.Ifc;

namespace Byggstyrning.RoomImporter.Tests;

[TestFixture]
public sealed class IfcSpaceBoundaryDiagnosticsTests
{
    private static string FixturePath =>
        Path.Combine(TestContext.CurrentContext.TestDirectory, "Fixtures", "minimal_spaces.ifc");

    [Test]
    public void Summarize_minimal_fixture_has_four_rel_space_boundaries()
    {
        var s = IfcSpaceBoundaryDiagnostics.SummarizeFile(FixturePath);
        Assert.That(s.IfcRelSpaceBoundaryCount, Is.EqualTo(4));
        Assert.That(s.IfcSpaceCount, Is.GreaterThanOrEqualTo(1));
        Assert.That(s.ArchicadSpaceBoundariesExportOff, Is.False);
    }

    [Test]
    public void ListBoundaries_minimal_fixture_extracts_points_for_each_relation()
    {
        var rows = IfcSpaceBoundaryDiagnostics.ListBoundariesForSpace(FixturePath, null)
            .Where(r => r.EntityLabel > 0)
            .ToList();
        Assert.That(rows.Count, Is.EqualTo(4));
        Assert.That(rows.All(r => r.ExtractOk && r.PointCount >= 2), Is.True);
    }
}
