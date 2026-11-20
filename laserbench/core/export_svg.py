# SPDX-License-Identifier: LGPL-2.1-or-later
"""Colour-coded SVG export (FR-071, FR-072). Task K-06.

Layout and metadata are fixed by IR_SCHEMA.md §5.
"""

from __future__ import annotations

from pathlib import Path

from laserbench.core.ir import IRJob

LB_NAMESPACE = "https://github.com/koepnick/FreeCAD_meerk40t/ns/ir/1"


def to_svg(job: IRJob) -> str:
    """Render the job as SVG text. Deterministic for a given job (NFR-002)."""
    raise NotImplementedError("K-06")


def export_svg(job: IRJob, path: Path) -> Path:
    """Write to_svg(job) atomically to path and return it."""
    raise NotImplementedError("K-06")
