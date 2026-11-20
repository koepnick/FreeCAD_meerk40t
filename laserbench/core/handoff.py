# SPDX-License-Identifier: LGPL-2.1-or-later
"""Launch the user's laser program with the exported files (FR-074). Task P-03.

Argument lists only, never a shell string (no shell injection). No laser I/O (OS-1).
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

PLACEHOLDERS = ("{svg}", "{json}", "{dxf}", "{job_name}")


class HandoffError(RuntimeError):
    """The command could not be built or started. The message is shown to the user."""


def build_argv(template: Sequence[str], files: Mapping[str, Path], job_name: str) -> list[str]:
    """Substitute placeholders in each argument. ``files`` maps "svg"/"json"/"dxf" to paths.

    A placeholder whose file was not exported raises HandoffError.
    """
    raise NotImplementedError("P-03")


def launch(argv: Sequence[str], cwd: Path | None = None) -> subprocess.Popen[bytes]:
    """Start the command without waiting for it. Launch failures raise HandoffError."""
    raise NotImplementedError("P-03")
