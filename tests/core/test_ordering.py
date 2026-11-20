# SPDX-License-Identifier: LGPL-2.1-or-later
"""K-04: cut ordering (FR-053): holes before parents, then nearest neighbour."""

from __future__ import annotations

from laserbench.core.ir import IRPath, IRSegment
from laserbench.core.ordering import containment_depths, order_paths


def poly(points, closed=False) -> IRPath:
    return IRPath(start=points[0], segments=[IRSegment.line(p) for p in points[1:]],
                  closed=closed)


def square(x, y, size) -> IRPath:
    return poly([(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)],
                closed=True)


def circle(cx, cy, r, ccw=True) -> IRPath:
    s = (cx + r, cy)
    return IRPath(start=s, segments=[IRSegment.arc(s, (cx, cy), ccw)], closed=True)


def vertices(path):
    return {path.start, *(s.end for s in path.segments)}


def same_loop(a: IRPath, b: IRPath) -> bool:
    return a.closed == b.closed and vertices(a) == vertices(b)


def test_depths_of_nested_squares() -> None:
    paths = [square(0, 0, 100), square(10, 10, 80), square(20, 20, 10), square(60, 60, 10),
             square(200, 0, 10)]
    assert containment_depths(paths) == [0, 1, 2, 2, 0]


def test_open_paths_and_touching_loops_have_depth_zero() -> None:
    paths = [square(0, 0, 10), poly([(2, 2), (5, 5)]), square(10, 0, 10)]
    assert containment_depths(paths) == [0, 0, 0]


def test_arc_boundaries_nest() -> None:
    paths = [circle(0, 0, 50), square(-5, -5, 10), circle(0, 0, 2), circle(30, 0, 5)]
    assert containment_depths(paths) == [0, 1, 2, 1]


def test_hole_touching_its_outline_still_nests() -> None:
    # A notch sharing part of the outer boundary is still inside it.
    assert containment_depths([square(0, 0, 10), square(0, 0, 5)]) == [0, 1]


def test_holes_before_parents() -> None:
    """FR-053: every inner contour is cut before the contour that encloses it."""
    outer, hole_a, hole_b = square(0, 0, 100), square(10, 10, 10), circle(70, 70, 5)
    out = order_paths([outer, hole_a, hole_b])
    assert same_loop(out[-1], outer)
    assert all(not same_loop(p, outer) for p in out[:2])


def test_island_in_a_hole_goes_first() -> None:
    plate, window, island = square(0, 0, 100), square(10, 10, 80), square(40, 40, 10)
    out = order_paths([plate, window, island])
    assert [same_loop(a, b) for a, b in zip(out, [island, window, plate], strict=True)] == \
        [True, True, True]


def test_nearest_neighbour_within_a_level() -> None:
    far, near, middle = square(90, 0, 5), square(5, 0, 5), square(40, 0, 5)
    out = order_paths([far, near, middle], start=(0, 0))
    assert [p.start[0] for p in out] == [5, 40, 90]


def test_closed_path_rotates_to_the_nearest_vertex() -> None:
    sq = square(10, 10, 10)
    [out] = order_paths([sq], start=(25, 25))
    assert out.start == (20, 20)
    assert out.closed and out.segments[-1].end == (20, 20)
    assert vertices(out) == vertices(sq)


def test_full_circle_starts_at_its_nearest_point() -> None:
    [out] = order_paths([circle(10, 0, 5)], start=(10, 20))
    assert out.start == (10, 5)
    assert out.segments[0].end == (10, 5) and out.segments[0].center == (10, 0)


def test_open_path_can_be_cut_backwards() -> None:
    p = IRPath(start=(0, 0), segments=[
        IRSegment.line((10, 0)),
        IRSegment.arc((10, 10), (10, 5), True),
        IRSegment.poly([(5, 12)], (0, 10)),
    ])
    [out] = order_paths([p], start=(0, 11))
    assert out.start == (0, 10)
    assert [s.kind for s in out.segments] == ["poly", "arc", "line"]
    assert out.segments[0].points == [(5, 12)] and out.segments[0].end == (10, 10)
    assert out.segments[1].ccw is False and out.segments[1].end == (10, 0)
    assert out.segments[2].end == (0, 0)


def test_travel_continues_from_the_previous_end() -> None:
    a = poly([(0, 0), (50, 0)])
    b = poly([(100, 0), (60, 0)])  # nearer by its end (60) once we're at 50
    c = poly([(55, 30), (55, 40)])
    out = order_paths([c, b, a], start=(0, 0))
    assert out[0] == a
    assert out[1].start == (60, 0)


def test_deterministic_ties_follow_input_order() -> None:
    left, right = square(-15, -5, 10), square(5, -5, 10)
    assert order_paths([left, right])[0].start == (-5, -5)
    assert order_paths([right, left])[0].start == (5, -5)
    paths = [square(i * 7 % 50, i * 13 % 50, 3) for i in range(20)]
    assert order_paths(paths) == order_paths(list(paths))


def test_empty_input() -> None:
    assert order_paths([]) == []
