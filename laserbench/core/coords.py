# SPDX-License-Identifier: LGPL-2.1-or-later
"""Job frame to machine frame transforms (FR-011). Task K-02.

The *job frame* is the 2D frame of the job plane as seen from above: +x to the right,
+y towards the rear of the machine. Its origin is the front-left corner of a gantry bed,
or the centre of a galvo field. The *machine frame* is defined in IR_SCHEMA.md §2.2.
Origins that mirror one axis (front-right, rear-left) flip arc direction.
"""

from __future__ import annotations

from laserbench.core.ir import IRBounds, IRMachine, IROperation, IRPath, Point


def is_mirroring(machine: IRMachine) -> bool:
    """True if the job→machine transform for this origin is a reflection (flips ccw)."""
    raise NotImplementedError("K-02")


def to_machine_point(point: Point, machine: IRMachine) -> Point:
    """Transform one job-frame point into the machine frame."""
    raise NotImplementedError("K-02")


def to_machine_path(path: IRPath, machine: IRMachine) -> IRPath:
    """Transform a path, including arc centres and directions."""
    raise NotImplementedError("K-02")


def to_machine_operation(op: IROperation, machine: IRMachine) -> IROperation:
    """Transform every path and region of an operation."""
    raise NotImplementedError("K-02")


def work_area(machine: IRMachine) -> IRBounds:
    """The bed or field extent in the machine frame (used by OUT_OF_BOUNDS, FR-061)."""
    raise NotImplementedError("K-02")
