# SPDX-License-Identifier: LGPL-2.1-or-later
"""Remove duplicate and overlapping geometry within one operation (FR-054). Task K-03."""

from __future__ import annotations

from laserbench.core.ir import POINT_TOLERANCE, IRPath


def dedupe_paths(paths: list[IRPath], tolerance: float = POINT_TOLERANCE) -> list[IRPath]:
    """Drop coincident lines and arcs (in either direction) and trim collinear overlaps.

    Closed paths that lose a segment become open paths. Output order is deterministic.
    """
    raise NotImplementedError("K-03")
