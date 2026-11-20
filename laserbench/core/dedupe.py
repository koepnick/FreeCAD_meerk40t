# SPDX-License-Identifier: LGPL-2.1-or-later
"""Remove duplicate and overlapping geometry within one operation (FR-054). Task K-03.

Every path is broken into its segments. Segments are taken in input order, and each one
keeps only what no earlier kept segment already covers:

* a line loses the stretches that lie on an earlier collinear line (so a shared edge of
  two adjacent squares is cut once, even if the squares differ in size);
* an arc is dropped when an earlier arc has the same centre, radius and end points, in
  either direction (a full circle matches any full circle on the same centre and radius);
* a poly is dropped when an earlier poly has the same points, in either direction.

What survives is chained back into paths. A closed path that loses a segment becomes an
open path that starts just after the gap, so the remaining chain is still one stroke.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from laserbench.core.ir import POINT_TOLERANCE, IRPath, IRSegment, Point


@dataclass
class _Piece:
    """A kept segment with its own start, and whether it joins the previous piece."""

    start: Point
    segment: IRSegment
    joined: bool  # True if it continues the previous piece of the same path with no gap


def dedupe_paths(paths: list[IRPath], tolerance: float = POINT_TOLERANCE) -> list[IRPath]:
    """Drop coincident lines and arcs (in either direction) and trim collinear overlaps.

    Closed paths that lose a segment become open paths. Output order is deterministic.
    """
    kept_lines: list[tuple[Point, Point]] = []
    kept_curves: list[tuple[Point, IRSegment]] = []
    out: list[IRPath] = []
    for path in paths:
        pieces: list[_Piece] = []
        lost_any = False
        gap_before_next = False
        start = path.start
        for seg in path.segments:
            if seg.kind == "line" and math.dist(start, seg.end) > tolerance:
                spans = _uncovered(start, seg.end, kept_lines, tolerance)
                for i, (a, b) in enumerate(spans):
                    # Snap to the original end points so kept pieces chain exactly.
                    a = start if _same(a, start, tolerance) else a
                    b = seg.end if _same(b, seg.end, tolerance) else b
                    joined = i == 0 and not gap_before_next and a == start
                    pieces.append(_Piece(a, IRSegment.line(b), joined))
                    kept_lines.append((a, b))
                full = (len(spans) == 1 and pieces[-1].start == start
                        and pieces[-1].segment.end == seg.end)
                lost_any = lost_any or not full
                gap_before_next = not (pieces and spans and pieces[-1].segment.end == seg.end)
            elif _length(start, seg) <= tolerance:
                lost_any = True  # degenerate: nothing to cut; joins still line up
            elif any(_same_curve(start, seg, s, k, tolerance) for s, k in kept_curves):
                lost_any = True
                gap_before_next = True
            else:
                pieces.append(_Piece(start, seg, not gap_before_next))
                kept_curves.append((start, seg))
                gap_before_next = False
            start = seg.end
        if not lost_any:
            out.append(path)
            continue
        out.extend(_chain(pieces, path.closed, gap_before_next, tolerance))
    return out


def _chain(pieces: list[_Piece], closed: bool, gap_at_end: bool, tol: float) -> list[IRPath]:
    """Group pieces into runs without gaps; rejoin across the start of a closed path."""
    runs: list[list[_Piece]] = []
    for piece in pieces:
        if runs and piece.joined:
            runs[-1].append(piece)
        else:
            runs.append([piece])
    if (closed and len(runs) > 1 and not gap_at_end and runs[0][0].joined
            and _same(runs[-1][-1].segment.end, runs[0][0].start, tol)):
        runs[0] = runs.pop() + runs[0]
    return [
        IRPath(start=run[0].start, segments=[p.segment for p in run], closed=False)
        for run in runs
    ]


def _same(a: Point, b: Point, tol: float) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _length(start: Point, seg: IRSegment) -> float:
    if seg.kind == "arc":
        assert seg.center is not None
        if _same(start, seg.end, POINT_TOLERANCE):
            return math.dist(start, seg.center)  # full circle: any positive radius counts
        return math.dist(start, seg.end)
    points = [start, *(seg.points or []), seg.end]
    return sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))


def _uncovered(a: Point, b: Point, kept: list[tuple[Point, Point]], tol: float
               ) -> list[tuple[Point, Point]]:
    """The parts of line a→b not lying on any kept collinear line, in order from a."""
    length = math.dist(a, b)
    if length <= tol:
        return []
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    free = [(0.0, length)]
    for c, d in kept:
        if abs(_offset(c, a, ux, uy)) > tol or abs(_offset(d, a, ux, uy)) > tol:
            continue  # not collinear
        tc = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
        td = (d[0] - a[0]) * ux + (d[1] - a[1]) * uy
        lo, hi = min(tc, td), max(tc, td)
        free = [piece for f in free for piece in _subtract(f, lo, hi, tol)]
        if not free:
            return []
    return [((a[0] + ux * s, a[1] + uy * s), (a[0] + ux * e, a[1] + uy * e)) for s, e in free]


def _offset(p: Point, a: Point, ux: float, uy: float) -> float:
    """Signed distance of p from the line through a with unit direction (ux, uy)."""
    return (p[0] - a[0]) * uy - (p[1] - a[1]) * ux


def _subtract(span: tuple[float, float], lo: float, hi: float, tol: float
              ) -> list[tuple[float, float]]:
    s, e = span
    if hi <= s + tol or lo >= e - tol:
        return [span]  # no overlap (touching at an end point doesn't count)
    out = []
    if lo - s > tol:
        out.append((s, lo))
    if e - hi > tol:
        out.append((hi, e))
    return out


def _same_curve(start: Point, seg: IRSegment, other_start: Point, other: IRSegment,
                tol: float) -> bool:
    if seg.kind != other.kind:
        return False
    if seg.kind == "arc":
        assert seg.center is not None and other.center is not None
        if not _same(seg.center, other.center, tol):
            return False
        if abs(math.dist(start, seg.center) - math.dist(other_start, other.center)) > tol:
            return False
        full = _same(start, seg.end, tol)
        if full or _same(other_start, other.end, tol):
            return full and _same(other_start, other.end, tol)
        forward = _same(start, other_start, tol) and _same(seg.end, other.end, tol)
        backward = _same(start, other.end, tol) and _same(seg.end, other_start, tol)
        return (forward and seg.ccw == other.ccw) or (backward and seg.ccw != other.ccw)
    mine = [start, *(seg.points or []), seg.end]
    theirs = [other_start, *(other.points or []), other.end]
    if len(mine) != len(theirs):
        return False
    return (all(_same(p, q, tol) for p, q in zip(mine, theirs, strict=True))
            or all(_same(p, q, tol) for p, q in zip(mine, reversed(theirs), strict=True)))
