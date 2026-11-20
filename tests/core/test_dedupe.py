# SPDX-License-Identifier: LGPL-2.1-or-later
"""K-03: duplicate and overlap removal within an operation (FR-054)."""

from __future__ import annotations

import math

from laserbench.core.dedupe import dedupe_paths
from laserbench.core.ir import IRPath, IRSegment


def poly(points, closed=False) -> IRPath:
    return IRPath(start=points[0], segments=[IRSegment.line(p) for p in points[1:]],
                  closed=closed)


def square(x, y, size, reverse=False) -> IRPath:
    pts = [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]
    if reverse:
        pts.reverse()
    return poly(pts, closed=True)


def circle(cx, cy, r, ccw=True, start_angle=0.0) -> IRPath:
    s = (cx + r * math.cos(start_angle), cy + r * math.sin(start_angle))
    return IRPath(start=s, segments=[IRSegment.arc(s, (cx, cy), ccw)], closed=True)


def total_length(paths) -> float:
    n = 0.0
    for p in paths:
        prev = p.start
        for s in p.segments:
            assert s.kind == "line"
            n += math.dist(prev, s.end)
            prev = s.end
    return n


def chained(path) -> bool:
    """Every segment is reachable as one stroke (the IR has no gaps by construction)."""
    return bool(path.segments)


def test_two_adjacent_squares_share_the_edge_once() -> None:
    """FR-054 acceptance: the shared edge x=10 is exported once."""
    out = dedupe_paths([square(0, 0, 10), square(10, 0, 10)])
    assert total_length(out) == 70  # 2 × 40 − 10
    assert out[0] == square(0, 0, 10)  # untouched path is returned as is
    [rest] = out[1:]
    assert not rest.closed
    # The second square loses its left edge, so it starts right after the gap.
    assert rest.start == (10, 0)
    assert [s.end for s in rest.segments] == [(20, 0), (20, 10), (10, 10)]


def test_repeated_path_is_dropped_in_either_direction() -> None:
    assert dedupe_paths([square(0, 0, 10), square(0, 0, 10)]) == [square(0, 0, 10)]
    assert dedupe_paths([square(0, 0, 10), square(0, 0, 10, reverse=True)]) == [
        square(0, 0, 10)]


def test_partial_collinear_overlap_is_trimmed() -> None:
    out = dedupe_paths([poly([(0, 0), (10, 0)]), poly([(5, 0), (15, 0)])])
    assert out[1] == poly([(10, 0), (15, 0)])
    # A long line over a short one keeps both ends.
    out = dedupe_paths([poly([(4, 0), (6, 0)]), poly([(0, 0), (10, 0)])])
    assert out[1:] == [poly([(0, 0), (4, 0)]), poly([(6, 0), (10, 0)])]


def test_parallel_and_touching_lines_are_kept() -> None:
    paths = [poly([(0, 0), (10, 0)]), poly([(0, 1), (10, 1)]), poly([(10, 0), (20, 0)])]
    assert dedupe_paths(paths) == paths


def test_within_tolerance_counts_as_coincident() -> None:
    out = dedupe_paths([poly([(0, 0), (10, 0)]), poly([(0, 0.00005), (10, 0.00005)])])
    assert out == [poly([(0, 0), (10, 0)])]


def test_arcs_coincide_in_either_direction() -> None:
    a = IRPath(start=(10, 0), segments=[IRSegment.arc((0, 10), (0, 0), True)])
    b = IRPath(start=(0, 10), segments=[IRSegment.arc((10, 0), (0, 0), False)])
    other_side = IRPath(start=(0, 10), segments=[IRSegment.arc((10, 0), (0, 0), True)])
    assert dedupe_paths([a, b]) == [a]
    assert dedupe_paths([a, other_side]) == [a, other_side]  # the other 270° arc


def test_full_circles_match_whatever_their_start() -> None:
    c1 = circle(5, 5, 2)
    c2 = circle(5, 5, 2, ccw=False, start_angle=1.0)
    assert dedupe_paths([c1, c2]) == [c1]
    assert dedupe_paths([c1, circle(5, 5, 3)]) == [c1, circle(5, 5, 3)]


def test_closed_path_with_lost_middle_segment_starts_after_the_gap() -> None:
    edge = poly([(10, 0), (10, 10)])
    out = dedupe_paths([edge, square(0, 0, 10)])
    [rest] = out[1:]
    assert not rest.closed
    assert rest.start == (10, 10)
    assert [s.end for s in rest.segments] == [(0, 10), (0, 0), (10, 0)]


def test_poly_segments_match_reversed() -> None:
    a = IRPath(start=(0, 0), segments=[IRSegment.poly([(1, 1), (2, 1)], (3, 0))])
    b = IRPath(start=(3, 0), segments=[IRSegment.poly([(2, 1), (1, 1)], (0, 0))])
    assert dedupe_paths([a, b]) == [a]


def test_overlap_within_one_path() -> None:
    there_and_back = poly([(0, 0), (10, 0), (0, 0)])
    assert dedupe_paths([there_and_back]) == [poly([(0, 0), (10, 0)])]


def test_mixed_path_keeps_curves_and_splits_at_gaps() -> None:
    edge = poly([(0, 0), (10, 0)])
    slot = IRPath(start=(0, 0), segments=[
        IRSegment.line((10, 0)),
        IRSegment.arc((10, 4), (10, 2), True),
        IRSegment.line((0, 4)),
        IRSegment.arc((0, 0), (0, 2), True),
    ], closed=True)
    [_, rest] = dedupe_paths([edge, slot])
    assert rest.start == (10, 0)
    assert [s.kind for s in rest.segments] == ["arc", "line", "arc"]
    assert rest.segments[-1].end == (0, 0)


def test_degenerate_segments_are_dropped_without_splitting() -> None:
    p = poly([(0, 0), (5, 0), (5, 0), (10, 0)])
    assert dedupe_paths([p]) == [poly([(0, 0), (5, 0), (10, 0)])]


def test_deterministic() -> None:
    paths = [square(0, 0, 10), square(10, 0, 10), square(0, 10, 10), square(5, 5, 10)]
    assert dedupe_paths(paths) == dedupe_paths(list(paths))
    assert all(chained(p) for p in dedupe_paths(paths))
