"""
Explore ArchiCAD IFC2x3 IfcSpace footprint geometry: FootPrint + GeometricCurveSet + IfcPolyline.

Requires: pip install ifcopenshell

Usage:
  python inspect_space_footprint_ifcopenshell.py [path-to.ifc] [--limit N]
"""
from __future__ import annotations

import argparse
import sys

import ifcopenshell
import ifcopenshell.util.placement as placement_util


def iter_footprint_polylines(space):
    """Yield (rep_identifier, rep_type, polyline) for FootPrint curve-set geometry on an IfcSpace."""
    if not space.Representation:
        return
    pds = space.Representation
    if not pds.is_a("IfcProductDefinitionShape"):
        return
    for rep in pds.Representations or []:
        ident = (getattr(rep, "RepresentationIdentifier", None) or "").strip()
        rtype = (getattr(rep, "RepresentationType", None) or "").strip()
        if ident != "FootPrint" or rtype != "GeometricCurveSet":
            continue
        for item in rep.Items or []:
            if item.is_a("IfcGeometricCurveSet"):
                for crv in item.Elements or []:
                    if crv.is_a("IfcPolyline"):
                        yield ident, rtype, crv
            elif item.is_a("IfcPolyline"):
                yield ident, rtype, item


def polyline_points_xy(poly):
    """IfcPolyline points as (x,y) in metres (IFC length unit assumed metres)."""
    pts = []
    for p in poly.Points or []:
        c = p.Coordinates
        x = float(c[0]) if len(c) > 0 else 0.0
        y = float(c[1]) if len(c) > 1 else 0.0
        pts.append((x, y))
    return pts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "ifc",
        nargs="?",
        default=None,
        help="Path to IFC (default: demo/in/A1_2b_BIM_XXX_0003_00.ifc in this repo)",
    )
    ap.add_argument("--limit", type=int, default=5, help="How many spaces to detail")
    ap.add_argument("--global-id", dest="gid", default=None, help="Only this IfcSpace GlobalId")
    args = ap.parse_args()

    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(here, "..", ".."))
    path = args.ifc or os.path.join(repo_root, "demo", "in", "A1_2b_BIM_XXX_0003_00.ifc")
    if not os.path.isfile(path):
        print("File not found:", path, file=sys.stderr)
        return 1

    f = ifcopenshell.open(path)
    spaces = f.by_type("IfcSpace")
    rel_sb = len(f.by_type("IfcRelSpaceBoundary"))

    print("=== IFC summary ===")
    print("Schema / file:", f.schema)
    print("IfcSpace count:", len(spaces))
    print("IfcRelSpaceBoundary count:", rel_sb)
    print()

    detailed = 0
    with_footprint = 0
    for sp in spaces:
        if args.gid and sp.GlobalId != args.gid:
            continue
        fps = list(iter_footprint_polylines(sp))
        if fps:
            with_footprint += 1
        if detailed >= args.limit and not args.gid:
            continue
        if not fps:
            if args.gid:
                print(f"No FootPrint/GeometricCurveSet polyline for GlobalId={args.gid}")
                return 1
            continue

        detailed += 1
        m = placement_util.get_local_placement(sp.ObjectPlacement)
        # 4x4 matrix as list of tuples
        print(f"--- IfcSpace #{sp.id()} GlobalId={sp.GlobalId} Name={getattr(sp, 'Name', None)} ---")
        print(f"  FootPrint polylines: {len(fps)}")
        for ident, rtype, pl in fps[:3]:
            pts = polyline_points_xy(pl)
            print(f"  RepresentationIdentifier={ident!r} Type={rtype!r} IfcPolyline #{pl.id()} points={len(pts)}")
            preview = "; ".join(f"({x:.3f},{y:.3f})" for x, y in pts[:6])
            if len(pts) > 6:
                preview += f" … (+{len(pts)-6} more)"
            print(f"    first XY: {preview}")
        print(f"  ObjectPlacement 4x3 (row-major-ish): {m}")
        print()

    if not args.gid:
        print(f"Spaces with at least one FootPrint polyline: {with_footprint} / {len(spaces)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
