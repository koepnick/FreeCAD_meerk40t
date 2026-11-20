# SPDX-License-Identifier: LGPL-2.1-or-later
"""G-03: kerf compensation (FR-050, FR-064).

FR-050 acceptance: a 50 mm square with a 0.2 mm kerf in Auto mode gives a 50.2 mm path,
and a 10 mm hole gives a 9.8 mm path.
"""

import unittest

import FreeCAD
import Part

from laserbench.fc.kerf import compensate

V = FreeCAD.Vector
TOL = 1e-4


def _square(x0, y0, size):
    return Part.makePolygon([V(x0, y0, 0), V(x0 + size, y0, 0), V(x0 + size, y0 + size, 0),
                             V(x0, y0 + size, 0), V(x0, y0, 0)])


def _circle(cx, cy, diameter):
    return Part.Wire([Part.makeCircle(diameter / 2, V(cx, cy, 0))])


def _width(wire):
    return wire.BoundBox.XLength


class TestKerf(unittest.TestCase):
    def _plate(self):
        """50 mm square plate with a 10 mm hole in the middle (hole listed first)."""
        return [_circle(25, 25, 10), _square(0, 0, 50)]

    def test_auto_matches_fr050_acceptance(self) -> None:
        """FR-050: 50 mm square → 50.2 mm path; 10 mm hole → 9.8 mm path (kerf 0.2)."""
        (hole, outer), issues = compensate(self._plate(), 0.2, "Auto", "op1")
        self.assertEqual(issues, [])
        self.assertAlmostEqual(_width(outer), 50.2, delta=TOL)
        self.assertAlmostEqual(outer.BoundBox.XMin, -0.1, delta=TOL)
        self.assertAlmostEqual(_width(hole), 9.8, delta=TOL)
        self.assertTrue(outer.isClosed() and hole.isClosed())

    def test_island_inside_a_hole_grows(self) -> None:
        """Depth parity: an island (depth 2) is a part and is offset outward."""
        wires = [_square(0, 0, 50), _square(10, 10, 30), _square(20, 20, 10)]
        (outer, hole, island), _ = compensate(wires, 0.2, "Auto", "op1")
        self.assertAlmostEqual(_width(outer), 50.2, delta=TOL)
        self.assertAlmostEqual(_width(hole), 29.8, delta=TOL)
        self.assertAlmostEqual(_width(island), 10.2, delta=TOL)

    def test_outside_and_inside_ignore_nesting(self) -> None:
        (hole, outer), _ = compensate(self._plate(), 0.2, "Outside", "op1")
        self.assertAlmostEqual(_width(hole), 10.2, delta=TOL)
        self.assertAlmostEqual(_width(outer), 50.2, delta=TOL)
        (hole, outer), _ = compensate(self._plate(), 0.2, "Inside", "op1")
        self.assertAlmostEqual(_width(hole), 9.8, delta=TOL)
        self.assertAlmostEqual(_width(outer), 49.8, delta=TOL)

    def test_none_and_zero_kerf_pass_through(self) -> None:
        wires = self._plate()
        for kerf, mode in ((0.2, "None"), (0.0, "Auto")):
            with self.subTest(mode=mode, kerf=kerf):
                out, issues = compensate(wires, kerf, mode, "op1")
                self.assertEqual(issues, [])
                self.assertEqual([_width(w) for w in out], [_width(w) for w in wires])

    def test_open_wires_pass_through(self) -> None:
        line = Part.Wire([Part.makeLine(V(0, 0, 0), V(10, 0, 0))])
        out, issues = compensate([line, _square(20, 0, 5)], 0.2, "Auto", "op1")
        self.assertIs(out[0], line)
        self.assertAlmostEqual(_width(out[1]), 5.2, delta=TOL)
        self.assertEqual(issues, [])

    def test_collapsed_hole_reports_kerf_collapse(self) -> None:
        """FR-064: a hole narrower than the kerf vanishes and is reported, not crashed on."""
        wires = [_square(0, 0, 50), _circle(25, 25, 0.15)]
        out, issues = compensate(wires, 0.2, "Auto", "op7")
        self.assertEqual(len(out), 1)
        [issue] = issues
        self.assertEqual(issue.code, "KERF_COLLAPSE")
        self.assertEqual(issue.severity, "warning")
        self.assertEqual(issue.operation_id, "op7")
        self.assertAlmostEqual(issue.location[0], 25, delta=TOL)

    def test_several_tiny_round_holes_do_not_crash(self) -> None:
        """Regression: OCC segfaults offsetting a collapsing circle, and FreeCAD survives
        only the first such crash per process. Three in one call, twice over, must all be
        reported as KERF_COLLAPSE (circles never reach OCC's offset)."""
        wires = [_square(0, 0, 50), *(_circle(10 * i + 5, 25, 0.15) for i in range(3))]
        for _ in range(2):
            out, issues = compensate(wires, 0.2, "Auto", "op1")
            self.assertEqual(len(out), 1)
            self.assertEqual([i.code for i in issues], ["KERF_COLLAPSE"] * 3)

    def test_small_round_holes_shrink_without_crashing(self) -> None:
        """Regression: OCC also segfaults shrinking small circles that don't collapse
        (seen up to about 2 mm at 0.1 mm). They are offset analytically instead."""
        wires = [_square(0, 0, 50), *(_circle(10 * i + 5, 25, d)
                                      for i, d in enumerate((0.25, 1.0, 2.0)))]
        for _ in range(2):
            (_, *holes), issues = compensate(wires, 0.2, "Auto", "op1")
            self.assertEqual(issues, [])
            for hole, d in zip(holes, (0.25, 1.0, 2.0), strict=True):
                self.assertAlmostEqual(_width(hole), d - 0.2, delta=TOL)

    def test_hole_just_wider_than_kerf_survives(self) -> None:
        """Only loops that must collapse are dropped."""
        (_, hole), issues = compensate([_square(0, 0, 50), _circle(25, 25, 0.25)], 0.2,
                                       "Auto", "op1")
        self.assertEqual(issues, [])
        self.assertAlmostEqual(_width(hole), 0.05, delta=TOL)

    def test_diagonal_thin_slots_collapse_through_occ(self) -> None:
        """A 45° slot narrower than the kerf has a wide bounding box, so OCC decides."""
        def slot(x):
            r = 0.07
            edges = [Part.makeLine(V(0, -r, 0), V(5, -r, 0)),
                     Part.makeCircle(r, V(5, 0, 0), V(0, 0, 1), -90, 90),
                     Part.makeLine(V(5, r, 0), V(0, r, 0)),
                     Part.makeCircle(r, V(0, 0, 0), V(0, 0, 1), 90, 270)]
            wire = Part.Wire(edges)
            wire.rotate(V(0, 0, 0), V(0, 0, 1), 45)
            wire.translate(V(x, 10, 0))
            return wire

        wires = [_square(0, 0, 50), slot(10), slot(20), slot(30)]
        out, issues = compensate(wires, 0.2, "Auto", "op1")
        self.assertEqual(len(out), 1)
        self.assertEqual(len(issues), 3)

    def test_pinched_loop_splits(self) -> None:
        """An inward offset across a waist narrower than the kerf leaves two loops."""
        dumbbell = Part.makePolygon([
            V(0, 0, 0), V(10, 0, 0), V(10, 4.95, 0), V(20, 4.95, 0), V(20, 0, 0), V(30, 0, 0),
            V(30, 10, 0), V(20, 10, 0), V(20, 5.05, 0), V(10, 5.05, 0), V(10, 10, 0),
            V(0, 10, 0), V(0, 0, 0),
        ])
        out, issues = compensate([dumbbell], 0.2, "Inside", "op1")
        self.assertEqual(len(out), 2)
        self.assertEqual(issues, [])

    def test_rejects_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            compensate(self._plate(), 0.2, "Sideways", "op1")
        with self.assertRaises(ValueError):
            compensate(self._plate(), -0.2, "Auto", "op1")


if __name__ == "__main__":
    unittest.main()
