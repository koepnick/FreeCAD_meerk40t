# SPDX-License-Identifier: LGPL-2.1-or-later
"""W-02: the LaserOperation object (FR-040, FR-044, FR-045, NFR-006).

LaserJob is W-03, so these tests put operations under a minimal stand-in job that has the
two properties an operation reads (JobPlane, Kerf) and an Operations list.
"""

import os
import subprocess
import sys
import tempfile
import unittest

import FreeCAD
import Part

from laserbench.objects import operation as op_mod
from laserbench.objects.operation import (
    LaserOperation,
    add_override_property,
    make_operation,
    read_fragment,
)

V = FreeCAD.Vector
TOL = 1e-3


class _StubJob:
    Type = op_mod.JOB_TYPE

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyPlacement", "JobPlane")
        obj.addProperty("App::PropertyLength", "Kerf")
        obj.addProperty("App::PropertyLinkList", "Operations")

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _rectangle_sketch(doc, name, x0=0.0, y0=0.0, w=20.0, h=10.0):
    sketch = doc.addObject("Sketcher::SketchObject", name)
    pts = [V(x0, y0, 0), V(x0 + w, y0, 0), V(x0 + w, y0 + h, 0), V(x0, y0 + h, 0)]
    for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
        sketch.addGeometry(Part.LineSegment(a, b), False)
    return sketch


def _path_bounds(paths):
    xs, ys = [], []
    for p in paths:
        pts = [p.start] + [s.end for s in p.segments]
        xs += [q[0] for q in pts]
        ys += [q[1] for q in pts]
    return min(xs), min(ys), max(xs), max(ys)


class TestLaserOperation(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = FreeCAD.newDocument("LBOperation")
        self.job = self.doc.addObject("Part::FeaturePython", "Job")
        _StubJob(self.job)

    def tearDown(self) -> None:
        FreeCAD.closeDocument(self.doc.Name)

    def _op(self, op_type, sources, **props):
        obj = make_operation(self.doc, op_type, sources)
        for k, v in props.items():
            setattr(obj, k, v)
        self.job.Operations = self.job.Operations + [obj]
        self.doc.recompute()
        return obj

    # --- properties -------------------------------------------------------

    def test_properties_follow_architecture(self) -> None:
        """ARCHITECTURE §4.1: every listed property exists, with usable defaults."""
        obj = self._op("cut", [])
        expected = {
            "OpType": "App::PropertyEnumeration", "Sources": "App::PropertyLinkSubList",
            "ProjectionMode": "App::PropertyEnumeration",
            "ProjectionDirection": "App::PropertyVector",
            "SectionHeight": "App::PropertyDistance", "KerfMode": "App::PropertyEnumeration",
            "Offset": "App::PropertyPlacement", "ArrayCount": "App::PropertyIntegerList",
            "ArraySpacing": "App::PropertyVector", "Enabled": "App::PropertyBool",
            "Order": "App::PropertyInteger", "Colour": "App::PropertyColor",
            "SettingsOverrides": "App::PropertyMap", "IRFragment": "App::PropertyString",
        }
        for name, type_id in expected.items():
            with self.subTest(property=name):
                self.assertEqual(obj.getTypeIdOfProperty(name), type_id)
        self.assertEqual(obj.getEnumerationsOfProperty("OpType"), ["Cut", "Score", "Fill"])
        self.assertEqual(obj.getEnumerationsOfProperty("KerfMode"),
                         ["Auto", "Outside", "Inside", "None"])
        self.assertEqual(obj.OpType, "Cut")
        self.assertTrue(obj.Enabled)
        self.assertEqual(obj.ArrayCount, [1, 1])
        self.assertIn("Transient", obj.getTypeOfProperty("IRFragment"))
        self.assertEqual(obj.getEditorMode("IRFragment"), ["Hidden"])

    def test_colour_and_order_are_auto_assigned(self) -> None:
        """FR-045: each new operation takes the next palette colour and the next order."""
        ops = [self._op(t, []) for t in ("Cut", "Score", "Fill")]
        self.assertEqual([o.Order for o in ops], [0, 1, 2])
        colours = [op_mod.colour_hex(o.Colour) for o in ops]
        self.assertEqual(colours, list(op_mod.PALETTE[:3]))
        ops[1].Colour = (0.0, 0.5, 0.0)  # user-overridable
        self.doc.recompute()
        self.assertEqual(read_fragment(ops[1])[0].colour, "#008000")

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_operation(self.doc, "Raster", [])

    # --- geometry pipeline ------------------------------------------------

    def test_cut_applies_job_kerf(self) -> None:
        """FR-040/FR-050: a Cut of a 20×10 sketch with 0.2 mm kerf gives a 20.2×10.2 path."""
        self.job.Kerf = 0.2
        sketch = _rectangle_sketch(self.doc, "Sketch")
        obj = self._op("Cut", [(sketch, [])])
        frag, issues = read_fragment(obj)
        self.assertEqual(issues, [])
        self.assertEqual((frag.id, frag.type, frag.kerf_mode), (obj.Name, "cut", "auto"))
        self.assertEqual(len(frag.paths), 1)
        self.assertTrue(frag.paths[0].closed)
        x0, y0, x1, y1 = _path_bounds(frag.paths)
        self.assertAlmostEqual(x1 - x0, 20.2, delta=TOL)
        self.assertAlmostEqual(y1 - y0, 10.2, delta=TOL)
        self.assertAlmostEqual(obj.Shape.BoundBox.XLength, 20.2, delta=TOL)

    def test_score_ignores_kerf(self) -> None:
        """Kerf compensation is for Cut only; Score follows the lines as drawn."""
        self.job.Kerf = 0.2
        sketch = _rectangle_sketch(self.doc, "Sketch")
        obj = self._op("Score", [(sketch, [])], KerfMode="Outside")
        frag, _ = read_fragment(obj)
        self.assertEqual((frag.type, frag.kerf_mode), ("score", "none"))
        x0, _, x1, _ = _path_bounds(frag.paths)
        self.assertAlmostEqual(x1 - x0, 20.0, delta=TOL)

    def test_fill_produces_regions_with_holes(self) -> None:
        """FR-040: a Fill of a face with a hole is one region with one hole, no paths."""
        outer = Part.Face(Part.makePolygon([V(0, 0, 0), V(40, 0, 0), V(40, 30, 0),
                                            V(0, 30, 0), V(0, 0, 0)]))
        hole = Part.Face(Part.Wire([Part.makeCircle(5, V(20, 15, 0))]))
        feature = self.doc.addObject("Part::Feature", "Plate")
        feature.Shape = outer.cut(hole)
        obj = self._op("Fill", [(feature, ["Face1"])], ProjectionMode="Face")
        frag, issues = read_fragment(obj)
        self.assertEqual(issues, [])
        self.assertEqual(frag.paths, [])
        self.assertEqual(len(frag.regions), 1)
        self.assertEqual(len(frag.regions[0].holes), 1)

    def test_job_plane_and_offset(self) -> None:
        """Geometry lands in the job frame, then the operation's Offset moves it (FR-046)."""
        self.job.JobPlane = FreeCAD.Placement(V(100, 0, 0), FreeCAD.Rotation())
        sketch = _rectangle_sketch(self.doc, "Sketch", x0=110, y0=5)
        obj = self._op("Score", [(sketch, [])],
                       Offset=FreeCAD.Placement(V(3, 4, 9), FreeCAD.Rotation()))
        x0, y0, _, _ = _path_bounds(read_fragment(obj)[0].paths)
        self.assertAlmostEqual(x0, 13, delta=TOL)
        self.assertAlmostEqual(y0, 9, delta=TOL)
        # The preview sits back on the job plane in global coordinates.
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, 113, delta=TOL)

    def test_array_repeats_geometry(self) -> None:
        """FR-047 / D-004: a 3×2 array expands to six paths in the IR."""
        sketch = _rectangle_sketch(self.doc, "Sketch")
        obj = self._op("Cut", [(sketch, [])], ArrayCount=[3, 2], ArraySpacing=V(25, 15, 0))
        frag, _ = read_fragment(obj)
        self.assertEqual(len(frag.paths), 6)
        self.assertEqual(_path_bounds(frag.paths), (0, 0, 70, 25))

    def test_recomputes_when_the_source_changes(self) -> None:
        """The parametric promise: editing the source changes the operation's IR."""
        box = self.doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 20, 10, 3
        obj = self._op("Score", [(box, [])], ProjectionMode="Direction")
        _, _, x1, _ = _path_bounds(read_fragment(obj)[0].paths)
        self.assertAlmostEqual(x1, 20, delta=TOL)
        box.Length = 30
        self.doc.recompute()
        _, _, x1, _ = _path_bounds(read_fragment(obj)[0].paths)
        self.assertAlmostEqual(x1, 30, delta=TOL)

    # --- settings overrides (FR-044, D-007) -------------------------------

    def test_overrides_map_and_expression_property(self) -> None:
        """Map values pass through as strings; a D-007 float property wins and follows an
        expression."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "42")
        sheet.setAlias("A1", "pwr")
        obj = self._op("Cut", [], SettingsOverrides={"speed": "20", "power": "10",
                                                     "air": "true"})
        self.assertEqual(read_fragment(obj)[0].settings,
                         {"air": "true", "power": "10", "speed": "20"})
        name = add_override_property(obj, "power")
        self.assertEqual((name, obj.Power), ("Power", 10.0))
        obj.setExpression("Power", "Spreadsheet.pwr")
        self.doc.recompute()
        self.assertEqual(read_fragment(obj)[0].settings["power"], 42.0)
        sheet.set("A1", "55")
        self.doc.recompute()
        self.assertEqual(read_fragment(obj)[0].settings["power"], 55.0)
        with self.assertRaises(ValueError):
            add_override_property(obj, "air")

    # --- error handling (FR-064, FR-065, D-009) ---------------------------

    def test_one_broken_source_is_an_issue_not_a_failure(self) -> None:
        sketch = _rectangle_sketch(self.doc, "Sketch")
        box = self.doc.addObject("Part::Box", "Box")
        obj = self._op("Cut", [(sketch, []), (box, ["Face99"])], ProjectionMode="Face")
        self.assertTrue(obj.isValid())
        frag, issues = read_fragment(obj)
        self.assertEqual(len(frag.paths), 1)
        self.assertEqual([i.code for i in issues], ["BROKEN_SOURCE"])
        self.assertIn("Box.Face99", issues[0].message)
        self.assertEqual(issues[0].operation_id, obj.Name)

    def test_all_sources_broken_marks_the_object(self) -> None:
        """D-009: a hard failure raises so the tree shows the error; the issue is kept."""
        box = self.doc.addObject("Part::Box", "Box")
        obj = self._op("Cut", [(box, ["Face99"])], ProjectionMode="Face")
        self.assertFalse(obj.isValid())
        frag, issues = read_fragment(obj)
        self.assertEqual(frag.paths, [])
        self.assertEqual([i.code for i in issues], ["BROKEN_SOURCE"])

    def test_unprojectable_source_is_a_geometry_error(self) -> None:
        box = self.doc.addObject("Part::Box", "Box")
        sketch = _rectangle_sketch(self.doc, "Sketch")
        obj = self._op("Cut", [(box, []), (sketch, [])], ProjectionMode="Face")
        frag, issues = read_fragment(obj)
        self.assertEqual([i.code for i in issues], ["GEOMETRY_ERROR"])
        self.assertEqual(len(frag.paths), 1)

    def test_kerf_collapse_is_reported(self) -> None:
        self.job.Kerf = 2.0
        plate = Part.makePolygon([V(0, 0, 0), V(40, 0, 0), V(40, 40, 0), V(0, 40, 0),
                                  V(0, 0, 0)])
        # A square, not a circle: OCC survives only one crash per process on a collapsing
        # circle offset, and test_kerf already spends it.
        tiny = Part.makePolygon([V(20, 20, 0), V(21, 20, 0), V(21, 21, 0), V(20, 21, 0),
                                 V(20, 20, 0)])
        feature = self.doc.addObject("Part::Feature", "Wires")
        feature.Shape = Part.Compound([plate, tiny])
        obj = self._op("Cut", [(feature, [])])
        frag, issues = read_fragment(obj)
        self.assertEqual([i.code for i in issues], ["KERF_COLLAPSE"])
        self.assertEqual(len(frag.paths), 1)

    def test_operation_without_a_job_uses_xy_and_no_kerf(self) -> None:
        sketch = _rectangle_sketch(self.doc, "Sketch")
        obj = make_operation(self.doc, "Cut", [(sketch, [])])
        self.doc.recompute()
        x0, _, x1, _ = _path_bounds(read_fragment(obj)[0].paths)
        self.assertAlmostEqual(x1 - x0, 20.0, delta=TOL)

    # --- save / restore (D-008, NFR-006) ----------------------------------

    def test_save_restore_recomputes_the_transient_fragment(self) -> None:
        sketch = _rectangle_sketch(self.doc, "Sketch")
        obj = self._op("Cut", [(sketch, [])], SettingsOverrides={"speed": "20"})
        add_override_property(obj, "power", 30.0)
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "op.FCStd")
            self.doc.saveAs(path)
            name = obj.Name
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)  # tearDown closes it
            op = self.doc.getObject(name)
            self.assertIsInstance(op.Proxy, LaserOperation)
            self.assertEqual(op.IRFragment, "")  # transient: not saved
            frag, _ = read_fragment(op)  # recomputes on demand
            self.assertEqual(frag.settings, {"power": 30.0, "speed": "20"})
            self.assertEqual(len(frag.paths), 1)

    def test_document_opens_without_the_workbench(self) -> None:
        """NFR-006: a saved operation opens in a FreeCAD that cannot import laserbench."""
        sketch = _rectangle_sketch(self.doc, "Sketch")
        self._op("Cut", [(sketch, [])])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "op.FCStd")
            self.doc.saveAs(path)
            script = os.path.join(tmp, "open.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(_OPEN_WITHOUT_WORKBENCH.format(path=path))
            result = subprocess.run([_freecadcmd(), script], capture_output=True, text=True,
                                    timeout=120, cwd=tmp)
        self.assertNotIn("LASERBENCH IMPORTABLE", result.stdout)
        self.assertIn("OPENED 1", result.stdout, result.stdout + result.stderr)


_OPEN_WITHOUT_WORKBENCH = """
import os, sys
sys.path = [p for p in sys.path if not os.path.isdir(os.path.join(p, "laserbench"))]
sys.modules.pop("laserbench", None)
import FreeCAD
try:
    import laserbench  # noqa: F401
    print("LASERBENCH IMPORTABLE")
except ImportError:
    pass
doc = FreeCAD.openDocument({path!r})
ops = [o for o in doc.Objects if o.Name.startswith("LaserOperation")]
print("OPENED", len(ops), flush=True)
os._exit(0)
"""


def _freecadcmd() -> str:
    home = FreeCAD.getHomePath()
    for name in ("freecadcmd", "FreeCADCmd", "freecadcmd.exe", "FreeCADCmd.exe"):
        candidate = os.path.join(home, "bin", name)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(os.path.dirname(sys.executable), "freecadcmd")
