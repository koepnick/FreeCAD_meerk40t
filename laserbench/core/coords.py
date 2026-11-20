# SPDX-License-Identifier: LGPL-2.1-or-later
"""Job frame to machine frame transforms (FR-011). Task K-02.

The *job frame* is the 2D frame of the job plane as seen from above: +x to the right,
+y towards the rear of the machine. Its origin is the front-left corner of a gantry bed,
or the centre of a galvo field. The *machine frame* is defined in IR_SCHEMA.md §2.2.
Origins that mirror one axis (front-right, rear-left) flip arc direction.
"""

from __future__ import annotations

from dataclasses import replace

from laserbench.core.ir import (
    IRBounds,
    IRMachine,
    IROperation,
    IRPath,
    IRRegion,
    IRSegment,
    Point,
)

# Per gantry origin: does machine x run against job x, and machine y against job y?
_FLIPS: dict[str, tuple[bool, bool]] = {
    "front-left": (False, False),
    "front-right": (True, False),
    "rear-left": (False, True),
    "rear-right": (True, True),
}


def _flips(machine: IRMachine) -> tuple[bool, bool]:
    if machine.kind == "galvo":
        return False, False  # the job frame of a galvo is already centred on the field
    return _FLIPS[machine.origin]


def is_mirroring(machine: IRMachine) -> bool:
    """True if the job→machine transform for this origin is a reflection (flips ccw)."""
    flip_x, flip_y = _flips(machine)
    return flip_x != flip_y  # flipping both axes is a 180° rotation, not a reflection


def to_machine_point(point: Point, machine: IRMachine) -> Point:
    """Transform one job-frame point into the machine frame."""
    flip_x, flip_y = _flips(machine)
    x, y = point
    return (machine.width - x if flip_x else x, machine.height - y if flip_y else y)


def to_machine_path(path: IRPath, machine: IRMachine) -> IRPath:
    """Transform a path, including arc centres and directions."""
    mirror = is_mirroring(machine)

    def seg(s: IRSegment) -> IRSegment:
        end = to_machine_point(s.end, machine)
        if s.kind == "arc":
            assert s.center is not None and s.ccw is not None
            return IRSegment.arc(end, to_machine_point(s.center, machine),
                                 (not s.ccw) if mirror else s.ccw)
        if s.kind == "poly":
            assert s.points is not None
            return IRSegment.poly([to_machine_point(p, machine) for p in s.points], end)
        return IRSegment.line(end)

    return IRPath(start=to_machine_point(path.start, machine),
                  segments=[seg(s) for s in path.segments], closed=path.closed, kind=path.kind)


def to_machine_operation(op: IROperation, machine: IRMachine) -> IROperation:
    """Transform every path and region of an operation."""
    return replace(
        op,
        paths=[to_machine_path(p, machine) for p in op.paths],
        regions=[IRRegion(outer=to_machine_path(r.outer, machine),
                          holes=[to_machine_path(h, machine) for h in r.holes])
                 for r in op.regions],
    )


def work_area(machine: IRMachine) -> IRBounds:
    """The bed or field extent in the machine frame (used by OUT_OF_BOUNDS, FR-061)."""
    if machine.kind == "galvo":
        hw, hh = machine.width / 2, machine.height / 2
        return IRBounds(-hw, -hh, hw, hh)
    return IRBounds(0.0, 0.0, machine.width, machine.height)
