# SPDX-License-Identifier: LGPL-2.1-or-later
"""Create Job task panel: pick a machine profile and material preset (FR-030). Task W-04."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui
from PySide import QtGui

from laserbench.core import presets
from laserbench.objects import job as job_mod

translate = FreeCAD.Qt.translate


def load_choices() -> tuple[list[presets.MachineProfile], list[presets.MaterialPreset], str]:
    """Profiles and presets from the user's data folder, and an error message if any."""
    data_dir = job_mod.presets_dir()
    try:
        presets.ensure_defaults(data_dir)
        return presets.load_machines(data_dir), presets.load_materials(data_dir), ""
    except (presets.PresetError, OSError) as exc:
        return [], [], str(exc)


class CreateJobPanel:
    """Task panel with machine, material and name; OK creates the job."""

    def __init__(self, doc: FreeCAD.Document,
                 machines: list[presets.MachineProfile] | None = None,
                 materials: list[presets.MaterialPreset] | None = None) -> None:
        self.doc = doc
        error = ""
        if machines is None or materials is None:
            machines, materials, error = load_choices()
        self.machines, self.materials = machines, materials
        self.created: Any = None

        self.form = QtGui.QWidget()
        self.form.setWindowTitle(translate("LaserBench", "Create laser job"))
        layout = QtGui.QFormLayout(self.form)
        self.machine = QtGui.QComboBox()
        self.material = QtGui.QComboBox()
        self.name = QtGui.QLineEdit("LaserJob")
        self.message = QtGui.QLabel(error)
        self.message.setWordWrap(True)
        layout.addRow(translate("LaserBench", "Machine"), self.machine)
        layout.addRow(translate("LaserBench", "Material"), self.material)
        layout.addRow(translate("LaserBench", "Name"), self.name)
        layout.addRow(self.message)
        for m in machines:
            self.machine.addItem(m.name, m.id)
        self.machine.currentIndexChanged.connect(self._fill_materials)
        self._fill_materials()
        if not machines and not error:
            self.message.setText(translate(
                "LaserBench", "No machine profiles yet. Add one in Preferences → LaserBench."))

    def _fill_materials(self, *_: Any) -> None:
        self.material.clear()
        machine_id = self.machine.currentData()
        for m in self.materials:
            if m.machine_id == machine_id:
                self.material.addItem(f"{m.name} ({m.thickness:g} mm)", m.id)

    def getStandardButtons(self) -> Any:  # noqa: N802
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def create(self) -> Any:
        """Create the job from the current choices (also used by tests)."""
        machine_id, material_id = self.machine.currentData(), self.material.currentData()
        if not machine_id or not material_id:
            self.message.setText(translate("LaserBench", "Choose a machine and a material."))
            return None
        self.doc.openTransaction(translate("LaserBench", "Create laser job"))
        try:
            name = self.name.text().strip() or "LaserJob"
            self.created = job_mod.make_job(self.doc, machine_id, material_id, name="LaserJob")
            self.created.Label = name
        finally:
            self.doc.commitTransaction()
        self.doc.recompute()
        return self.created

    def accept(self) -> bool:
        if self.create() is None:
            return False
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self) -> bool:
        FreeCADGui.Control.closeDialog()
        return True
