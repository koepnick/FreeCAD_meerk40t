# SPDX-License-Identifier: LGPL-2.1-or-later
"""G-04: Part wires in the job plane convert to IR paths (FR-051).

Lines become line segments, circular arcs become arcs with the right ccw flag in the job
plane, and everything else becomes a polyline within the chord tolerance.
"""

import unittest

import FreeCAD
import Part

from laserbench.core.ir import IRPath, IRRegion
from laserbench.fc.to_ir import (
    edge_to_segment,
    wire_to_path,
    wires_to_paths,
    wires_to_regions,
)

V = FreeCAD.Vector
TOL = 1e-6


def _square(x0, y0, size):
    return Part.makePolygon([V(x0, y0, 0), V(x0 + size, y0, 0), V(x0 + size, y0 + size, 0),
                             V(x0, y0 + size, 0), V(x0, y0, 0)])


def _close(a, b, tol=TOL):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


class TestEdgeToSegment(unittest.TestCase):
    def test_line(self) -> None:
        seg = edge_to_segment(Part.makeLine(V(0, 0, 0), V(10, 5, 0)), (0, 0))
        self.assertEqual(seg.kind, "line")
        self.assertTrue(_close(seg.end, (10, 5)))

    def test_line_walked_backwards(self) -> None:
        seg = edge_to_segment(Part.makeLine(V(0, 0, 0), V(10, 5, 0)), (10, 5))
        self.assertTrue(_close(seg.end, (0, 0)))

    def test_ccw_arc(self) -> None:
        # Quarter arc from (10, 0) to (0, 10) around the origin, counter-clockwise.
        arc = Part.makeCircle(10, V(0, 0, 0), V(0, 0, 1), 0, 90)
        seg = edge_to_segment(arc, (10, 0))
        self.assertEqual(seg.kind, "arc")
        self.assertTrue(seg.ccw)
        self.assertTrue(_close(seg.center, (0, 0)))
        self.assertTrue(_close(seg.end, (0, 10)))

    def test_same_arc_walked_backwards_is_clockwise(self) -> None:
        arc = Part.makeCircle(10, V(0, 0, 0), V(0, 0, 1), 0, 90)
        seg = edge_to_segment(arc, (0, 10))
        self.assertFalse(seg.ccw)
        self.assertTrue(_close(seg.end, (10, 0)))

    def test_arc_with_downward_axis(self) -> None:
        """A circle whose axis points down runs clockwise in the job plane."""
        arc = Part.makeCircle(10, V(0, 0, 0), V(0, 0, -1), 0, 90)
        p0 = arc.valueAt(arc.FirstParameter)
        seg = edge_to_segment(arc, (p0.x, p0.y))
        self.assertFalse(seg.ccw)

    def test_full_circle(self) -> None:
        circle = Part.makeCircle(5, V(3, 4, 0))
        seg = edge_to_segment(circle, (8, 4))
        self.assertEqual(seg.kind, "arc")
        self.assertTrue(_close(seg.end, (8, 4)))
        self.assertTrue(_close(seg.center, (3, 4)))

    def test_ellipse_becomes_poly_within_tolerance(self) -> None:
        """FR-051: maximum deviation of the polyline from the true curve is within tolerance."""
        ellipse = Part.Ellipse(V(0, 0, 0), 30, 10).toShape()
        p0 = ellipse.valueAt(ellipse.FirstParameter)
        for tol in (0.1, 0.01):
            with self.subTest(tolerance=tol):
                seg = edge_to_segment(ellipse, (p0.x, p0.y), tol)
                self.assertEqual(seg.kind, "poly")
                pts = [(p0.x, p0.y), *seg.points, seg.end]
                worst = 0.0
                for a, b in zip(pts, pts[1:], strict=False):
                    for t in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
                        q = V(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 0)
                        worst = max(worst, ellipse.distToShape(Part.Vertex(q))[0])
                self.assertLessEqual(worst, tol)
                self.assertGreater(len(seg.points), 8)

    def test_bspline_becomes_poly(self) -> None:
        spline = Part.BSplineCurve()
        spline.interpolate([V(0, 0, 0), V(10, 5, 0), V(20, -5, 0), V(30, 0, 0)])
        seg = edge_to_segment(spline.toShape(), (0, 0))
        self.assertEqual(seg.kind, "poly")
        self.assertTrue(_close(seg.end, (30, 0)))


class TestWireToPath(unittest.TestCase):
    def test_closed_square(self) -> None:
        path = wire_to_path(_square(0, 0, 10))
        self.assertIsInstance(path, IRPath)
        self.assertTrue(path.closed)
        self.assertEqual([s.kind for s in path.segments], ["line"] * 4)
        self.assertEqual(path.end, path.start)

    def test_slot_mixes_lines_and_arcs(self) -> None:
        """A stadium slot: two lines and two half-circle arcs, chained end to end."""
        edges = [
            Part.makeLine(V(0, 0, 0), V(20, 0, 0)),
            Part.makeCircle(5, V(20, 5, 0), V(0, 0, 1), -90, 90),
            Part.makeLine(V(20, 10, 0), V(0, 10, 0)),
            Part.makeCircle(5, V(0, 5, 0), V(0, 0, 1), 90, 270),
        ]
        path = wire_to_path(Part.Wire(edges))
        self.assertTrue(path.closed)
        self.assertEqual(sorted(s.kind for s in path.segments), ["arc", "arc", "line", "line"])
        for seg_start, seg in path.iter_segments():
            self.assertFalse(_close(seg_start, seg.end), "no zero-length segments")
        arcs = [s for s in path.segments if s.kind == "arc"]
        self.assertEqual(len({a.ccw for a in arcs}), 1, "both ends turn the same way")

    def test_open_wire(self) -> None:
        wire = Part.makePolygon([V(0, 0, 0), V(5, 0, 0), V(5, 5, 0)])
        path = wire_to_path(wire)
        self.assertFalse(path.closed)
        self.assertTrue(_close(path.end, (5, 5)) or _close(path.end, (0, 0)))

    def test_circle_wire(self) -> None:
        path = wire_to_path(Part.Wire([Part.makeCircle(3)]))
        self.assertTrue(path.closed)
        self.assertEqual(len(path.segments), 1)
        self.assertEqual(path.segments[0].kind, "arc")

    def test_located_wire_uses_global_geometry(self) -> None:
        """Wires coming out of extract carry a Placement; the IR must use placed geometry."""
        wire = Part.Wire([Part.makeCircle(3)])
        wire.Placement = FreeCAD.Placement(V(10, 20, 0), FreeCAD.Rotation(V(1, 0, 0), 180))
        [seg] = wire_to_path(wire).segments
        self.assertTrue(_close(seg.center, (10, 20)))

    def test_wires_to_paths(self) -> None:
        paths = wires_to_paths([_square(0, 0, 10), _square(20, 0, 5)])
        self.assertEqual(len(paths), 2)


class TestWiresToRegions(unittest.TestCase):
    def test_outer_with_hole_and_island(self) -> None:
        """Depth parity: outer, hole, island-in-hole (new region), separate part."""
        wires = [_square(2, 2, 6), _square(0, 0, 10), _square(4, 4, 2), _square(20, 0, 5)]
        regions = wires_to_regions(wires)
        self.assertTrue(all(isinstance(r, IRRegion) for r in regions))
        summary = sorted((round(_area(r.outer)), [round(_area(h)) for h in r.holes])
                         for r in regions)
        self.assertEqual(summary, [(4, []), (25, []), (100, [36])])

    def test_open_wires_are_skipped(self) -> None:
        wires = [_square(0, 0, 10), Part.makePolygon([V(0, 0, 0), V(5, 5, 0)])]
        self.assertEqual(len(wires_to_regions(wires)), 1)


def _area(path: IRPath) -> float:
    """Shoelace area of a line-only path."""
    pts = [path.start] + [s.end for s in path.segments]
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:], strict=False))) / 2


if __name__ == "__main__":
    unittest.main()
