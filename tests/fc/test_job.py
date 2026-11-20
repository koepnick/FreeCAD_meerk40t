# SPDX-License-Identifier: LGPL-2.1-or-later
"""W-03: the LaserJob object (FR-030 to FR-033, FR-045, D-008, D-009).

Profiles come from an in-memory resolver so the tests never touch the user's data folder.
"""

import os
import tempfile
import unittest

import FreeCAD
import Part

from laserbench.core.presets import MachineProfile, MaterialPreset
from laserbench.objects import job as job_mod
from laserbench.objects.job import add_operation, get_ir, make_job
from laserbench.objects.operation import make_operation

V = FreeCAD.Vector
TOL = 1e-3

CO2 = MachineProfile(id="co2", name="CO2", kind="gantry", width=600, height=400,
                     origin="rear-left", default_kerf=0.2)
PLY = MaterialPreset(id="ply3", machine_id="co2", name="Ply 3 mm", thickness=3.0, kerf=0.2,
                     settings={"cut": {"power": 65, "speed": 20}, "score": {"power": 20}})


def _resolver(machine_id, material_id):
    if (machine_id, material_id) != ("co2", "ply3"):
        raise KeyError(f"no material preset {material_id!r} for machine {machine_id!r}")
    return CO2, PLY


def _rectangle_sketch(doc, name, x0=0.0, y0=0.0, w=20.0, h=10.0):
    sketch = doc.addObject("Sketcher::SketchObject", name)
    pts = [V(x0, y0, 0), V(x0 + w, y0, 0), V(x0 + w, y0 + h, 0), V(x0, y0 + h, 0)]
    for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
        sketch.addGeometry(Part.LineSegment(a, b), False)
    return sketch


def _bounds(op):
    xs, ys = [], []
    for p in op.paths:
        for q in [p.start] + [s.end for s in p.segments]:
            xs.append(q[0])
            ys.append(q[1])
    return min(xs), min(ys), max(xs), max(ys)


class TestLaserJob(unittest.TestCase):
    def setUp(self) -> None:
        job_mod.set_preset_resolver(_resolver)
        self.doc = FreeCAD.newDocument("LBJob")
        self.job = make_job(self.doc, "co2", "ply3")

    def tearDown(self) -> None:
        FreeCAD.closeDocument(self.doc.Name)
        job_mod.set_preset_resolver(None)

    def _op(self, op_type, sources, **props):
        op = make_operation(self.doc, op_type, sources)
        for k, v in props.items():
            setattr(op, k, v)
        add_operation(self.job, op)
        return op

    def _touched(self):
        return [o.Name for o in self.doc.Objects if "Touched" in o.State]

    # --- object -----------------------------------------------------------

    def test_properties_and_preset_defaults(self) -> None:
        """FR-030: the job links a machine and material; thickness and kerf start from it."""
        expected = {
            "MachineProfile": "App::PropertyString", "MaterialPreset": "App::PropertyString",
            "Thickness": "App::PropertyLength", "Kerf": "App::PropertyLength",
            "JobPlane": "App::PropertyPlacement", "Operations": "App::PropertyLinkList",
            "OutputDir": "App::PropertyPath", "ExportFormats": "App::PropertyStringList",
            "IRCache": "App::PropertyString", "ValidationSummary": "App::PropertyStringList",
        }
        for name, type_id in expected.items():
            with self.subTest(property=name):
                self.assertEqual(self.job.getTypeIdOfProperty(name), type_id)
        self.assertEqual((self.job.MachineProfile, self.job.MaterialPreset), ("co2", "ply3"))
        self.assertAlmostEqual(self.job.Thickness.Value, 3.0)
        self.assertAlmostEqual(self.job.Kerf.Value, 0.2)
        self.assertEqual(self.job.ExportFormats, ["svg", "json"])
        self.assertIn("Transient", self.job.getTypeOfProperty("IRCache"))
        self.assertEqual(self.job.getEditorMode("IRCache"), ["Hidden"])

    def test_job_ir_end_to_end(self) -> None:
        """Operations → fragments → kerf, merge, transform, validate → stored IR."""
        sketch = _rectangle_sketch(self.doc, "Sketch", 10, 20)
        self._op("Cut", [(sketch, [])], SettingsOverrides={"power": "70"})
        self.doc.recompute()
        ir = get_ir(self.job)
        self.assertEqual((ir.machine.id, ir.machine.origin), ("co2", "rear-left"))
        self.assertEqual((ir.material.id, ir.material.kerf, ir.material.thickness),
                         ("ply3", 0.2, 3.0))
        [cut] = ir.operations
        self.assertEqual(cut.settings, {"kerf": 0.2, "power": 70, "speed": 20})
        x0, y0, x1, y1 = _bounds(cut)
        self.assertAlmostEqual(x1 - x0, 20.2, delta=TOL)  # Auto kerf grew the outline
        # rear-left origin: job y 19.9 … 30.1 lands at 400 - y in the machine frame.
        self.assertAlmostEqual(y0, 400 - 30.1, delta=TOL)
        self.assertAlmostEqual(y1, 400 - 19.9, delta=TOL)
        self.assertEqual(self.job.ValidationSummary, [])
        self.assertAlmostEqual(self.job.Shape.BoundBox.XLength, 20.2, delta=TOL)
        self.assertEqual(self._touched(), [])

    def test_disabled_operation_is_absent(self) -> None:
        """FR-045 acceptance: a disabled operation is absent from the export."""
        a = self._op("Cut", [(_rectangle_sketch(self.doc, "A"), [])])
        b = self._op("Score", [(_rectangle_sketch(self.doc, "B", 50), [])])
        self.doc.recompute()
        self.assertEqual([o.id for o in get_ir(self.job).operations], [a.Name, b.Name])
        b.Enabled = False
        self.doc.recompute()
        self.assertEqual([o.id for o in get_ir(self.job).operations], [a.Name])

    def test_order_property_decides_the_operation_order(self) -> None:
        a = self._op("Cut", [(_rectangle_sketch(self.doc, "A"), [])])
        b = self._op("Score", [(_rectangle_sketch(self.doc, "B", 50), [])])
        a.Order, b.Order = 5, 1
        self.doc.recompute()
        self.assertEqual([o.id for o in get_ir(self.job).operations], [b.Name, a.Name])

    # --- recompute (FR-031, FR-033) ---------------------------------------

    def test_recomputes_when_source_geometry_changes(self) -> None:
        """FR-033: edit the model → job touched → recompute → updated output."""
        box = self.doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 20, 10, 3
        self._op("Score", [(box, [])], ProjectionMode="Direction")
        self.doc.recompute()
        box.Length = 35
        self.doc.recompute()
        x0, _, x1, _ = _bounds(get_ir(self.job).operations[0])
        self.assertAlmostEqual(x1 - x0, 35, delta=TOL)
        self.assertEqual(self._touched(), [])

    def test_kerf_follows_a_spreadsheet_in_one_recompute(self) -> None:
        """FR-031: Kerf = Spreadsheet.kerf; changing the cell updates the output."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "0.2")
        sheet.setAlias("A1", "kerf")
        self.job.setExpression("Kerf", "Spreadsheet.kerf")
        self._op("Cut", [(_rectangle_sketch(self.doc, "Sketch"), [])])
        self.doc.recompute()
        sheet.set("A1", "1")
        self.doc.recompute()
        ir = get_ir(self.job)
        x0, _, x1, _ = _bounds(ir.operations[0])
        self.assertAlmostEqual(x1 - x0, 21.0, delta=TOL)
        self.assertEqual(ir.material.kerf, 1.0)
        self.assertEqual(ir.operations[0].settings["kerf"], 1.0)
        self.assertEqual(self._touched(), [])

    def test_job_plane_change_rebuilds_operations(self) -> None:
        self._op("Score", [(_rectangle_sketch(self.doc, "Sketch", 110, 5), [])])
        self.doc.recompute()
        self.job.JobPlane = FreeCAD.Placement(V(100, 0, 0), FreeCAD.Rotation())
        self.doc.recompute()
        x0, _, _, _ = _bounds(get_ir(self.job).operations[0])
        self.assertAlmostEqual(x0, 10, delta=TOL)
        self.assertEqual(self._touched(), [])

    # --- problems (D-009) -------------------------------------------------

    def test_operation_issues_reach_the_summary(self) -> None:
        box = self.doc.addObject("Part::Box", "Box")
        sketch = _rectangle_sketch(self.doc, "Sketch", 10, 10)
        self._op("Cut", [(sketch, []), (box, ["Face99"])], ProjectionMode="Face")
        self.doc.recompute()
        self.assertTrue(self.job.isValid())
        [line] = self.job.ValidationSummary
        self.assertTrue(line.startswith("error: BROKEN_SOURCE:"), line)
        self.assertIn("Box.Face99", line)
        self.assertTrue(get_ir(self.job).has_errors)

    def test_geometry_outside_the_bed_is_reported(self) -> None:
        self._op("Cut", [(_rectangle_sketch(self.doc, "Sketch", 590, 0), [])])
        self.doc.recompute()
        self.assertEqual([s.split(":")[1].strip() for s in self.job.ValidationSummary],
                         ["OUT_OF_BOUNDS"])

    def test_unknown_profile_marks_the_job(self) -> None:
        bad = make_job(self.doc, "co2", "steel", name="BadJob")
        self.doc.recompute()
        self.assertFalse(bad.isValid())
        self.assertEqual(len(bad.ValidationSummary), 1)
        self.assertIn("steel", bad.ValidationSummary[0])
        with self.assertRaises(ValueError):
            get_ir(bad)

    # --- save / restore (D-008) -------------------------------------------

    def test_save_restore_recomputes_the_transient_cache(self) -> None:
        self._op("Cut", [(_rectangle_sketch(self.doc, "Sketch"), [])])
        self.doc.recompute()
        before = get_ir(self.job).to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "job.FCStd")
            self.doc.saveAs(path)
            name = self.job.Name
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)
            job = self.doc.getObject(name)
            self.assertIsInstance(job.Proxy, job_mod.LaserJob)
            self.assertEqual(job.IRCache, "")
            after = get_ir(job).to_dict()
        self.assertEqual(after["source_document"], "job.FCStd")
        for key in ("operations", "bounds", "issues", "machine", "material"):
            self.assertEqual(after[key], before[key], key)


if __name__ == "__main__":
    unittest.main()
