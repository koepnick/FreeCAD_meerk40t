# SPDX-License-Identifier: LGPL-2.1-or-later
"""G-01: operation sources resolve to shapes in global coordinates (FR-041, FR-065).

One test per source kind (sketch, face, edge, solid, Body), plus the broken-link cases that
must raise LBSourceError naming the object and sub-element instead of a traceback.
"""

import unittest

import FreeCAD
import Part

from laserbench.fc.extract import LBSourceError, resolve_sources

V = FreeCAD.Vector
TOL = 1e-6


def _rectangle_sketch(doc, name, w=20.0, h=10.0):
    sketch = doc.addObject("Sketcher::SketchObject", name)
    pts = [V(0, 0, 0), V(w, 0, 0), V(w, h, 0), V(0, h, 0)]
    for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
        sketch.addGeometry(Part.LineSegment(a, b), False)
    return sketch


class TestResolveSources(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = FreeCAD.newDocument("LBSources")

    def tearDown(self) -> None:
        FreeCAD.closeDocument(self.doc.Name)

    def _box(self, name="Box", placement=None):
        box = self.doc.addObject("Part::Box", name)
        box.Length, box.Width, box.Height = 30, 20, 5
        if placement is not None:
            box.Placement = placement
        self.doc.recompute()
        return box

    def assertBoundsEqual(self, shape, expected) -> None:  # noqa: N802 (unittest style)
        bb = shape.BoundBox
        got = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
        for g, e in zip(got, expected, strict=True):
            self.assertAlmostEqual(g, e, delta=TOL, msg=f"bounds {got} != {expected}")

    def test_sketch_source(self) -> None:
        """FR-041: a whole sketch resolves to its wires, placed by its Placement."""
        sketch = _rectangle_sketch(self.doc, "Sketch")
        sketch.Placement = FreeCAD.Placement(V(5, 6, 7), FreeCAD.Rotation())
        self.doc.recompute()
        [(obj, sub, shape)] = resolve_sources([(sketch, [])])
        self.assertIs(obj, sketch)
        self.assertEqual(sub, "")
        self.assertEqual(len(shape.Edges), 4)
        self.assertBoundsEqual(shape, (5, 6, 7, 25, 16, 7))

    def test_face_source(self) -> None:
        """FR-041: a face sub-element resolves to that face, in global coordinates."""
        box = self._box(placement=FreeCAD.Placement(V(100, 0, 0), FreeCAD.Rotation()))
        [(_, sub, shape)] = resolve_sources([(box, ["Face6"])])
        self.assertEqual(sub, "Face6")
        self.assertEqual(shape.ShapeType, "Face")
        self.assertBoundsEqual(shape, (100, 0, 5, 130, 20, 5))  # Face6 is the top face

    def test_edge_sources(self) -> None:
        """FR-041: several edge sub-elements resolve one entry each, in order."""
        box = self._box()
        result = resolve_sources([(box, ["Edge1", "Edge2"])])
        self.assertEqual([sub for _, sub, _ in result], ["Edge1", "Edge2"])
        for _, _, shape in result:
            self.assertEqual(shape.ShapeType, "Edge")

    def test_solid_source(self) -> None:
        """FR-041: a whole solid resolves to the solid."""
        box = self._box()
        [(_, _, shape)] = resolve_sources([(box, [])])
        self.assertEqual(len(shape.Solids), 1)
        self.assertAlmostEqual(shape.Volume, 30 * 20 * 5, delta=TOL)

    def test_body_source_and_nested_sketch_placement(self) -> None:
        """FR-041: a Body resolves to its tip shape; container placement is applied."""
        body = self.doc.addObject("PartDesign::Body", "Body")
        body.Placement = FreeCAD.Placement(V(0, 50, 0), FreeCAD.Rotation())
        sketch = _rectangle_sketch(self.doc, "BodySketch")
        body.addObject(sketch)
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 3
        self.doc.recompute()

        [(_, _, body_shape)] = resolve_sources([(body, [])])
        self.assertAlmostEqual(body_shape.Volume, 20 * 10 * 3, delta=1e-3)
        self.assertBoundsEqual(body_shape, (0, 50, 0, 20, 60, 3))

        # The sketch inside the Body must pick up the Body's placement too.
        [(_, _, sketch_shape)] = resolve_sources([(sketch, [])])
        self.assertBoundsEqual(sketch_shape, (0, 50, 0, 20, 60, 0))

        # A face picked on the Pad feature is also global.
        top = max(pad.Shape.Faces, key=lambda f: f.CenterOfMass.z)
        name = f"Face{pad.Shape.Faces.index(top) + 1}"
        [(_, _, face)] = resolve_sources([(pad, [name])])
        self.assertBoundsEqual(face, (0, 50, 3, 20, 60, 3))

    def test_missing_sub_element_raises(self) -> None:
        """FR-065: a sub-element that no longer exists names the object and sub-element."""
        box = self._box()
        box.Label = "Plate"
        with self.assertRaises(LBSourceError) as ctx:
            resolve_sources([(box, ["Face99"])])
        self.assertEqual((ctx.exception.label, ctx.exception.subname), ("Plate", "Face99"))

    def test_toponaming_marked_sub_element_raises(self) -> None:
        """FR-065: FreeCAD's "?Face6" marker for a lost element is an error, not a fallback."""
        box = self._box()
        with self.assertRaises(LBSourceError) as ctx:
            resolve_sources([(box, ["?Face6"])])
        self.assertEqual(ctx.exception.subname, "Face6")

    def test_deleted_object_raises(self) -> None:
        """FR-065: a source whose object was deleted raises LBSourceError, not a traceback."""
        box = self._box()
        self.doc.removeObject(box.Name)
        with self.assertRaises(LBSourceError):
            resolve_sources([(box, [])])
        with self.assertRaises(LBSourceError):
            resolve_sources([(None, ["Face1"])])

    def test_result_is_a_copy(self) -> None:
        """Resolving must not move the source object's own shape."""
        sketch = _rectangle_sketch(self.doc, "Sketch")
        self.doc.recompute()
        before = sketch.Shape.BoundBox
        [(_, _, shape)] = resolve_sources([(sketch, [])])
        shape.translate(V(1000, 0, 0))
        self.assertAlmostEqual(sketch.Shape.BoundBox.XMin, before.XMin, delta=TOL)


if __name__ == "__main__":
    unittest.main()
