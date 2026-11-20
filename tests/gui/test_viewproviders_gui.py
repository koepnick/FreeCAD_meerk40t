# SPDX-License-Identifier: LGPL-2.1-or-later
"""W-05: view providers, preview colours and the bed outline (FR-032, FR-034, FR-045)."""

import tempfile
import unittest
from pathlib import Path

import FreeCAD
import Part

from laserbench.core.presets import MachineProfile, MaterialPreset
from laserbench.gui.panels.operation_panel import AddOperationPanel
from laserbench.gui.viewproviders import (
    GREY,
    ViewProviderLaserJob,
    ViewProviderLaserOperation,
    attach_view_provider,
    edge_colours,
    work_area_corners,
)
from laserbench.objects import job as job_mod

V = FreeCAD.Vector
CO2 = MachineProfile(id="co2", name="CO2", kind="gantry", width=600, height=400,
                     origin="rear-left")
FIBER = MachineProfile(id="fiber", name="Fiber", kind="galvo", width=150, height=150,
                       origin="center")
PLY = MaterialPreset(id="ply3", machine_id="co2", name="Ply", thickness=3.0, kerf=0.2)
ALU = MaterialPreset(id="alu", machine_id="fiber", name="Alu", thickness=0.0, kerf=0.03)


def _resolver(machine_id, material_id):
    return {"co2": (CO2, PLY), "fiber": (FIBER, ALU)}[machine_id]


def _close(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=False))


class TestViewProviders(unittest.TestCase):
    def setUp(self) -> None:
        job_mod.set_preset_resolver(_resolver)
        self.doc = FreeCAD.newDocument("LBView")
        self.job = job_mod.make_job(self.doc, "co2", "ply3")
        attach_view_provider(self.job)
        self.ops = []
        for i in range(2):
            sketch = self.doc.addObject("Sketcher::SketchObject", f"Sketch{i}")
            for a, b in (((0, 0), (10, 0)), ((10, 0), (10, 10)), ((10, 10), (0, 10)),
                         ((0, 10), (0, 0))):
                sketch.addGeometry(Part.LineSegment(V(a[0] + 30 * i, a[1], 0),
                                                    V(b[0] + 30 * i, b[1], 0)))
            self.ops.append(AddOperationPanel(self.doc, [(sketch, [])], self.job).create())
        self.ops[1].OpType = "Score"
        self.doc.recompute()

    def tearDown(self) -> None:
        for d in list(FreeCAD.listDocuments().values()):
            if d.Name.startswith("LBView"):
                FreeCAD.closeDocument(d.Name)
        job_mod.set_preset_resolver(None)

    def test_proxies_and_tree(self) -> None:
        """FR-032: operations nest under their job."""
        self.assertIsInstance(self.job.ViewObject.Proxy, ViewProviderLaserJob)
        for op in self.ops:
            self.assertIsInstance(op.ViewObject.Proxy, ViewProviderLaserOperation)
        self.assertEqual(self.job.ViewObject.Proxy.claimChildren(), self.ops)
        self.assertTrue(self.job.ViewObject.Proxy.getIcon().endswith(".svg"))

    def test_job_edges_coloured_per_operation(self) -> None:
        """FR-034: each operation's edges are drawn in its colour."""
        colours = self.job.ViewObject.LineColorArray
        self.assertEqual(len(colours), len(self.job.Shape.Edges))
        counts = [len(sub.Edges) for sub in self.job.Shape.SubShapes]  # kerf adds corner arcs
        expected = [op.Colour for op, n in zip(self.ops, counts, strict=True) for _ in range(n)]
        for got, want in zip(colours, expected, strict=True):
            self.assertTrue(_close(got[:3], want[:3]), (got, want))
        self.assertNotEqual(tuple(colours[0][:3]), tuple(colours[-1][:3]))

    def test_colour_change_and_disable(self) -> None:
        op = self.ops[0]
        op.Colour = (0.0, 0.5, 1.0)
        self.doc.recompute()
        self.assertTrue(_close(op.ViewObject.LineColor[:3], (0.0, 0.5, 1.0)))
        self.assertTrue(_close(self.job.ViewObject.LineColorArray[0][:3], (0.0, 0.5, 1.0)))
        op.Enabled = False
        self.doc.recompute()
        self.assertTrue(_close(op.ViewObject.LineColor[:3], GREY))
        # The job preview now only holds the enabled operation, in its colour.
        self.assertEqual(len(self.job.ViewObject.LineColorArray), 4)  # a score: no kerf
        self.assertTrue(_close(self.job.ViewObject.LineColorArray[0][:3],
                               self.ops[1].Colour[:3]))

    def test_bed_outline(self) -> None:
        """The dashed outline is the bed (gantry) or the centred field (galvo)."""
        proxy = self.job.ViewObject.Proxy
        self.assertEqual([p[:2] for p in proxy.outline_points()],
                         [(0, 0), (600, 0), (600, 400), (0, 400), (0, 0)])
        self.job.MachineProfile, self.job.MaterialPreset = "fiber", "alu"
        self.doc.recompute()
        self.assertEqual(proxy.outline_points()[0][:2], (-75, -75))
        self.job.ViewObject.Visibility = False
        self.assertEqual(proxy.outline_switch.whichChild.getValue(), -1)
        self.job.ViewObject.Visibility = True
        self.assertEqual(proxy.outline_switch.whichChild.getValue(), 0)

    def test_survives_save_and_reopen(self) -> None:
        path = Path(tempfile.mkdtemp(prefix="lb-vp-")) / "LBViewSaved.FCStd"
        name = self.job.Name
        self.doc.saveAs(str(path))
        FreeCAD.closeDocument(self.doc.Name)
        doc = FreeCAD.openDocument(str(path))
        job = doc.getObject(name)
        doc.recompute()
        self.assertIsInstance(job.ViewObject.Proxy, ViewProviderLaserJob)
        self.assertEqual(len(job.ViewObject.Proxy.claimChildren()), 2)
        self.assertEqual(len(job.ViewObject.Proxy.outline_points()), 5)
        FreeCAD.closeDocument(doc.Name)

    def test_helpers(self) -> None:
        self.assertIsNone(edge_colours(Part.Shape(), [(1, 0, 0)]))
        self.assertIsNone(edge_colours(self.job.Shape, [(1, 0, 0)]))  # count mismatch
        self.assertEqual(work_area_corners("galvo", 10, 20)[2], (5, 10))


if __name__ == "__main__":
    unittest.main()
