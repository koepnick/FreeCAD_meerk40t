# SPDX-License-Identifier: LGPL-2.1-or-later
"""G-02: projection modes flatten geometry into the job plane (FR-042, FR-043, FR-046).

Fixtures: a 40x30x10 box with a 10x10x4 pocket in the top, a 20 mm diameter cylinder with a
6 mm through hole, and a rectangle sketch rotated out of the XY plane.
"""

import math
import unittest

import FreeCAD
import Part

from laserbench.fc.extract import LBProjectionError, apply_offset, to_job_plane

V = FreeCAD.Vector
XY = FreeCAD.Placement()
TOL = 1e-4


def _pocket_box() -> Part.Shape:
    return Part.makeBox(40, 30, 10).cut(Part.makeBox(10, 10, 4, V(15, 10, 6)))


def _holed_cylinder() -> Part.Shape:
    return Part.makeCylinder(10, 5).cut(Part.makeCylinder(3, 5))


def _top_face(shape: Part.Shape) -> Part.Face:
    return max(shape.Faces, key=lambda f: (f.CenterOfMass.z, f.Area))


def _loops(wires):
    """(xmin, ymin, xmax, ymax) of each wire, rounded and sorted, largest first."""
    out = []
    for w in wires:
        bb = w.BoundBox
        out.append(tuple(round(v, 3) for v in (bb.XMin, bb.YMin, bb.XMax, bb.YMax)))
    return sorted(out, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))


class _Base(unittest.TestCase):
    def assertFlatClosed(self, wires) -> None:  # noqa: N802
        self.assertTrue(wires)
        for w in wires:
            self.assertTrue(w.isClosed(), "every loop must be closed")
            bb = w.BoundBox
            self.assertLess(max(abs(bb.ZMin), abs(bb.ZMax)), TOL, "wires must lie at z = 0")


class TestPocketBox(_Base):
    """FR-042: a box with a pocket gives the outer loop and the pocket loop in every mode."""

    EXPECTED = [(0, 0, 40, 30), (15, 10, 25, 20)]

    def test_face_mode(self) -> None:
        wires = to_job_plane(_top_face(_pocket_box()), "Face", XY)
        self.assertFlatClosed(wires)
        self.assertEqual(_loops(wires), self.EXPECTED)

    def test_direction_mode(self) -> None:
        wires = to_job_plane(_pocket_box(), "Direction", XY)
        self.assertFlatClosed(wires)
        self.assertEqual(_loops(wires), self.EXPECTED)

    def test_section_mode(self) -> None:
        wires = to_job_plane(_pocket_box(), "Section", XY, section_height=8)
        self.assertFlatClosed(wires)
        self.assertEqual(_loops(wires), self.EXPECTED)

    def test_section_below_pocket_has_only_outline(self) -> None:
        wires = to_job_plane(_pocket_box(), "Section", XY, section_height=3)
        self.assertEqual(_loops(wires), [(0, 0, 40, 30)])

    def test_face_mode_rejects_a_whole_solid(self) -> None:
        with self.assertRaises(LBProjectionError):
            to_job_plane(_pocket_box(), "Face", XY)

    def test_face_mode_rejects_curved_faces(self) -> None:
        side = next(f for f in _holed_cylinder().Faces if f.findPlane() is None)
        with self.assertRaises(LBProjectionError):
            to_job_plane(side, "Face", XY)

    def test_unknown_mode(self) -> None:
        with self.assertRaises(LBProjectionError):
            to_job_plane(_pocket_box(), "Shadow", XY)

    def test_job_plane_is_respected(self) -> None:
        """Geometry is expressed in the job plane's local XY."""
        plane = FreeCAD.Placement(V(100, 50, 0), FreeCAD.Rotation())
        wires = to_job_plane(_top_face(_pocket_box()), "Face", plane)
        self.assertEqual(_loops(wires), [(-100, -50, -60, -20), (-85, -40, -75, -30)])

    def test_side_view_direction(self) -> None:
        """Direction (0, -1, 0) is a front view: width x height of the box."""
        wires = to_job_plane(_pocket_box(), "Direction", XY, direction=V(0, -1, 0))
        self.assertFlatClosed(wires)
        bb = Part.Compound(wires).BoundBox
        self.assertAlmostEqual(bb.XLength, 40, delta=TOL)
        self.assertAlmostEqual(bb.YLength, 10, delta=TOL)


class TestHoledCylinder(_Base):
    """FR-042: a cylinder with a through hole gives two concentric circles in every mode."""

    def _check(self, wires) -> None:
        self.assertFlatClosed(wires)
        self.assertEqual(_loops(wires), [(-10, -10, 10, 10), (-3, -3, 3, 3)])

    def test_face_mode(self) -> None:
        self._check(to_job_plane(_top_face(_holed_cylinder()), "Face", XY))

    def test_direction_mode(self) -> None:
        self._check(to_job_plane(_holed_cylinder(), "Direction", XY))

    def test_section_mode(self) -> None:
        self._check(to_job_plane(_holed_cylinder(), "Section", XY, section_height=2.5))


class TestSketchPlanes(_Base):
    """FR-043: sketches are flattened from their own plane at true size."""

    def _rectangle(self, placement: FreeCAD.Placement) -> Part.Shape:
        wire = Part.makePolygon([V(0, 0, 0), V(20, 0, 0), V(20, 10, 0), V(0, 10, 0), V(0, 0, 0)])
        wire.Placement = placement
        return Part.Compound([wire])

    def test_rotated_sketch_is_flattened_at_true_size(self) -> None:
        tilted = FreeCAD.Placement(V(5, 0, 30), FreeCAD.Rotation(V(1, 0, 0), 90))  # XZ plane
        for mode in ("Face", "Direction", "Section"):
            with self.subTest(mode=mode):
                wires = to_job_plane(self._rectangle(tilted), mode, XY)
                self.assertFlatClosed(wires)
                bb = Part.Compound(wires).BoundBox
                self.assertAlmostEqual(bb.XLength, 20, delta=TOL)
                self.assertAlmostEqual(bb.YLength, 10, delta=TOL)
                self.assertAlmostEqual(bb.XMin, 5, delta=TOL)

    def test_sketch_parallel_to_plane_keeps_position(self) -> None:
        raised = FreeCAD.Placement(V(7, 8, 12), FreeCAD.Rotation(V(0, 0, 1), 90))
        [wire] = to_job_plane(self._rectangle(raised), "Face", XY)
        bb = wire.BoundBox
        rounded = tuple(round(v, 3) for v in (bb.XMin, bb.YMin, bb.XMax, bb.YMax))
        self.assertEqual(rounded, (-3, 8, 7, 28))

    def test_single_line_sketch_uses_its_placement(self) -> None:
        """A collinear sketch has no plane of its own; its Placement supplies one."""
        line = Part.Compound([Part.Wire([Part.makeLine(V(0, 0, 0), V(0, 10, 0))])])
        line.Placement = FreeCAD.Placement(V(), FreeCAD.Rotation(V(1, 0, 0), 90))
        [wire] = to_job_plane(line, "Face", XY)
        self.assertAlmostEqual(wire.Length, 10, delta=TOL)
        self.assertLess(abs(wire.BoundBox.ZMax), TOL)

    def test_non_planar_edges_rejected_outside_direction_mode(self) -> None:
        bent = Part.Compound([Part.makePolygon([V(0, 0, 0), V(10, 0, 0), V(10, 0, 10),
                                                V(10, 10, 10)])])
        with self.assertRaises(LBProjectionError):
            to_job_plane(bent, "Face", XY)
        wires = to_job_plane(bent, "Direction", XY)
        self.assertAlmostEqual(sum(w.Length for w in wires), 20, delta=TOL)


class TestApplyOffset(unittest.TestCase):
    """FR-046: only x, y and rotation about Z are applied."""

    def test_offset_moves_and_rotates_in_plane(self) -> None:
        square = Part.makePolygon([V(0, 0, 0), V(10, 0, 0), V(10, 10, 0), V(0, 10, 0),
                                   V(0, 0, 0)])
        offset = FreeCAD.Placement(V(100, 50, 25), FreeCAD.Rotation(90, 0, 30))  # yaw, pitch, roll
        [moved] = apply_offset([square], offset)
        bb = moved.BoundBox
        got = tuple(round(v, 6) for v in (bb.XMin, bb.YMin, bb.XMax, bb.YMax, bb.ZMin, bb.ZMax))
        self.assertEqual(got, (90, 50, 100, 60, 0, 0))
        self.assertEqual(square.BoundBox.XMin, 0, "input wires are not modified")

    def test_identity_offset(self) -> None:
        circle = Part.Wire([Part.makeCircle(5)])
        [same] = apply_offset([circle], FreeCAD.Placement())
        self.assertAlmostEqual(same.BoundBox.XMin, -5, delta=1e-9)
        self.assertTrue(math.isclose(same.Length, circle.Length))


if __name__ == "__main__":
    unittest.main()
