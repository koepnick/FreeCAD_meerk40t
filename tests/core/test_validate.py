# SPDX-License-Identifier: LGPL-2.1-or-later
"""K-05: one test per validation rule that triggers it, plus clean cases (FR-060..FR-066)."""

from __future__ import annotations

from laserbench.core.ir import (
    ISSUE_CODES,
    IRBounds,
    IRJob,
    IRMachine,
    IRMaterial,
    IROperation,
    IRPath,
    IRRegion,
    IRSegment,
)
from laserbench.core.validate import (
    check_bounds,
    check_empty,
    check_fill_regions,
    check_open_contours,
    check_self_intersection,
    check_smaller_than_kerf,
    path_bounds,
    validate_job,
)

GANTRY = IRMachine(id="m", name="Bed", kind="gantry", width=300, height=200,
                   origin="front-left")
GALVO = IRMachine(id="g", name="Field", kind="galvo", width=110, height=110, origin="center")
MATERIAL = IRMaterial(id="ply3", name="Ply 3 mm", thickness=3, kerf=0.2)


def poly(points, closed=False) -> IRPath:
    return IRPath(start=points[0], segments=[IRSegment.line(p) for p in points[1:]],
                  closed=closed)


def square(x, y, size) -> IRPath:
    return poly([(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)], True)


def circle(cx, cy, r) -> IRPath:
    s = (cx + r, cy)
    return IRPath(start=s, segments=[IRSegment.arc(s, (cx, cy), True)], closed=True)


def op(type_="cut", paths=(), regions=(), id_="op1") -> IROperation:
    return IROperation(id=id_, label=id_.upper(), type=type_, order=0, colour="#ff0000",
                       paths=list(paths), regions=list(regions))


def job(*ops, machine=GANTRY, material=MATERIAL) -> IRJob:
    return IRJob(name="j", machine=machine, material=material, operations=list(ops))


def codes(issues) -> list[str]:
    return [i.code for i in issues]


# --- path_bounds -------------------------------------------------------------------------

def test_path_bounds_include_arc_extremes() -> None:
    assert path_bounds(circle(10, 10, 5)) == IRBounds(5, 5, 15, 15)
    # Quarter arc from (5, 0) ccw to (0, 5) around the origin: no extreme in between.
    quarter = IRPath(start=(5, 0), segments=[IRSegment.arc((0, 5), (0, 0), True)])
    assert path_bounds(quarter) == IRBounds(0, 0, 5, 5)
    # The same ends clockwise go the long way round, through -x and -y.
    long_way = IRPath(start=(5, 0), segments=[IRSegment.arc((0, 5), (0, 0), False)])
    assert path_bounds(long_way) == IRBounds(-5, -5, 5, 5)


# --- FR-061 OUT_OF_BOUNDS ----------------------------------------------------------------

def test_out_of_bounds_on_a_gantry() -> None:
    inside, sticking_out = square(10, 10, 50), square(280, 10, 50)
    assert check_bounds(job(op(paths=[inside]))) == []
    [issue] = check_bounds(job(op(paths=[inside, sticking_out])))
    assert (issue.code, issue.severity, issue.operation_id) == ("OUT_OF_BOUNDS", "error", "op1")
    assert issue.location == (305, 35)
    assert "300 × 200" in issue.message


def test_out_of_bounds_on_a_galvo_field_and_via_an_arc() -> None:
    assert check_bounds(job(op(paths=[circle(0, 0, 50)]), machine=GALVO)) == []
    assert codes(check_bounds(job(op(paths=[circle(0, 0, 56)]), machine=GALVO))) == [
        "OUT_OF_BOUNDS"]
    # Fill regions count too; edge-on-boundary is inside.
    fill = op("fill", regions=[IRRegion(outer=square(-55, -55, 110))])
    assert check_bounds(job(fill, machine=GALVO)) == []


# --- FR-062 OPEN_CONTOUR -----------------------------------------------------------------

def test_open_contour_in_cut_only() -> None:
    line = poly([(1, 2), (5, 2)])
    [issue] = check_open_contours(op(paths=[square(0, 0, 10), line]))
    assert (issue.code, issue.severity, issue.location) == ("OPEN_CONTOUR", "warning", (1, 2))
    assert check_open_contours(op("score", paths=[line])) == []


# --- FR-063 FILL_NO_REGION ---------------------------------------------------------------

def test_fill_without_regions() -> None:
    [issue] = check_fill_regions(op("fill"))
    assert (issue.code, issue.severity) == ("FILL_NO_REGION", "error")
    assert check_fill_regions(op("fill", regions=[IRRegion(outer=square(0, 0, 5))])) == []
    assert check_fill_regions(op("cut")) == []


# --- FR-064 SMALLER_THAN_KERF ------------------------------------------------------------

def test_small_hole_and_narrow_slot() -> None:
    kerf = 0.2
    ok_hole, tiny_hole = circle(50, 50, 0.25), circle(20, 20, 0.15)  # Ø0.5 ok, Ø0.3 < 0.4
    slot_ok = poly([(0, 0), (30, 0), (30, 0.25), (0, 0.25), (0, 0)], True)
    slot_narrow = poly([(0, 5), (30, 5), (30, 5.15), (0, 5.15), (0, 5)], True)
    issues = check_smaller_than_kerf(
        op(paths=[square(0, 0, 100), ok_hole, tiny_hole, slot_ok, slot_narrow]), kerf)
    assert codes(issues) == ["SMALLER_THAN_KERF", "SMALLER_THAN_KERF"]
    assert issues[0].location == (20, 20)
    assert issues[1].location == (15, 5.075)
    assert check_smaller_than_kerf(op(paths=[tiny_hole]), 0.0) == []
    assert check_smaller_than_kerf(op("score", paths=[tiny_hole]), kerf) == []


# --- FR-066 SELF_INTERSECTION ------------------------------------------------------------

def test_self_intersecting_bow_tie() -> None:
    bow_tie = poly([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)], True)
    [issue] = check_self_intersection(op(paths=[bow_tie, square(20, 0, 5)]))
    assert (issue.code, issue.severity, issue.location) == ("SELF_INTERSECTION", "warning",
                                                            (5, 5))


def test_simple_contours_do_not_self_intersect() -> None:
    slot = IRPath(start=(0, 0), segments=[
        IRSegment.line((10, 0)), IRSegment.arc((10, 4), (10, 2), True),
        IRSegment.line((0, 4)), IRSegment.arc((0, 0), (0, 2), True)], closed=True)
    concave = poly([(0, 0), (10, 0), (10, 10), (5, 3), (0, 10), (0, 0)], True)
    assert check_self_intersection(op(paths=[slot, concave, circle(0, 0, 3),
                                             poly([(0, 0), (5, 5), (0, 5), (5, 0)])])) == []


def test_doubled_back_edge_counts_as_self_intersection() -> None:
    spike = poly([(0, 0), (10, 0), (10, 5), (10, 2), (10, 8), (0, 8), (0, 0)], True)
    assert codes(check_self_intersection(op(paths=[spike]))) == ["SELF_INTERSECTION"]


def test_region_boundaries_are_checked() -> None:
    bow_tie = poly([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)], True)
    fill = op("fill", regions=[IRRegion(outer=square(-20, -20, 50), holes=[bow_tie])])
    assert codes(check_self_intersection(fill)) == ["SELF_INTERSECTION"]


# --- EMPTY_OPERATION ---------------------------------------------------------------------

def test_empty_operation() -> None:
    [issue] = check_empty(op())
    assert (issue.code, issue.severity) == ("EMPTY_OPERATION", "warning")
    assert check_empty(op(paths=[square(0, 0, 1)])) == []


# --- validate_job ------------------------------------------------------------------------

def test_validate_job_order_and_codes() -> None:
    bad_cut = op(paths=[square(290, 0, 20), poly([(0, 0), (1, 1)])], id_="cut")
    bad_fill = op("fill", id_="fill")
    issues = validate_job(job(bad_cut, bad_fill))
    assert [(i.code, i.operation_id) for i in issues] == [
        ("OUT_OF_BOUNDS", "cut"),
        ("OPEN_CONTOUR", "cut"),
        ("EMPTY_OPERATION", "fill"),
        ("FILL_NO_REGION", "fill"),
    ]


def test_clean_job_has_no_issues() -> None:
    plate = op(paths=[circle(30, 30, 3), square(10, 10, 40)])
    assert validate_job(job(plate)) == []


def test_every_core_code_is_covered() -> None:
    core_codes = {"OUT_OF_BOUNDS", "OPEN_CONTOUR", "FILL_NO_REGION", "SMALLER_THAN_KERF",
                  "SELF_INTERSECTION", "EMPTY_OPERATION"}
    assert core_codes <= set(ISSUE_CODES)
