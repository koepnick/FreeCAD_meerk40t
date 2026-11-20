# SPDX-License-Identifier: LGPL-2.1-or-later
"""W-07: api.export and api.send (FR-070 to FR-075).

The send tests launch a fake "laser program" (a Python script that records its arguments),
never a real one.
"""

import json
import shutil
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import FreeCAD
import Part

from laserbench import api
from laserbench.core.handoff import HandoffError
from laserbench.core.presets import MachineProfile, MaterialPreset
from laserbench.objects import job as job_mod
from laserbench.objects.job import add_operation, get_ir, make_job
from laserbench.objects.operation import make_operation

V = FreeCAD.Vector
SVG = "{http://www.w3.org/2000/svg}"

FAKE = """
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding="utf-8")
"""

def _python() -> str | None:
    """A plain Python interpreter; under freecadcmd sys.executable is FreeCAD itself."""
    if Path(sys.executable).name.lower().startswith("python"):
        return sys.executable
    return shutil.which("python3") or shutil.which("python")


PLY = MaterialPreset(id="ply3", machine_id="co2", name="Ply 3 mm", thickness=3.0, kerf=0.2,
                     settings={"cut": {"power": 65, "speed": 20}})


def _sketch(doc, x0=0.0, y0=0.0, w=20.0, h=10.0):
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    pts = [V(x0, y0, 0), V(x0 + w, y0, 0), V(x0 + w, y0 + h, 0), V(x0, y0 + h, 0)]
    for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
        sketch.addGeometry(Part.LineSegment(a, b), False)
    return sketch


class TestExportSend(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lb-export-"))
        self.command: list[str] = []
        job_mod.set_preset_resolver(self._resolver)
        self.doc = FreeCAD.newDocument("LBExport")
        self.sketch = _sketch(self.doc, 10, 10)
        self.job = make_job(self.doc, "co2", "ply3")
        self.job.Label = "Box lid"
        op = make_operation(self.doc, "Cut", [(self.sketch, [])])
        add_operation(self.job, op)
        self.doc.recompute()

    def tearDown(self) -> None:
        FreeCAD.closeDocument(self.doc.Name)
        job_mod.set_preset_resolver(None)

    def _resolver(self, machine_id, material_id):
        machine = MachineProfile(id="co2", name="CO2", kind="gantry", width=600, height=400,
                                 origin="rear-left", default_kerf=0.2,
                                 send_command=list(self.command))
        return machine, PLY

    def test_export_writes_svg_and_json(self) -> None:
        """FR-070/FR-071/FR-075: stable names in the output folder, matching the IR."""
        files = api.export(self.job, out_dir=self.tmp)
        self.assertEqual(files, {"svg": self.tmp / "Box lid.svg",
                                 "json": self.tmp / "Box lid.json"})
        self.assertEqual(files["json"].read_text(encoding="utf-8"), self.job.IRCache)
        root = ET.parse(files["svg"]).getroot()
        self.assertEqual(root.get("width"), "600mm")
        self.assertEqual(len(list(root.iter(SVG + "path"))), 1)
        ops = [g for g in root.findall(SVG + "g") if g.get("type")]
        self.assertEqual([g.get("type") for g in ops], ["op cut"])
        self.assertEqual(ops[0].get("power"), "650")
        self.assertEqual(api.output_paths(self.job, out_dir=self.tmp), files)

    def test_export_follows_model_changes_without_manual_recompute(self) -> None:
        """FR-033: an edit upstream is picked up by export itself."""
        api.export(self.job, out_dir=self.tmp)
        before = get_ir(self.job).bounds
        self.sketch.Placement = FreeCAD.Placement(V(30, 5, 0), FreeCAD.Rotation())  # no recompute
        files = api.export(self.job, out_dir=self.tmp)
        after = get_ir(self.job).bounds
        self.assertNotEqual(before, after)
        self.assertEqual(files["json"].read_text(encoding="utf-8"), self.job.IRCache)

    def test_export_refuses_errors(self) -> None:
        """A job with validation errors (here out of the bed) is not exported."""
        far = _sketch(self.doc, 1000, 0)
        add_operation(self.job, make_operation(self.doc, "Cut", [(far, [])]))
        self.doc.recompute()
        with self.assertRaises(api.ExportError) as ctx:
            api.export(self.job, out_dir=self.tmp)
        self.assertIn("not exported", str(ctx.exception))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_output_folder_rules(self) -> None:
        with self.assertRaises(api.ExportError):  # unsaved document, no OutputDir
            api.export(self.job)
        self.job.OutputDir = str(self.tmp / "abs")
        self.assertEqual(api.export(self.job)["svg"], self.tmp / "abs" / "Box lid.svg")
        self.job.OutputDir = "laser"
        with self.assertRaises(api.ExportError):  # relative needs a saved document
            api.export(self.job)
        self.doc.saveAs(str(self.tmp / "lid.FCStd"))
        self.assertEqual(api.export(self.job)["svg"], self.tmp / "laser" / "Box lid.svg")
        self.job.OutputDir = ""
        self.assertEqual(api.export(self.job)["json"], self.tmp / "Box lid.json")

    def test_formats(self) -> None:
        self.assertEqual(list(api.export(self.job, ["SVG", "svg"], self.tmp)), ["svg"])
        self.job.ExportFormats = ["json"]
        self.assertEqual(list(api.export(self.job, out_dir=self.tmp)), ["json"])
        for bad in (["dxf"], []):
            with self.assertRaises(api.ExportError):
                api.export(self.job, bad, self.tmp)

    def test_send_launches_the_profile_command(self) -> None:
        """FR-074: placeholders filled, launched without waiting."""
        python = _python()
        if python is None:
            self.skipTest("no Python interpreter on PATH for the fake laser program")
        script = self.tmp / "fake laser.py"
        script.write_text(FAKE, encoding="utf-8")
        record = self.tmp / "argv.json"
        self.command = [python, str(script), str(record), "{svg}", "{job_name}"]
        self.job.OutputDir = str(self.tmp / "out")
        proc = api.send(self.job)
        self.assertIsNotNone(proc)
        self.assertEqual(proc.wait(timeout=60), 0)
        args = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(args, [str(self.tmp / "out" / "Box lid.svg"), "Box lid"])
        self.assertTrue(Path(args[0]).is_file())

    def test_send_without_command_only_exports(self) -> None:
        self.job.OutputDir = str(self.tmp)
        self.assertIsNone(api.send(self.job))
        self.assertTrue((self.tmp / "Box lid.svg").is_file())

    def test_send_refuses_auto_start(self) -> None:
        self.command = ["meerk40t", "--auto", "{svg}"]
        self.job.OutputDir = str(self.tmp)
        with self.assertRaises(HandoffError):
            api.send(self.job)

    def test_send_reports_missing_program(self) -> None:
        self.command = [str(self.tmp / "no-such-laser-program"), "{svg}"]
        self.job.OutputDir = str(self.tmp)
        t0 = time.monotonic()
        with self.assertRaises(HandoffError):
            api.send(self.job)
        self.assertLess(time.monotonic() - t0, 30)


if __name__ == "__main__":
    unittest.main()
