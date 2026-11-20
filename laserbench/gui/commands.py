# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI commands (FR-030, FR-032, FR-040, FR-070 to FR-074). Tasks W-04, W-07.

Imports FreeCADGui and Qt lazily inside functions so this module imports headless. The
selection helpers here take plain objects, so they are tested under freecadcmd.
"""

from __future__ import annotations

from typing import Any

import FreeCAD

translate = FreeCAD.Qt.translate


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802 - Qt's name
    """Mark ``text`` for translation; FreeCAD translates command texts when it shows them."""
    return text


#: Every command the workbench has, in toolbar order.
COMMANDS: tuple[str, ...] = (
    "LaserBench_CreateJob",
    "LaserBench_AddOperation",
    "LaserBench_MoveOperationUp",
    "LaserBench_MoveOperationDown",
    "LaserBench_ToggleOperation",
    "LaserBench_Validate",
    "LaserBench_Export",
    "LaserBench_Send",
)

OPERATION_TYPE = "LaserBench::LaserOperation"
JOB_TYPE = "LaserBench::LaserJob"


# --- selection helpers (no GUI needed) ---------------------------------------------------


def _type_of(obj: Any) -> str | None:
    return getattr(getattr(obj, "Proxy", None), "Type", None)


def sources_from_selection(selection: list[Any]) -> list[tuple[Any, list[str]]]:
    """Turn ``Gui.Selection.getSelectionEx()`` into a Sources value.

    LaserBench objects are skipped, so selecting a job alongside the geometry is fine.
    A whole-object pick gives ``[]`` sub-names (the whole sketch, solid or Body).
    """
    sources = []
    for sel in selection:
        obj = sel.Object
        if _type_of(obj) in (OPERATION_TYPE, JOB_TYPE):
            continue
        sources.append((obj, [s for s in sel.SubElementNames if s]))
    return sources


def target_job(selection: list[Any], doc: FreeCAD.Document | None) -> Any | None:
    """The job a new operation goes into: a selected job, an operation's job, or the
    only job in the document. None when it's ambiguous or there is none."""
    from laserbench.objects.job import jobs_in
    from laserbench.objects.operation import find_job

    for sel in selection:
        kind = _type_of(sel.Object)
        if kind == JOB_TYPE:
            return sel.Object
        if kind == OPERATION_TYPE:
            job = find_job(sel.Object)
            if job is not None:
                return job
    jobs = jobs_in(doc) if doc is not None else []
    return jobs[0] if len(jobs) == 1 else None


def selected_operations(selection: list[Any]) -> list[Any]:
    """Selected LaserOperations, in selection order."""
    return [s.Object for s in selection if _type_of(s.Object) == OPERATION_TYPE]


# --- commands -------------------------------------------------------------------------------


def _icon() -> str:
    import os

    import laserbench

    return os.path.join(os.path.dirname(laserbench.__file__), "resources", "icons",
                        "laserbench.svg")


def _selection() -> list[Any]:
    import FreeCADGui

    return FreeCADGui.Selection.getSelectionEx()


def _show(panel: Any) -> None:
    import FreeCADGui

    FreeCADGui.Control.showDialog(panel)


def _no_dialog_open() -> bool:
    import FreeCADGui

    return FreeCADGui.Control.activeDialog() is False


class CreateJob:
    """Create a LaserJob, choosing the machine and material (FR-030)."""

    def GetResources(self) -> dict[str, str]:  # noqa: N802
        return {"Pixmap": _icon(),
                "MenuText": QT_TRANSLATE_NOOP("LaserBench_CreateJob", "Create job"),
                "ToolTip": QT_TRANSLATE_NOOP(
                    "LaserBench_CreateJob",
                    "Create a laser job for a machine and material")}

    def IsActive(self) -> bool:  # noqa: N802
        return FreeCAD.ActiveDocument is not None and _no_dialog_open()

    def Activated(self) -> None:  # noqa: N802
        from laserbench.gui.panels.job_panel import CreateJobPanel

        _show(CreateJobPanel(FreeCAD.ActiveDocument))


class AddOperation:
    """Add an operation from the selected geometry (FR-040, FR-041)."""

    def GetResources(self) -> dict[str, str]:  # noqa: N802
        return {"Pixmap": _icon(),
                "MenuText": QT_TRANSLATE_NOOP("LaserBench_AddOperation", "Add operation"),
                "ToolTip": QT_TRANSLATE_NOOP(
                    "LaserBench_AddOperation",
                    "Cut, score or fill the selected sketches, faces, edges or solids")}

    def IsActive(self) -> bool:  # noqa: N802
        from laserbench.objects.job import jobs_in

        doc = FreeCAD.ActiveDocument
        return doc is not None and bool(jobs_in(doc)) and _no_dialog_open()

    def Activated(self) -> None:  # noqa: N802
        from laserbench.gui.panels.operation_panel import AddOperationPanel

        selection = _selection()
        doc = FreeCAD.ActiveDocument
        _show(AddOperationPanel(doc, sources_from_selection(selection),
                                target_job(selection, doc)))


class _MoveOperation:
    delta = 0
    name = ""
    menu = ""
    tip = ""

    def GetResources(self) -> dict[str, str]:  # noqa: N802
        return {"Pixmap": _icon(), "MenuText": self.menu, "ToolTip": self.tip}

    def IsActive(self) -> bool:  # noqa: N802
        return FreeCAD.ActiveDocument is not None and len(
            selected_operations(_selection())) == 1

    def Activated(self) -> None:  # noqa: N802
        from laserbench.objects.job import move_operation
        from laserbench.objects.operation import find_job

        [op] = selected_operations(_selection())
        job = find_job(op)
        if job is None:
            return
        doc = op.Document
        doc.openTransaction(translate("LaserBench", "Move operation"))
        try:
            move_operation(job, op, self.delta)
        finally:
            doc.commitTransaction()
        doc.recompute()


class MoveOperationUp(_MoveOperation):
    """Run the selected operation earlier (FR-032)."""

    delta = -1
    menu = QT_TRANSLATE_NOOP("LaserBench_MoveOperationUp", "Move operation up")
    tip = QT_TRANSLATE_NOOP("LaserBench_MoveOperationUp",
                            "Run the selected operation one step earlier")


class MoveOperationDown(_MoveOperation):
    """Run the selected operation later (FR-032)."""

    delta = 1
    menu = QT_TRANSLATE_NOOP("LaserBench_MoveOperationDown", "Move operation down")
    tip = QT_TRANSLATE_NOOP("LaserBench_MoveOperationDown",
                            "Run the selected operation one step later")


class ToggleOperation:
    """Enable or disable the selected operations (FR-045)."""

    def GetResources(self) -> dict[str, str]:  # noqa: N802
        return {"Pixmap": _icon(),
                "MenuText": QT_TRANSLATE_NOOP("LaserBench_ToggleOperation",
                                              "Enable/disable operation"),
                "ToolTip": QT_TRANSLATE_NOOP(
                    "LaserBench_ToggleOperation",
                    "Disabled operations are left out of the job and its exports")}

    def IsActive(self) -> bool:  # noqa: N802
        return bool(FreeCAD.ActiveDocument) and bool(selected_operations(_selection()))

    def Activated(self) -> None:  # noqa: N802
        ops = selected_operations(_selection())
        doc = ops[0].Document
        doc.openTransaction(translate("LaserBench", "Enable/disable operation"))
        try:
            for op in ops:
                op.Enabled = not op.Enabled
        finally:
            doc.commitTransaction()
        doc.recompute()


def _job_for_command() -> Any | None:
    doc = FreeCAD.ActiveDocument
    return target_job(_selection(), doc) if doc is not None else None


def _report(text: str) -> None:
    """Report View line plus a status-bar message the user notices without a dialog."""
    import FreeCADGui

    FreeCAD.Console.PrintMessage(text + "\n")
    FreeCADGui.getMainWindow().statusBar().showMessage(text, 10000)


def _warn(title: str, text: str) -> None:
    import FreeCADGui
    from PySide import QtGui

    FreeCAD.Console.PrintWarning(text + "\n")
    QtGui.QMessageBox.warning(FreeCADGui.getMainWindow(), title, text)


def export_message(job: Any, files: dict[str, Any]) -> str:
    """One line for the user: what was written where, and any warnings left."""
    from laserbench.objects.job import get_ir

    names = ", ".join(p.name for p in files.values())
    folder = next(iter(files.values())).parent
    text = translate("LaserBench", "{job}: exported {files} to {folder}").format(
        job=job.Label, files=names, folder=folder)
    warnings = sum(1 for i in get_ir(job).issues if i.severity == "warning")
    if warnings:
        text += translate("LaserBench", " ({n} warning(s), use Check job to see them)"
                          ).format(n=warnings)
    return text


class Validate:
    """Recompute the job and list its problems (FR-060)."""

    def GetResources(self) -> dict[str, str]:  # noqa: N802
        return {"Pixmap": _icon(),
                "MenuText": QT_TRANSLATE_NOOP("LaserBench_Validate", "Check job"),
                "ToolTip": QT_TRANSLATE_NOOP(
                    "LaserBench_Validate",
                    "Recompute the job and list problems such as shapes outside the bed or "
                    "open cut contours")}

    def IsActive(self) -> bool:  # noqa: N802
        return _job_for_command() is not None and _no_dialog_open()

    def Activated(self) -> None:  # noqa: N802
        from laserbench.gui.panels.validation import ValidationPanel

        job = _job_for_command()
        if job is None:
            return
        job.Document.recompute()
        _show(ValidationPanel(job))


class Export:
    """Export the job's files: SVG and IR JSON (FR-070 to FR-072, FR-075)."""

    def GetResources(self) -> dict[str, str]:  # noqa: N802
        return {"Pixmap": _icon(),
                "MenuText": QT_TRANSLATE_NOOP("LaserBench_Export", "Export job"),
                "ToolTip": QT_TRANSLATE_NOOP(
                    "LaserBench_Export",
                    "Write the job's SVG and JSON files to its output folder")}

    def IsActive(self) -> bool:  # noqa: N802
        return _job_for_command() is not None

    def Activated(self) -> None:  # noqa: N802
        from laserbench import api

        job = _job_for_command()
        if job is None:
            return
        try:
            files = api.export(job)
        except api.ExportError as exc:
            _warn(translate("LaserBench", "Export"), str(exc))
            return
        _report(export_message(job, files))


class Send:
    """Export, then open the files in the machine's laser program (FR-074).

    Opening is all it does: the user checks the job and starts it in the laser program.
    """

    def GetResources(self) -> dict[str, str]:  # noqa: N802
        return {"Pixmap": _icon(),
                "MenuText": QT_TRANSLATE_NOOP("LaserBench_Send", "Send to laser program"),
                "ToolTip": QT_TRANSLATE_NOOP(
                    "LaserBench_Send",
                    "Export the job and open it in the program set in the machine profile "
                    "(e.g. MeerK40t). The laser does not start until you start it there.")}

    def IsActive(self) -> bool:  # noqa: N802
        return _job_for_command() is not None

    def Activated(self) -> None:  # noqa: N802
        from laserbench import api
        from laserbench.core.handoff import HandoffError
        from laserbench.objects.job import presets_dir

        job = _job_for_command()
        if job is None:
            return
        title = translate("LaserBench", "Send to laser program")
        try:
            proc = api.send(job)
        except (api.ExportError, HandoffError) as exc:
            _warn(title, str(exc))
            return
        files = api.output_paths(job)
        if proc is None:
            _warn(title, translate(
                "LaserBench",
                "{msg}\n\nThe machine profile {machine!r} has no send command, so nothing "
                "was opened. Add one to {path}, for example \"send_command\": "
                "[\"meerk40t\", \"{{svg}}\"].").format(
                    msg=export_message(job, files), machine=job.MachineProfile,
                    path=presets_dir() / "machines.json"))
            return
        _report(export_message(job, files) + translate(
            "LaserBench", ". Opened in the laser program: check it there and start the job "
            "yourself."))


_IMPLEMENTED: dict[str, type] = {
    "LaserBench_CreateJob": CreateJob,
    "LaserBench_AddOperation": AddOperation,
    "LaserBench_MoveOperationUp": MoveOperationUp,
    "LaserBench_MoveOperationDown": MoveOperationDown,
    "LaserBench_ToggleOperation": ToggleOperation,
    "LaserBench_Validate": Validate,
    "LaserBench_Export": Export,
    "LaserBench_Send": Send,
}


def register_commands() -> list[str]:
    """Register every command with FreeCADGui and return their names (for InitGui)."""
    import FreeCADGui

    for name, cls in _IMPLEMENTED.items():
        FreeCADGui.addCommand(name, cls())
    return list(_IMPLEMENTED)
