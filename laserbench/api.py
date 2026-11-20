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


def export(job: Any, formats: Sequence[str] = DEFAULT_FORMATS, out_dir: Path | None = None
           ) -> dict[str, Path]:
    """Export the job; returns {"svg": path, ...}. Refuses if the job has errors."""
    raise NotImplementedError("W-07")


def send(job: Any) -> subprocess.Popen[bytes] | None:
    """Export, then launch the machine profile's send command (FR-074)."""
    raise NotImplementedError("W-07")


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
