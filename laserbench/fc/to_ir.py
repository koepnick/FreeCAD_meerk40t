# SPDX-License-Identifier: LGPL-2.1-or-later
"""Convert Part wires in the job plane to IR paths (FR-051). Task G-04.

Input wires lie in the job plane's local XY (z = 0), as produced by ``fc/extract.py``.
Output is in the same frame; ``core/coords.py`` maps it to the machine frame later.
"""

from __future__ import annotations

import FreeCAD
import Part

from laserbench.core.ir import IRPath, IRRegion, IRSegment, Point

DEFAULT_TOLERANCE = 0.01  # mm chord deviation for curves that aren't lines or circles

_FLAT = 1.0 - 1e-9  # |axis.z| above this means a circle lies in the job plane
_INSIDE_TOL = 1e-6


def _xy(v: FreeCAD.Vector) -> Point:
    return (v.x, v.y)


def _dist2(a: Point, b: Point) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _ends(edge: Part.Edge) -> tuple[Point, Point]:
    """Edge end points in parameter order (ignoring the edge's Orientation flag)."""
    return _xy(edge.valueAt(edge.FirstParameter)), _xy(edge.valueAt(edge.LastParameter))


def edge_to_segment(edge: Part.Edge, start: Point, tolerance: float = DEFAULT_TOLERANCE
                    ) -> IRSegment:
    """Line → line, circle arc → arc (ccw in the job plane), anything else → poly.

    The edge is traversed away from whichever of its ends is nearer ``start``, so callers
    don't have to care about OCC's edge orientation flags.
    """
    p0, p1 = _ends(edge)
    forward = _dist2(p0, start) <= _dist2(p1, start)
    end = p1 if forward else p0
    curve = edge.Curve

    if isinstance(curve, Part.Line | Part.LineSegment):
        return IRSegment.line(end)
    if isinstance(curve, Part.Circle) and abs(curve.Axis.z) >= _FLAT:
        # Increasing parameter runs counter-clockwise about the circle's axis.
        ccw = (curve.Axis.z > 0) == forward
        if edge.isClosed():
            end = start  # a full circle ends where it starts
        return IRSegment.arc(end, _xy(curve.Center), ccw)

    points = _discretize_within(edge, tolerance)
    if not forward:
        points.reverse()
    return IRSegment.poly(points[1:-1], end)


def _discretize_within(edge: Part.Edge, tolerance: float) -> list[Point]:
    """Polyline whose chords stay within ``tolerance`` of the curve (FR-051).

    OCC's Deflection is a target, not a bound (it overshoots by ~15% on ellipses), so check
    each chord and tighten until the bound holds.
    """
    deflection = tolerance
    for _ in range(6):
        vectors = edge.discretize(Deflection=deflection)
        if _max_chord_deviation(edge, vectors) <= tolerance:
            break
        deflection /= 2
    return [_xy(v) for v in vectors]


def _max_chord_deviation(edge: Part.Edge, vectors: list[FreeCAD.Vector]) -> float:
    worst = 0.0
    for a, b in zip(vectors, vectors[1:], strict=False):
        for t in (0.25, 0.5, 0.75):
            probe = Part.Vertex(a + (b - a) * t)
            worst = max(worst, edge.distToShape(probe)[0])
    return worst


def wire_to_path(wire: Part.Wire, tolerance: float = DEFAULT_TOLERANCE) -> IRPath:
    """Convert one wire, following its edge order and orientation."""
    edges = wire.OrderedEdges
    start = _xy(wire.OrderedVertexes[0].Point)
    segments: list[IRSegment] = []
    current = start
    for edge in edges:
        segment = edge_to_segment(edge, current, tolerance)
        segments.append(segment)
        current = segment.end
    closed = wire.isClosed()
    if closed:
        last = segments[-1]
        # Snap the floating-point end exactly onto the start so the IR validates.
        segments[-1] = IRSegment(last.kind, start, center=last.center, ccw=last.ccw,
                                 points=last.points)
    return IRPath(start=start, segments=segments, closed=closed)


def wires_to_paths(wires: list[Part.Wire], tolerance: float = DEFAULT_TOLERANCE
                   ) -> list[IRPath]:
    """Convert each wire with wire_to_path."""
    return [wire_to_path(w, tolerance) for w in wires]


def wires_to_regions(wires: list[Part.Wire], tolerance: float = DEFAULT_TOLERANCE
                     ) -> list[IRRegion]:
    """Group closed wires into outer boundaries with their holes, for fill operations.

    Nesting depth decides the role: even depth is an outer boundary, odd depth is a hole of
    the smallest loop around it. An island inside a hole starts a new region. Open wires
    are skipped here; validation reports them.
    """
    closed = [w for w in wires if w.isClosed()]
    depths, parents = nesting(closed)

    regions: dict[int, IRRegion] = {}
    order: list[int] = []
    for i, w in enumerate(closed):
        if depths[i] % 2 == 0:
            regions[i] = IRRegion(outer=wire_to_path(w, tolerance))
            order.append(i)
    for j, w in enumerate(closed):
        parent = parents[j]
        if depths[j] % 2 == 1 and parent is not None:
            regions[parent].holes.append(wire_to_path(w, tolerance))
    return [regions[i] for i in order]


def nesting(closed: list[Part.Wire]) -> tuple[list[int], list[int | None]]:
    """Nesting depth of each closed wire, and the index of the smallest loop around it.

    Depth 0 is an outer boundary, 1 a hole, 2 an island inside a hole, and so on.
    Shared with kerf compensation, which uses the same parity rule (FR-050).
    """
    faces = [Part.Face(w) for w in closed]
    probes = [_probe_point(w) for w in closed]
    depths: list[int] = []
    parents: list[int | None] = []
    for j in range(len(closed)):
        around = [i for i in range(len(closed))
                  if i != j and faces[i].isInside(probes[j], _INSIDE_TOL, True)]
        depths.append(len(around))
        parents.append(min(around, key=lambda i: faces[i].Area) if around else None)
    return depths, parents


def _probe_point(wire: Part.Wire) -> FreeCAD.Vector:
    """A point on the wire, used to test whether another loop contains it."""
    edge = wire.OrderedEdges[0]
    return edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
