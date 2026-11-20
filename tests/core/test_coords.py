# SPDX-License-Identifier: LGPL-2.1-or-later
"""K-02: job frame → machine frame for every origin (FR-011, IR_SCHEMA §2.2)."""

from __future__ import annotations

import pytest

from laserbench.core.coords import (
    is_mirroring,
    to_machine_operation,
    to_machine_path,
    to_machine_point,
    work_area,
)
from laserbench.core.ir import IRBounds, IRMachine, IROperation, IRPath, IRRegion, IRSegment

W, H = 600.0, 400.0


def gantry(origin: str) -> IRMachine:
    return IRMachine(id="m", name="M", kind="gantry", width=W, height=H, origin=origin)


GALVO = IRMachine(id="g", name="G", kind="galvo", width=110, height=110, origin="center")

# Job point (10, 20) — 10 mm right of the front-left corner, 20 mm towards the rear.
EXPECTED = {
    "front-left": ((10, 20), False),
    "front-right": ((W - 10, 20), True),
    "rear-left": ((10, H - 20), True),
    "rear-right": ((W - 10, H - 20), False),
}


@pytest.mark.parametrize("origin", sorted(EXPECTED))
def test_point_and_mirroring_per_gantry_origin(origin: str) -> None:
    point, mirror = EXPECTED[origin]
    assert to_machine_point((10, 20), gantry(origin)) == point
    assert is_mirroring(gantry(origin)) is mirror


def test_galvo_centre_is_identity() -> None:
    assert to_machine_point((-5, 7), GALVO) == (-5, 7)
    assert not is_mirroring(GALVO)


def _quarter_arc() -> IRPath:
    # From (20, 10) counter-clockwise around (10, 10) to (10, 20), then a polyline.
    return IRPath(start=(20, 10), segments=[
        IRSegment.arc((10, 20), (10, 10), True),
        IRSegment.poly([(5, 25)], (0, 20)),
        IRSegment.line((0, 0)),
    ])


def _signed_turn(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


@pytest.mark.parametrize("origin", sorted(EXPECTED))
def test_arc_direction_follows_the_geometry(origin: str) -> None:
    """An arc's ccw must agree with the turn direction of its transformed points."""
    m = gantry(origin)
    path = to_machine_path(_quarter_arc(), m)
    arc = path.segments[0]
    assert arc.kind == "arc"
    assert arc.center == to_machine_point((10, 10), m)
    assert arc.end == to_machine_point((10, 20), m)
    # start → end seen from the centre: positive cross product means counter-clockwise.
    turn = _signed_turn(arc.center, path.start, arc.end)
    assert (turn > 0) is arc.ccw
    assert arc.ccw is (not EXPECTED[origin][1])
    assert path.segments[1].points == [to_machine_point((5, 25), m)]
    assert path.segments[2].end == to_machine_point((0, 0), m)


def test_full_circle_flips_on_reflection() -> None:
    circle = IRPath(start=(30, 20), segments=[IRSegment.arc((30, 20), (20, 20), True)],
                    closed=True)
    out = to_machine_path(circle, gantry("front-right"))
    assert out.closed and out.segments[0].ccw is False
    assert out.start == out.segments[0].end == (W - 30, 20)


def test_operation_paths_and_regions_are_transformed() -> None:
    square = IRPath(start=(0, 0), segments=[IRSegment.line((10, 0)), IRSegment.line((10, 10)),
                                            IRSegment.line((0, 10)), IRSegment.line((0, 0))],
                    closed=True)
    op = IROperation(id="f", label="Fill", type="fill", order=3, colour="#00ff00",
                     settings={"power": 5}, regions=[IRRegion(outer=square, holes=[square])])
    out = to_machine_operation(op, gantry("rear-left"))
    assert (out.id, out.order, out.settings) == ("f", 3, {"power": 5})
    assert out.regions[0].outer.start == (0, H)
    assert out.regions[0].holes[0].segments[1].end == (10, H - 10)
    assert op.regions[0].outer.start == (0, 0)  # input untouched


def test_work_area() -> None:
    assert work_area(gantry("rear-right")) == IRBounds(0, 0, W, H)
    assert work_area(GALVO) == IRBounds(-55, -55, 55, 55)
