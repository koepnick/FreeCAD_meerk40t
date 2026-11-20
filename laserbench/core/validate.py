# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation rules producing IRIssues (FR-060 to FR-064, FR-066). Task K-05.

Issue codes and severities are fixed by IR_SCHEMA.md §3.9 / ir.ISSUE_CODES.
BROKEN_SOURCE, KERF_COLLAPSE and GEOMETRY_ERROR come from the fc pipeline, not from here.

Rules run on the finished job, so geometry and issue locations are in the machine frame.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from laserbench.core.ir import POINT_TOLERANCE, IRBounds, IRIssue, IRJob, IROperation, IRPath, Point

_ARC_STEP = math.radians(5)


def check_bounds(job: IRJob) -> list[IRIssue]:
    """OUT_OF_BOUNDS for geometry outside the machine work area or galvo field (FR-061).

    One issue per operation, located at the centre of its first path that sticks out.
    """
    area = _work_area(job)
    issues = []
    for op in job.operations:
        outside = [b for b in (path_bounds(p) for p in _all_paths(op))
                   if not _contains(area, b)]
        if outside:
            first = outside[0]
            where = "galvo field" if job.machine.kind == "galvo" else "machine bed"
            issues.append(IRIssue(
                code="OUT_OF_BOUNDS", operation_id=op.id,
                location=((first.min_x + first.max_x) / 2, (first.min_y + first.max_y) / 2),
                message=(f"{_name(op)}: {len(outside)} path(s) extend outside the "
                         f"{area.width:g} × {area.height:g} mm {where}. Move the geometry "
                         f"or change the job plane.")))
    return issues


def check_open_contours(op: IROperation) -> list[IRIssue]:
    """OPEN_CONTOUR for each open path in a cut operation, located at its start (FR-062)."""
    if op.type != "cut":
        return []
    return [IRIssue(code="OPEN_CONTOUR", operation_id=op.id, location=p.start,
                    message=(f"{_name(op)}: a contour is not closed, so the part won't "
                             f"come free. Close the sketch or use a Score operation."))
            for p in op.paths if not p.closed]


def check_fill_regions(op: IROperation) -> list[IRIssue]:
    """FILL_NO_REGION for a fill operation without closed regions (FR-063)."""
    if op.type != "fill" or op.regions:
        return []
    return [IRIssue(code="FILL_NO_REGION", operation_id=op.id,
                    message=(f"{_name(op)}: there is no closed region to fill. Fill needs "
                             f"closed outlines; check the sources and projection mode."))]


def check_smaller_than_kerf(op: IROperation, kerf: float) -> list[IRIssue]:
    """SMALLER_THAN_KERF for slots narrower than kerf or holes under 2 × kerf (FR-064).

    A loop's size is its hydraulic diameter, 4 × area / perimeter: a circle's diameter, a
    square's side, about twice a long slot's width. So one threshold, 2 × kerf, covers
    both the hole rule and the slot rule.
    """
    if op.type != "cut" or kerf <= 0:
        return []
    issues = []
    for path in op.paths:
        if not path.closed:
            continue
        poly = _polygon(path)
        perimeter = _perimeter(poly)
        if perimeter <= 0:
            continue
        size = 4 * abs(_area(poly)) / perimeter
        if size < 2 * kerf:
            b = path_bounds(path)
            issues.append(IRIssue(
                code="SMALLER_THAN_KERF", operation_id=op.id,
                location=((b.min_x + b.max_x) / 2, (b.min_y + b.max_y) / 2),
                message=(f"{_name(op)}: a feature about {size:.3g} mm across is too small "
                         f"for the {kerf:g} mm kerf and may burn away.")))
    return issues


def check_self_intersection(op: IROperation) -> list[IRIssue]:
    """SELF_INTERSECTION for each self-intersecting closed path (FR-066)."""
    issues = []
    for path in _all_paths(op):
        if not path.closed:
            continue
        crossing = _self_crossing(_polygon(path))
        if crossing is not None:
            issues.append(IRIssue(
                code="SELF_INTERSECTION", operation_id=op.id, location=crossing,
                message=(f"{_name(op)}: a contour crosses itself, so inside and outside "
                         f"are ambiguous. Fix the sketch.")))
    return issues


def check_empty(op: IROperation) -> list[IRIssue]:
    """EMPTY_OPERATION when an enabled operation produced no geometry."""
    if op.paths or op.regions:
        return []
    return [IRIssue(code="EMPTY_OPERATION", operation_id=op.id,
                    message=f"{_name(op)} produced no geometry and will do nothing.")]


def validate_job(job: IRJob) -> list[IRIssue]:
    """Run every rule above. Order: job-level rules, then each operation in IR order."""
    issues = check_bounds(job)
    for op in job.operations:
        issues += check_empty(op)
        issues += check_open_contours(op)
        issues += check_fill_regions(op)
        issues += check_smaller_than_kerf(op, job.material.kerf)
        issues += check_self_intersection(op)
    return issues


def path_bounds(path: IRPath) -> IRBounds:
    """Axis-aligned bounds of a path, including arc extremes (IR_SCHEMA §3.4)."""
    xs, ys = [path.start[0]], [path.start[1]]
    current = path.start
    for seg in path.segments:
        pts = [seg.end, *(seg.points or [])]
        if seg.kind == "arc":
            pts += _arc_extremes(current, seg.end, seg.center, bool(seg.ccw))  # type: ignore[arg-type]
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
        current = seg.end
    return IRBounds(min(xs), min(ys), max(xs), max(ys))


# --- helpers ---------------------------------------------------------------------------


def _name(op: IROperation) -> str:
    return op.label or op.id


def _all_paths(op: IROperation) -> Iterator[IRPath]:
    yield from op.paths
    for region in op.regions:
        yield region.outer
        yield from region.holes


def _work_area(job: IRJob) -> IRBounds:
    m = job.machine
    if m.kind == "galvo":
        return IRBounds(-m.width / 2, -m.height / 2, m.width / 2, m.height / 2)
    return IRBounds(0.0, 0.0, m.width, m.height)


def _contains(area: IRBounds, b: IRBounds) -> bool:
    t = POINT_TOLERANCE
    return (b.min_x >= area.min_x - t and b.min_y >= area.min_y - t
            and b.max_x <= area.max_x + t and b.max_y <= area.max_y + t)


def _sweep(start: Point, end: Point, center: Point, ccw: bool) -> tuple[float, float]:
    """Start angle and signed sweep of an arc; equal ends mean a full circle."""
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
    if math.dist(start, end) <= POINT_TOLERANCE:
        sweep = 2 * math.pi if ccw else -2 * math.pi
    return a0, sweep


def _arc_extremes(start: Point, end: Point, center: Point, ccw: bool) -> list[Point]:
    """The axis-extreme points (0°, 90°, 180°, 270°) that the arc passes through."""
    a0, sweep = _sweep(start, end, center, ccw)
    r = math.dist(start, center)
    out = []
    for k in range(4):
        angle = k * math.pi / 2
        along = (angle - a0) % (2 * math.pi) if sweep > 0 else (a0 - angle) % (2 * math.pi)
        if along <= abs(sweep):
            out.append((center[0] + r * math.cos(angle), center[1] + r * math.sin(angle)))
    return out


def _polygon(path: IRPath) -> list[Point]:
    """Vertices of a closed path with arcs discretised; the closing vertex is omitted."""
    pts = [path.start]
    current = path.start
    for seg in path.segments:
        if seg.kind == "arc":
            assert seg.center is not None
            a0, sweep = _sweep(current, seg.end, seg.center, bool(seg.ccw))
            r = math.dist(current, seg.center)
            n = max(4, math.ceil(abs(sweep) / _ARC_STEP))
            pts += [(seg.center[0] + r * math.cos(a0 + sweep * k / n),
                     seg.center[1] + r * math.sin(a0 + sweep * k / n)) for k in range(1, n)]
        pts += seg.points or []
        pts.append(seg.end)
        current = seg.end
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) <= POINT_TOLERANCE:
        pts.pop()
    return pts


def _area(poly: list[Point]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(poly, poly[1:] + poly[:1], strict=True)) / 2


def _perimeter(poly: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(poly, poly[1:] + poly[:1], strict=True))


def _self_crossing(poly: list[Point]) -> Point | None:
    """A point where two non-adjacent edges of the closed polygon meet, if any."""
    edges = [(a, b) for a, b in zip(poly, poly[1:] + poly[:1], strict=True)
             if math.dist(a, b) > POINT_TOLERANCE]
    n = len(edges)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # first and last edges share the start vertex
            hit = _segments_meet(*edges[i], *edges[j])
            if hit is not None:
                return hit
    return None


def _segments_meet(p: Point, p2: Point, q: Point, q2: Point) -> Point | None:
    rx, ry = p2[0] - p[0], p2[1] - p[1]
    sx, sy = q2[0] - q[0], q2[1] - q[1]
    denom = rx * sy - ry * sx
    qpx, qpy = q[0] - p[0], q[1] - p[1]
    if abs(denom) < 1e-12:
        # Parallel: only a problem if they overlap along the same line.
        if abs(qpx * ry - qpy * rx) > POINT_TOLERANCE * math.hypot(rx, ry):
            return None
        length2 = rx * rx + ry * ry
        t0 = (qpx * rx + qpy * ry) / length2
        t1 = t0 + (sx * rx + sy * ry) / length2
        lo, hi = max(0.0, min(t0, t1)), min(1.0, max(t0, t1))
        if hi - lo > POINT_TOLERANCE / math.sqrt(length2):
            return (p[0] + rx * lo, p[1] + ry * lo)
        return None
    t = (qpx * sy - qpy * sx) / denom
    u = (qpx * ry - qpy * rx) / denom
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (p[0] + rx * t, p[1] + ry * t)
    return None
