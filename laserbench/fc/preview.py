# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the 3D-view preview from IR (FR-034). Task G-05.

IR coordinates here are in the job frame (the job plane's local XY), before the machine
transform of ``core/coords.py``. Colouring per operation is the view provider's job (W-05).
"""

from __future__ import annotations

import math

import FreeCAD
import Part

from laserbench.core.ir import POINT_TOLERANCE, IROperation, IRPath, IRSegment, Point

_Z = FreeCAD.Vector(0, 0, 1)


def operation_shape(op: IROperation, job_plane: FreeCAD.Placement) -> Part.Shape:
    """Edges of one job-frame operation, placed on the job plane."""
    edges: list[Part.Edge] = []
    for path in _paths(op):
        for start, seg in path.iter_segments():
            edges.extend(_segment_edges(start, seg))
    compound = Part.Compound(edges)
    compound.Placement = job_plane
    return compound


def build_preview(operations: list[IROperation], job_plane: FreeCAD.Placement) -> Part.Compound:
    """Compound of all operations' edges. Its bounding box matches the IR bounds."""
    return Part.Compound([operation_shape(op, job_plane) for op in operations])


def _paths(op: IROperation) -> list[IRPath]:
    paths = list(op.paths)
    for region in op.regions:
        paths.append(region.outer)
        paths.extend(region.holes)
    return paths


def _v(p: Point) -> FreeCAD.Vector:
    return FreeCAD.Vector(p[0], p[1], 0)


def _same(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) <= POINT_TOLERANCE and abs(a[1] - b[1]) <= POINT_TOLERANCE


def _segment_edges(start: Point, seg: IRSegment) -> list[Part.Edge]:
    if seg.kind == "line":
        return [] if _same(start, seg.end) else [Part.makeLine(_v(start), _v(seg.end))]
    if seg.kind == "poly":
        points = [start, *(seg.points or []), seg.end]
        return [Part.makeLine(_v(a), _v(b))
                for a, b in zip(points, points[1:], strict=False) if not _same(a, b)]
    return [_arc_edge(start, seg)]


def _arc_edge(start: Point, seg: IRSegment) -> Part.Edge:
    assert seg.center is not None
    cx, cy = seg.center
    radius = math.hypot(start[0] - cx, start[1] - cy)
    if _same(start, seg.end):
        circle = Part.makeCircle(radius, _v(seg.center), _Z)
        return circle if seg.ccw else circle.reversed()
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(seg.end[1] - cy, seg.end[0] - cx)
    sweep = (a1 - a0) % math.tau if seg.ccw else -((a0 - a1) % math.tau)
    mid = a0 + sweep / 2
    through = FreeCAD.Vector(cx + radius * math.cos(mid), cy + radius * math.sin(mid), 0)
    return Part.Arc(_v(start), through, _v(seg.end)).toShape()
