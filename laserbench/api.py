# SPDX-License-Identifier: LGPL-2.1-or-later
"""Public scripting API (FR-080, FR-081). Task W-08.

Every GUI action has a function here. Usable headless from freecadcmd::

    import laserbench.api as lb
    lb.export_document("lid.FCStd")

FreeCAD modules are imported inside functions so ``import laserbench.api`` is cheap.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from laserbench.core.ir import IRIssue, IRJob
from laserbench.core.presets import MachineProfile, MaterialPreset

DEFAULT_FORMATS = ("svg", "json")
#: Formats export() can write now. DXF (FR-073) is Phase 2.
SUPPORTED_FORMATS = ("svg", "json")


class ExportError(RuntimeError):
    """Export was refused or failed. The message is shown to the user as is."""


def make_job(doc: Any, machine: str, material: str, name: str = "LaserJob") -> Any:
    """Create a LaserJob in ``doc`` for a machine profile id and material preset id."""
    raise NotImplementedError("W-08")


def add_operation(job: Any, op_type: str, sources: list[Any], **props: Any) -> Any:
    """Add a LaserOperation (``"cut"``, ``"score"`` or ``"fill"``) to a job."""
    raise NotImplementedError("W-08")


def recompute(job: Any) -> list[IRIssue]:
    """Recompute the document and return the job's validation issues."""
    raise NotImplementedError("W-08")


def get_ir(job: Any) -> IRJob:
    """The job's current IR (see objects.job.get_ir)."""
    raise NotImplementedError("W-08")


def export(job: Any, formats: Sequence[str] | None = None, out_dir: Path | None = None
           ) -> dict[str, Path]:
    """Export the job; returns {"svg": path, ...}. Refuses if the job has errors.

    ``formats`` defaults to the job's ExportFormats and ``out_dir`` to its OutputDir, or the
    document's folder when that is empty. Files get stable names from the job label
    (``Box lid.svg``) and are replaced atomically, so a program watching them never reads a
    half-written file (FR-075). The job is recomputed first if it is out of date.
    """
    from laserbench.core.export_json import export_json
    from laserbench.core.export_svg import export_svg

    paths = output_paths(job, formats, out_dir)
    ir = _fresh_ir(job)
    errors = [i for i in ir.issues if i.severity == "error"]
    if errors:
        lines = "\n".join(f"- {i.message}" for i in errors)
        raise ExportError(f"{job.Label} has {len(errors)} error(s) and was not exported:\n"
                          f"{lines}")
    writers = {"svg": export_svg, "json": export_json}
    written: dict[str, Path] = {}
    try:
        for fmt, path in paths.items():
            written[fmt] = writers[fmt](ir, path)
    except OSError as exc:
        raise ExportError(f"Cannot write to {path.parent}: {exc.strerror or exc}") from exc
    return written


def output_paths(job: Any, formats: Sequence[str] | None = None, out_dir: Path | None = None
                 ) -> dict[str, Path]:
    """Where export() writes each format, without writing anything (FR-075)."""
    from laserbench.core.fsutil import job_output_path

    directory = _output_dir(job, out_dir)
    return {fmt: job_output_path(directory, job.Label, fmt) for fmt in _formats(job, formats)}


def send(job: Any) -> subprocess.Popen[bytes] | None:
    """Export, then launch the machine profile's send command (FR-074).

    Returns None, after exporting, when the profile has no send command. LaserBench only
    opens the files in the laser program; the user starts the job there. Raises
    ExportError or core.handoff.HandoffError with a message for the user.
    """
    from laserbench.core.handoff import build_argv, launch
    from laserbench.objects.job import resolve_presets

    files = export(job)
    try:
        machine, _ = resolve_presets(job.MachineProfile, job.MaterialPreset)
    except (KeyError, ValueError, OSError) as exc:
        raise ExportError(f"{job.Label}: cannot read the machine profile ({exc})") from exc
    if not machine.send_command:
        return None
    argv = build_argv(machine.send_command, files, job.Label)
    return launch(argv, cwd=next(iter(files.values())).parent)


def _formats(job: Any, formats: Sequence[str] | None) -> list[str]:
    requested = list(formats) if formats is not None else list(job.ExportFormats)
    wanted: list[str] = []
    for f in (str(x).strip().lower().lstrip(".") for x in requested):
        if f and f not in wanted:
            wanted.append(f)
    unknown = [f for f in wanted if f not in SUPPORTED_FORMATS]
    if unknown:
        raise ExportError(f"{job.Label}: cannot export {', '.join(unknown)}; supported "
                          f"formats are {', '.join(SUPPORTED_FORMATS)}.")
    if not wanted:
        raise ExportError(f"{job.Label}: no export formats chosen (ExportFormats is empty).")
    return wanted


def _output_dir(job: Any, out_dir: Path | None) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    if job.OutputDir:
        directory = Path(job.OutputDir).expanduser()
        if directory.is_absolute():
            return directory
        doc_file = job.Document.FileName
        if doc_file:  # relative to the document, so a project folder can move
            return Path(doc_file).parent / directory
        raise ExportError(f"{job.Label}: OutputDir {job.OutputDir!r} is relative, but the "
                          "document has not been saved. Save it or use an absolute folder.")
    doc_file = job.Document.FileName
    if not doc_file:
        raise ExportError(f"{job.Label}: save the document first, or set the job's OutputDir.")
    return Path(doc_file).parent


def _fresh_ir(job: Any) -> IRJob:
    from laserbench.objects.job import get_ir

    # Only touched objects recompute, so this is cheap when the job is up to date; it
    # catches edits anywhere upstream (a sketch, a spreadsheet cell) before exporting.
    job.Document.recompute()
    if not job.IRCache:
        job.recompute()
    if "Invalid" in job.State or not job.IRCache:
        summary = "; ".join(job.ValidationSummary) or "recompute failed"
        raise ExportError(f"{job.Label} could not be computed: {summary}")
    return get_ir(job)


def export_document(path: str | Path, formats: Sequence[str] = DEFAULT_FORMATS) -> list[Path]:
    """Headless: open a .FCStd, recompute, and export every job in it (FR-081)."""
    raise NotImplementedError("W-08")


def load_profiles() -> list[MachineProfile]:
    """Machine profiles from the user data folder, creating defaults on first run."""
    raise NotImplementedError("W-08")


def save_profiles(profiles: list[MachineProfile]) -> None:
    """Replace the stored machine profiles."""
    raise NotImplementedError("W-08")


def load_presets() -> list[MaterialPreset]:
    """Material presets from the user data folder, creating defaults on first run."""
    raise NotImplementedError("W-08")


def save_presets(presets: list[MaterialPreset]) -> None:
    """Replace the stored material presets."""
    raise NotImplementedError("W-08")
