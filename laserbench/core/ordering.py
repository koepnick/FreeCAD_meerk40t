# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cut ordering: holes before the contours that enclose them, then short travel (FR-053).

Task K-04.
"""

from __future__ import annotations

from laserbench.core.ir import IRPath, Point


def containment_depths(paths: list[IRPath]) -> list[int]:
    """Nesting depth of each closed path (0 = outermost). Open paths get depth 0."""
    raise NotImplementedError("K-04")


def order_paths(paths: list[IRPath], start: Point = (0.0, 0.0)) -> list[IRPath]:
    """Return paths in cutting order.

    Deepest contours first, nearest-neighbour within a depth level starting from start.
    Closed paths may be rotated to start at the point nearest the previous end. Deterministic.
    """
    raise NotImplementedError("K-04")
