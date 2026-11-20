# SPDX-License-Identifier: LGPL-2.1-or-later
"""Add Operation task panel: type, projection and kerf for the selection (FR-040). W-04."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui
from PySide import QtGui

from laserbench.objects import job as job_mod
from laserbench.objects import operation as op_mod

translate = FreeCAD.Qt.translate

_TYPE_HELP = {
    "Cut": "Cut through along closed outlines; kerf compensation applies.",
    "Score": "Follow the lines (open or closed) without cutting through.",
    "Fill": "Engrave the area inside closed outlines.",
}


class AddOperationPanel:
    """Task panel for a new operation on the selected geometry; OK adds it to a job."""

    def __init__(self, doc: FreeCAD.Document, sources: list[tuple[Any, list[str]]],
                 job: Any | None = None) -> None:
        self.doc = doc
        self.sources = sources
        self.created: Any = None
        self.jobs = job_mod.jobs_in(doc)

        self.form = QtGui.QWidget()
        self.form.setWindowTitle(translate("LaserBench", "Add laser operation"))
        layout = QtGui.QFormLayout(self.form)
        self.job = QtGui.QComboBox()
        for j in self.jobs:
            self.job.addItem(j.Label, j.Name)
        if job is not None and job in self.jobs:
            self.job.setCurrentIndex(self.jobs.index(job))
        self.op_type = QtGui.QComboBox()
        self.op_type.addItems(list(op_mod.OP_TYPES))
        self.projection = QtGui.QComboBox()
        self.projection.addItems(list(op_mod.PROJECTION_MODES))
        self.kerf_mode = QtGui.QComboBox()
        self.kerf_mode.addItems(list(op_mod.KERF_MODES))
        self.help = QtGui.QLabel()
        self.help.setWordWrap(True)
        self.selection = QtGui.QLabel(self._describe_sources())
        self.selection.setWordWrap(True)
        layout.addRow(translate("LaserBench", "Job"), self.job)
        layout.addRow(translate("LaserBench", "Type"), self.op_type)
        layout.addRow(translate("LaserBench", "Projection"), self.projection)
        layout.addRow(translate("LaserBench", "Kerf"), self.kerf_mode)
        layout.addRow(self.help)
        layout.addRow(translate("LaserBench", "Geometry"), self.selection)
        self.op_type.currentIndexChanged.connect(self._type_changed)
        self.projection.setCurrentText(self._default_projection())
        self._type_changed()

    def _describe_sources(self) -> str:
        if not self.sources:
            return translate("LaserBench", "Nothing selected: the operation starts empty. "
                             "Set its Sources property later.")
        parts = []
        for obj, subs in self.sources:
            parts.append(f"{obj.Label}: {', '.join(subs)}" if subs else obj.Label)
        return "; ".join(parts)

    def _default_projection(self) -> str:
        # Picked faces mean Face mode; whole solids or Bodies mean a top-down projection.
        subs = [s for _, names in self.sources for s in names]
        if subs and all(s.startswith("Face") for s in subs):
            return "Face"
        if any(getattr(obj, "Shape", None) is not None and obj.Shape.Solids and not names
               for obj, names in self.sources):
            return "Direction"
        return "Face"

    def _type_changed(self, *_: Any) -> None:
        op_type = self.op_type.currentText()
        self.kerf_mode.setEnabled(op_type == "Cut")
        self.help.setText(translate("LaserBench", _TYPE_HELP[op_type]))

    def getStandardButtons(self) -> Any:  # noqa: N802
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def create(self) -> Any:
        """Create the operation and add it to the chosen job (also used by tests)."""
        if not self.jobs:
            return None
        job = self.jobs[self.job.currentIndex()]
        self.doc.openTransaction(translate("LaserBench", "Add laser operation"))
        try:
            op = op_mod.make_operation(self.doc, self.op_type.currentText(), self.sources)
            op.Label = f"{self.op_type.currentText()}"
            op.ProjectionMode = self.projection.currentText()
            op.KerfMode = self.kerf_mode.currentText()
            job_mod.add_operation(job, op)
            self.created = op
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
