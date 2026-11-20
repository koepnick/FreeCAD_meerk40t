# SPDX-License-Identifier: LGPL-2.1-or-later
"""Convert Part wires in the job plane to IR paths (FR-051). Task G-04."""

from __future__ import annotations

import Part

from laserbench.core.ir import IRPath, IRRegion, IRSegment, Point

DEFAULT_TOLERANCE = 0.01  # mm chord deviation for curves that aren't lines or circles


def edge_to_segment(edge: Part.Edge, start: Point, tolerance: float = DEFAULT_TOLERANCE
                    ) -> IRSegment:
    """Line → line, circle arc → arc (ccw in the job plane), anything else → poly."""
    raise NotImplementedError("G-04")


def wire_to_path(wire: Part.Wire, tolerance: float = DEFAULT_TOLERANCE) -> IRPath:
    """Convert one wire, following its edge order and orientation."""
    raise NotImplementedError("G-04")


def wires_to_paths(wires: list[Part.Wire], tolerance: float = DEFAULT_TOLERANCE
                   ) -> list[IRPath]:
    """Convert each wire with wire_to_path."""
    raise NotImplementedError("G-04")


def wires_to_regions(wires: list[Part.Wire], tolerance: float = DEFAULT_TOLERANCE
                     ) -> list[IRRegion]:
    """Group closed wires into outer boundaries with their holes, for fill operations."""
    raise NotImplementedError("G-04")
