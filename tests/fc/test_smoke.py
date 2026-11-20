# SPDX-License-Identifier: LGPL-2.1-or-later
"""Smoke test: FreeCAD and Part load, and the laserbench package imports inside FreeCAD."""

import unittest

import FreeCAD
import Part


class TestSmoke(unittest.TestCase):
    def test_freecad_version_is_supported(self) -> None:
        major, minor = (int(v) for v in FreeCAD.Version()[:2])
        self.assertGreaterEqual((major, minor), (1, 0))

    def test_part_box(self) -> None:
        doc = FreeCAD.newDocument("LBSmoke")
        try:
            box = doc.addObject("Part::Box", "Box")
            doc.recompute()
            self.assertAlmostEqual(box.Shape.Volume, 1000.0)
            self.assertIsInstance(box.Shape, Part.Shape)
        finally:
            FreeCAD.closeDocument(doc.Name)

    def test_laserbench_imports(self) -> None:
        import laserbench
        import laserbench.core.ir

        self.assertTrue(laserbench.__version__)
