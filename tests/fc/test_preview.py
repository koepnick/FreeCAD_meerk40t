# SPDX-License-Identifier: LGPL-2.1-or-later
"""G-05: the preview built from IR matches the IR geometry and bounds (FR-034)."""

import unittest

import FreeCAD
import Part

from laserbench.core.ir import IROperation, IRPath, IRRegion, IRSegment
from laserbench.fc.preview import build_preview, operation_shape
from laserbench.fc.to_ir import wire_to_path

V = FreeCAD.Vector
TOL = 1e-3


def _op(op_id, paths=(), regions=(), op_type="cut"):
    return IROperation(id=op_id, label=op_id, type=op_type, order=0, colour="#ff0000",
                       paths=list(paths), regions=list(regions))


def _bounds(shape):
    bb = shape.BoundBox
    return tuple(round(v, 3) for v in (bb.XMin, bb.YMin, bb.XMax, bb.YMax))


class TestPreview(unittest.TestCase):
    def test_quarter_arc_bounds_follow_direction(self) -> None:
        """A ccw quarter arc from (10, 0) to (0, 10) stays in the first quadrant; the cw arc
        between the same points sweeps the other three quadrants."""
        ccw = IRPath(start=(10, 0), segments=[IRSegment.arc((0, 10), (0, 0), True)])
        cw = IRPath(start=(10, 0), segments=[IRSegment.arc((0, 10), (0, 0), False)])
        self.assertEqual(_bounds(operation_shape(_op("a", [ccw]), FreeCAD.Placement())),
                         (0, 0, 10, 10))
        self.assertEqual(_bounds(operation_shape(_op("b", [cw]), FreeCAD.Placement())),
                         (-10, -10, 10, 10))

    def test_full_circle_and_poly(self) -> None:
        circle = IRPath(start=(15, 5), segments=[IRSegment.arc((15, 5), (10, 5), True)],
                        closed=True)
        zigzag = IRPath(start=(0, 0), segments=[IRSegment.poly([(1, 2), (2, 0)], (3, 2))])
        shape = operation_shape(_op("c", [circle, zigzag]), FreeCAD.Placement())
        self.assertEqual(len(shape.Edges), 4)
        self.assertEqual(_bounds(shape), (0, 0, 15, 10))

    def test_round_trip_from_part_geometry(self) -> None:
        """Part wire → IR → preview reproduces the wire's length and bounds."""
        edges = [
            Part.makeLine(V(0, 0, 0), V(20, 0, 0)),
            Part.makeCircle(5, V(20, 5, 0), V(0, 0, 1), -90, 90),
            Part.makeLine(V(20, 10, 0), V(0, 10, 0)),
            Part.makeCircle(5, V(0, 5, 0), V(0, 0, 1), 90, 270),
        ]
        wire = Part.Wire(edges)
        shape = operation_shape(_op("slot", [wire_to_path(wire)]), FreeCAD.Placement())
        self.assertAlmostEqual(shape.Length, wire.Length, delta=TOL)
        self.assertEqual(_bounds(shape), _bounds(wire))

    def test_regions_are_drawn(self) -> None:
        outer = IRPath(start=(0, 0), segments=[IRSegment.line(p) for p in
                                               ((10, 0), (10, 10), (0, 10), (0, 0))],
                       closed=True)
        hole = IRPath(start=(6, 5), segments=[IRSegment.arc((6, 5), (5, 5), True)], closed=True)
        op = _op("fill", regions=[IRRegion(outer=outer, holes=[hole])], op_type="fill")
        self.assertEqual(len(operation_shape(op, FreeCAD.Placement()).Edges), 5)

    def test_job_plane_placement(self) -> None:
        """The preview sits on the job plane: job-frame (x, y) maps through its Placement."""
        line = IRPath(start=(0, 0), segments=[IRSegment.line((10, 0))])
        plane = FreeCAD.Placement(V(100, 0, 50), FreeCAD.Rotation(V(1, 0, 0), 90))
        bb = operation_shape(_op("l", [line]), plane).BoundBox
        self.assertAlmostEqual(bb.XMin, 100, delta=TOL)
        self.assertAlmostEqual(bb.XMax, 110, delta=TOL)
        self.assertAlmostEqual(bb.ZMin, 50, delta=TOL)

    def test_build_preview_combines_operations(self) -> None:
        a = IRPath(start=(0, 0), segments=[IRSegment.line((5, 0))])
        b = IRPath(start=(0, 20), segments=[IRSegment.line((5, 20))])
        preview = build_preview([_op("a", [a]), _op("b", [b])], FreeCAD.Placement())
        self.assertEqual(len(preview.Edges), 2)
        self.assertEqual(_bounds(preview), (0, 0, 5, 20))
        self.assertTrue(build_preview([], FreeCAD.Placement()).isNull() or
                        not build_preview([], FreeCAD.Placement()).Edges)


if __name__ == "__main__":
    unittest.main()
