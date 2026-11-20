# SPDX-License-Identifier: LGPL-2.1-or-later
"""DXF export, one layer per operation (FR-073). Phase 2."""

from __future__ import annotations

from pathlib import Path

from laserbench.core.ir import IRJob


def to_dxf(job: IRJob) -> str:
    """Render the job as DXF (LINE/ARC/LWPOLYLINE entities, mm units)."""
    raise NotImplementedError("FR-073 (phase 2)")


def export_dxf(job: IRJob, path: Path) -> Path:
    """Write to_dxf(job) atomically to path and return it."""
    raise NotImplementedError("FR-073 (phase 2)")
