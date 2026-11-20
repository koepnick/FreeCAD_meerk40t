# SPDX-License-Identifier: LGPL-2.1-or-later
"""IR JSON export (FR-070). Task K-07."""

from __future__ import annotations

from pathlib import Path

from laserbench.core.fsutil import atomic_write_text
from laserbench.core.ir import IRError, IRJob


def export_json(job: IRJob, path: Path) -> Path:
    """Write job.to_json() atomically to path and return it."""
    return atomic_write_text(Path(path), job.to_json())


def load_json(path: Path) -> IRJob:
    """Read an IR JSON file (schema-checked by IRJob.from_json).

    Raises IRError (or IRVersionError) for invalid content and OSError if the file
    cannot be read.
    """
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IRError(f"{Path(path).name}: not UTF-8 ({exc})") from exc
    return IRJob.from_json(text)
