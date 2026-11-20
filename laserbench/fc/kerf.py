# SPDX-License-Identifier: LGPL-2.1-or-later
"""Kerf compensation with Part.Face.makeOffset2D (FR-050, FR-064). Task G-03."""

from __future__ import annotations

import FreeCAD
import Part

from laserbench.core.ir import IRIssue
from laserbench.fc.to_ir import nesting

KERF_MODES = ("Auto", "Outside", "Inside", "None")

_MIN_AREA = 1e-9  # mm²; an offset face smaller than this has collapsed
_SIZE_SLACK = 1e-6  # mm; covers OCC's tolerance-enlarged bounding boxes


def compensate(
    wires: list[Part.Wire], kerf: float, mode: str, operation_id: str
) -> tuple[list[Part.Wire], list[IRIssue]]:
    """Offset closed wires by kerf/2 so parts come out at nominal size.

    Auto: outer boundaries outward, holes inward (nesting-depth parity decides).
    Open wires pass through unchanged. A loop whose offset vanishes is dropped and
    reported as KERF_COLLAPSE.

    Outside grows every loop and Inside shrinks every loop, regardless of nesting.
    An inward offset that pinches a loop into several pieces returns all of them.
    """
    if mode not in KERF_MODES:
        raise ValueError(f"unknown kerf mode {mode!r}")
    if kerf < 0:
        raise ValueError(f"kerf must not be negative, got {kerf}")
    if mode == "None" or kerf == 0:
        return list(wires), []

    closed = [w for w in wires if w.isClosed()]
    depths, _ = nesting(closed)
    half = kerf / 2
    out: list[Part.Wire] = []
    issues: list[IRIssue] = []
    closed_iter = iter(zip(closed, depths, strict=True))
    for wire in wires:
        if not wire.isClosed():
            out.append(wire)
            continue
        _, depth = next(closed_iter)
        grow = {"Outside": True, "Inside": False}.get(mode, depth % 2 == 0)
        offset = _offset(wire, half if grow else -half)
        if offset:
            out.extend(offset)
        else:
            centre = wire.BoundBox.Center
            issues.append(IRIssue(
                code="KERF_COLLAPSE",
                message=(f"A loop about {_size(wire):.3g} mm across vanishes when offset "
                         f"inward by half the {kerf:g} mm kerf; it was left out."),
                operation_id=operation_id,
                location=(centre.x, centre.y),
            ))
    return out, issues


def _offset(wire: Part.Wire, distance: float) -> list[Part.Wire]:
    """Offset one closed planar wire; an empty list means the loop collapsed.

    Two cases stay away from OCC's makeOffset2D, because it segfaults on them in FreeCAD
    1.1 (OCC 7.9) and FreeCAD converts only the first such crash in a process into
    CADKernelError; the second kills FreeCAD:

    * A full circle offset inward. Seen for every diameter up to about 2 mm at 0.1 mm,
      collapsing or not. A circle's offset is just a concentric circle, so build it.
    * A loop whose narrower bounding-box side is at most twice the inward offset. It must
      collapse (its inscribed circle is no wider than that side), so report it directly.
    """
    circle = _full_circle(wire)
    if circle is not None:
        radius = circle.Radius + distance
        if radius <= _SIZE_SLACK:
            return []
        return [Part.Wire([Part.makeCircle(radius, circle.Center, circle.Axis)])]
    if distance < 0:
        bb = wire.BoundBox
        if min(bb.XLength, bb.YLength) <= 2 * -distance + _SIZE_SLACK:
            return []
    try:
        result = Part.Face(wire).makeOffset2D(distance, 0, False, False, False)
    except (Part.OCCError, FreeCAD.Base.CADKernelError):
        return []  # OCC raises when an inward offset consumes the whole face
    return [f.OuterWire for f in result.Faces if f.Area > _MIN_AREA]


def _full_circle(wire: Part.Wire) -> Part.Circle | None:
    """The circle, if the wire is one closed circular edge."""
    if len(wire.Edges) != 1:
        return None
    edge = wire.Edges[0]
    curve = edge.Curve
    return curve if isinstance(curve, Part.Circle) and edge.isClosed() else None


def _size(wire: Part.Wire) -> float:
    bb = wire.BoundBox
    return min(bb.XLength, bb.YLength)
