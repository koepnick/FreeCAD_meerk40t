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


#: Every command the workbench will have. Validate, Export and Send arrive with W-06/W-07.
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


_IMPLEMENTED: dict[str, type] = {
    "LaserBench_CreateJob": CreateJob,
    "LaserBench_AddOperation": AddOperation,
    "LaserBench_MoveOperationUp": MoveOperationUp,
    "LaserBench_MoveOperationDown": MoveOperationDown,
    "LaserBench_ToggleOperation": ToggleOperation,
}


def register_commands() -> list[str]:
    """Register every command with FreeCADGui and return their names (for InitGui)."""
    import FreeCADGui

    for name, cls in _IMPLEMENTED.items():
        FreeCADGui.addCommand(name, cls())
    return list(_IMPLEMENTED)
