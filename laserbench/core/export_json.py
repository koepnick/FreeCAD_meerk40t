# SPDX-License-Identifier: LGPL-2.1-or-later
"""IR JSON export (FR-070). Task K-07."""

from __future__ import annotations

from pathlib import Path

from laserbench.core.ir import IRJob


def export_json(job: IRJob, path: Path) -> Path:
    """Write job.to_json() atomically to path and return it."""
    raise NotImplementedError("K-07")


def load_json(path: Path) -> IRJob:
    """Read an IR JSON file (schema-checked by IRJob.from_json)."""
    raise NotImplementedError("K-07")
