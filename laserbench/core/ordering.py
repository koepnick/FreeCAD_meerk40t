# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cut ordering: holes before the contours that enclose them, then short travel (FR-053).

Task K-04.

Closed paths are discretised (arcs every 5°) and nested by point-in-polygon tests. Paths
are cut deepest level first, so every hole and inner part is done before the outline that
would let the piece drop. Within a level the next path is the nearest one to where the
head is: closed paths are rotated to start at their nearest vertex (or the nearest point of
a full circle), and open paths may be cut from either end. Ties go to the earlier input
path, so the result is deterministic.
"""

from __future__ import annotations

import math

from laserbench.core.ir import POINT_TOLERANCE, IRPath, IRSegment, Point

_ARC_STEP = math.radians(5)


def containment_depths(paths: list[IRPath]) -> list[int]:
    """Nesting depth of each closed path (0 = outermost). Open paths get depth 0."""
    polygons = [_polygon(p) if p.closed else None for p in paths]
    areas = [abs(_area(poly)) if poly else 0.0 for poly in polygons]
    depths = []
    for i, inner in enumerate(polygons):
        depth = 0
        if inner:
            for j, outer in enumerate(polygons):
                if i != j and outer and areas[j] > areas[i] and _inside(inner, outer):
                    depth += 1
        depths.append(depth)
    return depths


def order_paths(paths: list[IRPath], start: Point = (0.0, 0.0)) -> list[IRPath]:
    """Return paths in cutting order.

    Deepest contours first, nearest-neighbour within a depth level starting from start.
    Closed paths may be rotated to start at the point nearest the previous end. Deterministic.
    """
    depths = containment_depths(paths)
    here = start
    out: list[IRPath] = []
    for level in sorted(set(depths), reverse=True):
        pending = [i for i, d in enumerate(depths) if d == level]
        while pending:
            best = min(pending, key=lambda i: (_entry(paths[i], here)[0], i))
            pending.remove(best)
            path = _entry(paths[best], here)[1]
            out.append(path)
            here = path.segments[-1].end if path.segments else path.start
    return out


# --- entry point choice ----------------------------------------------------------------


def _entry(path: IRPath, here: Point) -> tuple[float, IRPath]:
    """Distance from ``here`` to the best start of ``path``, and the path started there."""
    if not path.segments:
        return math.dist(here, path.start), path
    if path.closed:
        if len(path.segments) == 1 and path.segments[0].kind == "arc":
            return _enter_circle(path, here)
        vertices = [path.start] + [s.end for s in path.segments[:-1]]
        k = min(range(len(vertices)), key=lambda i: (math.dist(here, vertices[i]), i))
        rotated = path if k == 0 else IRPath(
            start=vertices[k], segments=path.segments[k:] + path.segments[:k],
            closed=True, kind=path.kind)
        return math.dist(here, vertices[k]), rotated
    end = path.segments[-1].end
    if math.dist(here, end) < math.dist(here, path.start):
        return math.dist(here, end), _reversed(path)
    return math.dist(here, path.start), path


def _enter_circle(path: IRPath, here: Point) -> tuple[float, IRPath]:
    seg = path.segments[0]
    assert seg.center is not None and seg.ccw is not None
    cx, cy = seg.center
    radius = math.dist(path.start, seg.center)
    away = math.dist(here, seg.center)
    if away <= POINT_TOLERANCE or radius <= POINT_TOLERANCE:
        return abs(away - radius), path
    p = (cx + (here[0] - cx) * radius / away, cy + (here[1] - cy) * radius / away)
    if math.dist(p, path.start) <= POINT_TOLERANCE:
        return math.dist(here, path.start), path
    return abs(away - radius), IRPath(start=p, segments=[IRSegment.arc(p, seg.center, seg.ccw)],
                                      closed=True, kind=path.kind)


def _reversed(path: IRPath) -> IRPath:
    starts = [path.start] + [s.end for s in path.segments[:-1]]
    segments = []
    for begin, seg in zip(reversed(starts), reversed(path.segments), strict=True):
        if seg.kind == "arc":
            assert seg.center is not None and seg.ccw is not None
            segments.append(IRSegment.arc(begin, seg.center, not seg.ccw))
        elif seg.kind == "poly":
            segments.append(IRSegment.poly(list(reversed(seg.points or [])), begin))
        else:
            segments.append(IRSegment.line(begin))
    return IRPath(start=path.segments[-1].end, segments=segments, closed=False, kind=path.kind)


# --- geometry --------------------------------------------------------------------------


def _polygon(path: IRPath) -> list[Point]:
    """Vertices of a closed path, with arcs discretised; the closing vertex is omitted."""
    pts = [path.start]
    current = path.start
    for seg in path.segments:
        if seg.kind == "arc":
            pts.extend(_arc_points(current, seg))
        elif seg.kind == "poly":
            pts.extend(seg.points or [])
        pts.append(seg.end)
        current = seg.end
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) <= POINT_TOLERANCE:
        pts.pop()
    return pts


def _arc_points(start: Point, seg: IRSegment) -> list[Point]:
    """Intermediate points of an arc (excluding its ends)."""
    assert seg.center is not None
    cx, cy = seg.center
    r = math.dist(start, seg.center)
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(seg.end[1] - cy, seg.end[0] - cx)
    sweep = (a1 - a0) % (2 * math.pi) if seg.ccw else -((a0 - a1) % (2 * math.pi))
    if abs(sweep) <= 1e-12:
        sweep = 2 * math.pi if seg.ccw else -2 * math.pi  # full circle
    n = max(4, math.ceil(abs(sweep) / _ARC_STEP))
    return [(cx + r * math.cos(a0 + sweep * k / n), cy + r * math.sin(a0 + sweep * k / n))
            for k in range(1, n)]


def _area(poly: list[Point]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1],
                                                          strict=True)) / 2


def _inside(inner: list[Point], outer: list[Point]) -> bool:
    """True if no vertex of ``inner`` is outside ``outer`` and at least one is inside."""
    seen_inside = False
    for p in inner:
        where = _classify(p, outer)
        if where < 0:
            return False
        seen_inside = seen_inside or where > 0
    return seen_inside


def _classify(p: Point, poly: list[Point]) -> int:
    """1 inside, 0 on the boundary (within tolerance), -1 outside. Even-odd rule."""
    x, y = p
    inside = False
    for a, b in zip(poly, poly[1:] + poly[:1], strict=True):
        if _on_segment(p, a, b):
            return 0
        if (a[1] > y) != (b[1] > y):
            cross_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if cross_x > x:
                inside = not inside
    return 1 if inside else -1


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    length = math.dist(a, b)
    if length <= POINT_TOLERANCE:
        return math.dist(p, a) <= POINT_TOLERANCE
    t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (length * length)
    if t < -POINT_TOLERANCE / length or t > 1 + POINT_TOLERANCE / length:
        return False
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    return abs(cross) / length <= POINT_TOLERANCE
