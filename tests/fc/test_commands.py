# SPDX-License-Identifier: LGPL-2.1-or-later
"""W-04: the App-side logic behind the commands (selection → sources, target job, reorder).

The commands and panels themselves need a GUI; tests/gui covers them under xvfb.
"""

import unittest
from types import SimpleNamespace

import FreeCAD
import Part

from laserbench.core.presets import MachineProfile, MaterialPreset
from laserbench.gui.commands import (
    COMMANDS,
    selected_operations,
    sources_from_selection,
    target_job,
)
from laserbench.objects import job as job_mod
from laserbench.objects.job import add_operation, make_job, move_operation, ordered_operations
from laserbench.objects.operation import make_operation

CO2 = MachineProfile(id="co2", name="CO2", kind="gantry", width=600, height=400,
                     origin="rear-left")
PLY = MaterialPreset(id="ply3", machine_id="co2", name="Ply", thickness=3.0, kerf=0.2)


def sel(obj, *subs):
    return SimpleNamespace(Object=obj, SubElementNames=tuple(subs))


class TestCommandLogic(unittest.TestCase):
    def setUp(self) -> None:
        job_mod.set_preset_resolver(lambda m, p: (CO2, PLY))
        self.doc = FreeCAD.newDocument("LBCommands")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.job = make_job(self.doc, "co2", "ply3")

    def tearDown(self) -> None:
        FreeCAD.closeDocument(self.doc.Name)
        job_mod.set_preset_resolver(None)

    def _ops(self, n):
        ops = []
        for _ in range(n):
            op = make_operation(self.doc, "Score", [])
            add_operation(self.job, op)
            ops.append(op)
        return ops

    def test_command_names(self) -> None:
        self.assertIn("LaserBench_CreateJob", COMMANDS)
        self.assertIn("LaserBench_AddOperation", COMMANDS)

    def test_sources_from_selection(self) -> None:
        [op] = self._ops(1)
        selection = [sel(self.box, "Face6", "Face1"), sel(self.job), sel(op),
                     sel(self.doc.addObject("Part::Cylinder", "Cyl"))]
        sources = sources_from_selection(selection)
        self.assertEqual([(o.Name, s) for o, s in sources],
                         [("Box", ["Face6", "Face1"]), ("Cyl", [])])

    def test_target_job(self) -> None:
        [op] = self._ops(1)
        self.assertIs(target_job([], self.doc), self.job)  # the only job
        other = make_job(self.doc, "co2", "ply3", name="Other")
        self.assertIsNone(target_job([sel(self.box)], self.doc))  # ambiguous
        self.assertIs(target_job([sel(other)], self.doc), other)
        self.assertIs(target_job([sel(self.box), sel(op)], self.doc), self.job)
        self.assertIsNone(target_job([], None))

    def test_selected_operations(self) -> None:
        a, b = self._ops(2)
        self.assertEqual(selected_operations([sel(b), sel(self.box), sel(a)]), [b, a])

    def test_move_operation_reorders_and_renumbers(self) -> None:
        """FR-032: order is user-adjustable; the tree order follows."""
        a, b, c = self._ops(3)
        self.assertEqual(ordered_operations(self.job), [a, b, c])
        self.assertTrue(move_operation(self.job, c, -1))
        self.assertEqual(ordered_operations(self.job), [a, c, b])
        self.assertEqual([o.Order for o in (a, c, b)], [0, 1, 2])
        self.assertEqual(list(self.job.Operations), [a, c, b])
        self.assertFalse(move_operation(self.job, a, -1))
        self.assertTrue(move_operation(self.job, a, 5))
        self.assertEqual(ordered_operations(self.job), [c, b, a])

    def test_move_fixes_gaps_and_ties_in_order(self) -> None:
        a, b, c = self._ops(3)
        a.Order, b.Order, c.Order = 7, 7, 2
        self.assertEqual(ordered_operations(self.job), [c, a, b])
        move_operation(self.job, b, -1)
        self.assertEqual([(o.Name, o.Order) for o in ordered_operations(self.job)],
                         [(c.Name, 0), (b.Name, 1), (a.Name, 2)])

    def test_reorder_changes_the_ir(self) -> None:
        sketch_a = self.doc.addObject("Part::Feature", "A")
        sketch_a.Shape = Part.makePolygon([FreeCAD.Vector(10, 10, 0), FreeCAD.Vector(20, 10, 0)])
        a, b = self._ops(2)
        a.Sources = [(sketch_a, "")]
        b.Sources = [(sketch_a, "")]
        self.doc.recompute()
        self.assertEqual([o.id for o in job_mod.get_ir(self.job).operations], [a.Name, b.Name])
        move_operation(self.job, b, -1)
        self.doc.recompute()
        self.assertEqual([o.id for o in job_mod.get_ir(self.job).operations], [b.Name, a.Name])
