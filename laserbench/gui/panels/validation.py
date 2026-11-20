# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation results panel (FR-060). Task W-06.

A task panel listing the job's issues, errors first. Clicking one selects its operation and,
when the issue has a location, centres the 3D view on it and marks it with a cross.

Issue locations are in the machine frame (IR_SCHEMA §2.2). Every job→machine transform in
``core/coords.py`` is its own inverse (identity, or flips of x and/or y), so applying it
again gives the job-frame point, which the job plane places in 3D.
"""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui

from laserbench.core.coords import to_machine_point
from laserbench.core.ir import IRIssue, Point

translate = FreeCAD.Qt.translate

_SEVERITY_ORDER = {"error": 0, "warning": 1}


def location_in_3d(job_obj: Any, location: Point) -> FreeCAD.Vector:
    """A machine-frame issue location as a 3D point on the job plane."""
    from laserbench.objects.job import get_ir

    machine = get_ir(job_obj).machine
    x, y = to_machine_point(location, machine)  # self-inverse: machine → job frame
    return job_obj.JobPlane.multVec(FreeCAD.Vector(x, y, 0))


def sorted_issues(issues: list[IRIssue]) -> list[IRIssue]:
    """Errors before warnings; otherwise the order the validator found them."""
    return sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i.severity, 2))


class ValidationPanel:
    """Lists issues; selecting one selects the operation and zooms to its location."""

    def __init__(self, job_obj: Any) -> None:
        self.job = job_obj
        self.issues: list[IRIssue] = []
        self.marker: Any = None

        self.form = QtGui.QWidget()
        self.form.setWindowTitle(translate("LaserBench", "Check job"))
        layout = QtGui.QVBoxLayout(self.form)
        self.summary = QtGui.QLabel()
        self.summary.setWordWrap(True)
        self.list = QtGui.QTreeWidget()
        self.list.setColumnCount(3)
        self.list.setHeaderLabels([translate("LaserBench", "Problem"),
                                   translate("LaserBench", "Operation"),
                                   translate("LaserBench", "Details")])
        self.list.setRootIsDecorated(False)
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(lambda item, _prev: self._activate(item))
        layout.addWidget(self.summary)
        layout.addWidget(self.list)

        from laserbench.objects.job import get_ir

        try:
            issues = get_ir(job_obj).issues
        except ValueError as exc:  # the job could not be computed at all
            issues = []
            self.summary.setText(str(exc))
            self.list.hide()
            return
        self.show_issues(issues)

    def show_issues(self, issues: list[IRIssue]) -> None:
        """Fill the list (FR-060)."""
        self.issues = sorted_issues(issues)
        self.list.clear()
        style = QtGui.QApplication.style()
        icons = {"error": style.standardIcon(QtGui.QStyle.SP_MessageBoxCritical),
                 "warning": style.standardIcon(QtGui.QStyle.SP_MessageBoxWarning)}
        doc = self.job.Document
        for n, issue in enumerate(self.issues):
            op = doc.getObject(issue.operation_id) if issue.operation_id else None
            item = QtGui.QTreeWidgetItem([issue.code.replace("_", " ").capitalize(),
                                          op.Label if op is not None else "",
                                          issue.message])
            item.setIcon(0, icons.get(issue.severity, QtGui.QIcon()))
            item.setToolTip(2, issue.message)
            item.setData(0, QtCore.Qt.UserRole, n)
            self.list.addTopLevelItem(item)
        for col in range(2):
            self.list.resizeColumnToContents(col)
        errors = sum(1 for i in issues if i.severity == "error")
        warnings = len(issues) - errors
        if not issues:
            text = translate("LaserBench", "{job}: no problems found. Ready to export.")
        elif errors:
            text = translate("LaserBench", "{job}: {e} error(s) and {w} warning(s). Errors "
                             "must be fixed before export. Click a problem to show it.")
        else:
            text = translate("LaserBench", "{job}: {w} warning(s). The job can be exported. "
                             "Click a problem to show it.")
        self.summary.setText(text.format(job=self.job.Label, e=errors, w=warnings))

    def _activate(self, item: Any) -> None:
        if item is None:
            return
        self.select_issue(item.data(0, QtCore.Qt.UserRole))

    def select_issue(self, index: int) -> None:
        """Select the issue's operation and centre the view on its location."""
        issue = self.issues[index]
        FreeCADGui.Selection.clearSelection()
        op = self.job.Document.getObject(issue.operation_id) if issue.operation_id else None
        if op is not None:
            FreeCADGui.Selection.addSelection(op)
        view = _active_view(self.job.Document)
        if view is None:
            return
        if issue.location is None:
            if op is not None:
                FreeCADGui.SendMsgToActiveView("ViewSelection")
            self._set_marker(None)
            return
        point = location_in_3d(self.job, issue.location)
        self._set_marker(point)
        centre_view_on(view, point)

    def _set_marker(self, point: FreeCAD.Vector | None) -> None:
        from pivy import coin

        view = _active_view(self.job.Document)
        if view is None:
            return
        graph = view.getSceneGraph()
        if self.marker is not None:
            graph.removeChild(self.marker)
            self.marker = None
        if point is None:
            return
        self.marker = coin.SoSeparator()
        colour = coin.SoBaseColor()
        colour.rgb.setValue(1.0, 0.5, 0.0)
        coords = coin.SoCoordinate3()
        coords.point.setValue(point.x, point.y, point.z)
        markers = coin.SoMarkerSet()
        markers.markerIndex = coin.SoMarkerSet.CROSS_9_9
        for node in (colour, coords, markers):
            self.marker.addChild(node)
        graph.addChild(self.marker)

    def marker_point(self) -> tuple[float, float, float] | None:
        """Where the cross is, for tests; None when no issue location is shown."""
        if self.marker is None:
            return None
        return tuple(self.marker.getChild(1).point.getValues()[0])

    def getStandardButtons(self) -> Any:  # noqa: N802
        return QtGui.QDialogButtonBox.Close

    def reject(self) -> bool:
        self._set_marker(None)
        FreeCADGui.Control.closeDialog()
        return True

    def accept(self) -> bool:
        return self.reject()


def centre_view_on(view: Any, point: FreeCAD.Vector) -> None:
    """Move the camera so ``point`` is in the centre, keeping its direction and zoom."""
    cam = view.getCameraNode()
    direction = cam.orientation.getValue().multVec(_coin_vec(0, 0, -1))
    distance = cam.focalDistance.getValue()
    target = _coin_vec(point.x, point.y, point.z)
    cam.position.setValue(target - direction * distance)


def view_centre(view: Any) -> tuple[float, float, float]:
    """The camera's focal point (for tests)."""
    cam = view.getCameraNode()
    direction = cam.orientation.getValue().multVec(_coin_vec(0, 0, -1))
    focal = cam.position.getValue() + direction * cam.focalDistance.getValue()
    return tuple(focal.getValue())


def _coin_vec(x: float, y: float, z: float) -> Any:
    from pivy import coin

    return coin.SbVec3f(x, y, z)


def _active_view(doc: FreeCAD.Document) -> Any:
    gui_doc = FreeCADGui.getDocument(doc.Name)
    view = getattr(gui_doc, "ActiveView", None) if gui_doc is not None else None
    return view if view is not None and hasattr(view, "getCameraNode") else None
