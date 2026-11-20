# SPDX-License-Identifier: LGPL-2.1-or-later
"""W-04 in the real GUI: commands register, panels create a job and an operation."""

import unittest
from pathlib import Path

import FreeCAD
import FreeCADGui
import Part

from laserbench.core.presets import MachineProfile, MaterialPreset
from laserbench.gui import commands
from laserbench.gui.panels.job_panel import CreateJobPanel
from laserbench.gui.panels.operation_panel import AddOperationPanel
from laserbench.objects import job as job_mod

CO2 = MachineProfile(id="co2", name="CO2 gantry", kind="gantry", width=600, height=400,
                     origin="rear-left")
FIBER = MachineProfile(id="fiber", name="Fiber", kind="galvo", width=150, height=150,
                       origin="center")
PLY = MaterialPreset(id="ply3", machine_id="co2", name="Ply", thickness=3.0, kerf=0.2)
ACRYLIC = MaterialPreset(id="acr", machine_id="co2", name="Acrylic", thickness=5.0, kerf=0.15)
ALU = MaterialPreset(id="alu", machine_id="fiber", name="Alu", thickness=0.0, kerf=0.03)
MATERIALS = [PLY, ACRYLIC, ALU]


def _resolver(machine_id, material_id):
    machine = {"co2": CO2, "fiber": FIBER}[machine_id]
    return machine, next(m for m in MATERIALS
                         if (m.machine_id, m.id) == (machine_id, material_id))


class TestCommandsGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.names = commands.register_commands()

    def setUp(self) -> None:
        job_mod.set_preset_resolver(_resolver)
        self.doc = FreeCAD.newDocument("LBGui")

    def tearDown(self) -> None:
        FreeCAD.closeDocument(self.doc.Name)
        job_mod.set_preset_resolver(None)

    def test_commands_are_registered(self) -> None:
        listed = FreeCADGui.listCommands()
        for name in self.names:
            self.assertIn(name, listed)

    def test_workbench_activates(self) -> None:
        """InitGui registers the workbench and its toolbar loads without errors (FR-003)."""
        if "LaserBenchWorkbench" not in FreeCADGui.listWorkbenches():
            # Not installed in this FreeCAD's Mod folder: load InitGui.py as FreeCAD would.
            init_gui = Path(__file__).resolve().parents[2] / "InitGui.py"
            exec(compile(init_gui.read_text(encoding="utf-8"), str(init_gui), "exec"), {})
        FreeCADGui.activateWorkbench("LaserBenchWorkbench")
        self.assertEqual(FreeCADGui.activeWorkbench().name(), "LaserBenchWorkbench")

    def test_create_job_panel(self) -> None:
        panel = CreateJobPanel(self.doc, [CO2, FIBER], MATERIALS)
        self.assertEqual(panel.machine.count(), 2)
        self.assertEqual(panel.material.count(), 2)  # only the CO2's materials
        panel.machine.setCurrentIndex(1)
        self.assertEqual(panel.material.count(), 1)
        panel.machine.setCurrentIndex(0)
        panel.material.setCurrentIndex(1)
        panel.name.setText("Lid")
        job = panel.create()
        self.assertEqual((job.Label, job.MachineProfile, job.MaterialPreset),
                         ("Lid", "co2", "acr"))
        self.assertAlmostEqual(job.Kerf.Value, 0.15)
        self.assertTrue(job.isValid())

    def test_create_job_panel_without_profiles(self) -> None:
        panel = CreateJobPanel(self.doc, [], [])
        self.assertIsNone(panel.create())
        self.assertTrue(panel.message.text())

    def test_add_operation_panel(self) -> None:
        job = job_mod.make_job(self.doc, "co2", "ply3")
        plate = self.doc.addObject("Part::Feature", "Plate")
        plate.Shape = Part.makePlane(40, 30)
        self.doc.recompute()
        panel = AddOperationPanel(self.doc, [(plate, ["Face1"])], job)
        self.assertEqual(panel.projection.currentText(), "Face")
        self.assertTrue(panel.kerf_mode.isEnabled())
        panel.op_type.setCurrentText("Score")
        self.assertFalse(panel.kerf_mode.isEnabled())
        panel.op_type.setCurrentText("Cut")
        panel.kerf_mode.setCurrentText("Outside")
        op = panel.create()
        self.assertEqual((op.OpType, op.ProjectionMode, op.KerfMode), ("Cut", "Face", "Outside"))
        self.assertEqual(list(job.Operations), [op])
        [frag] = job_mod.get_ir(job).operations
        self.assertEqual(frag.id, op.Name)
        # Undo removes the whole addition in one step.
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(list(job.Operations), [])

    def test_solid_selection_defaults_to_direction(self) -> None:
        job = job_mod.make_job(self.doc, "co2", "ply3")
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        panel = AddOperationPanel(self.doc, [(box, [])], job)
        self.assertEqual(panel.projection.currentText(), "Direction")

    def test_toggle_and_move_commands(self) -> None:
        job = job_mod.make_job(self.doc, "co2", "ply3")
        a = AddOperationPanel(self.doc, [], job).create()
        b = AddOperationPanel(self.doc, [], job).create()
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(b)
        FreeCADGui.runCommand("LaserBench_MoveOperationUp")
        self.assertEqual(job_mod.ordered_operations(job), [b, a])
        FreeCADGui.runCommand("LaserBench_ToggleOperation")
        self.assertFalse(b.Enabled)
        FreeCADGui.Selection.clearSelection()
