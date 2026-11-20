# SPDX-License-Identifier: LGPL-2.1-or-later
"""Resolve operation sources and flatten them into the job plane (FR-041 to FR-043).

Tasks G-01 (sources) and G-02 (projection modes). Never import Qt or FreeCADGui here.
"""

from __future__ import annotations

from collections.abc import Sequence

import FreeCAD
import Part

PROJECTION_MODES = ("Face", "Direction", "Section")


class LBSourceError(Exception):
    """A source link is broken, e.g. a face lost to a topological-naming change (FR-065).

    The pipeline turns this into a BROKEN_SOURCE issue naming the operation and sub-element.
    """

    def __init__(self, label: str, subname: str, detail: str = "") -> None:
        self.label = label
        self.subname = subname
        self.detail = detail
        super().__init__(f"{label}.{subname}: {detail}" if detail else f"{label}.{subname}")


def resolve_sources(
    links: Sequence[tuple[FreeCAD.DocumentObject, Sequence[str]]],
) -> list[tuple[FreeCAD.DocumentObject, str, Part.Shape]]:
    """Resolve an ``App::PropertyLinkSubList`` value to shapes in global coordinates.

    An empty sub-name list means the whole object (sketch, solid or Body).
    Raises LBSourceError for a missing object or sub-element. Never falls back silently.
    """
    resolved: list[tuple[FreeCAD.DocumentObject, str, Part.Shape]] = []
    for obj, subnames in links:
        label = _label(obj)
        parent = _parent_placement(obj, label)
        for sub in list(subnames) or [""]:
            shape = _shape_of(obj, sub, label)
            shape = shape.copy()
            # Part.getShape includes the object's own Placement; prepend the placements of the
            # containers (Body, Part) it sits in to land in global coordinates.
            shape.Placement = parent.multiply(shape.Placement)
            resolved.append((obj, sub, shape))
    return resolved


def _label(obj: FreeCAD.DocumentObject | None) -> str:
    """Return a human-readable label, even for a deleted or missing object."""
    if obj is None:
        return "<missing>"
    try:
        return obj.Label
    except Exception:  # deleted objects raise on any attribute access
        return "<deleted>"


def _parent_placement(obj: FreeCAD.DocumentObject | None, label: str) -> FreeCAD.Placement:
    """Placement of the containers around ``obj`` (global placement minus its own)."""
    try:
        if obj is None or obj.Document is None:
            raise ReferenceError("object is not in a document")
        own = getattr(obj, "Placement", None)
        if own is None:
            return FreeCAD.Placement()
        return obj.getGlobalPlacement().multiply(own.inverse())
    except Exception as exc:
        raise LBSourceError(label, "", f"source object is missing ({exc})") from exc


def _shape_of(obj: FreeCAD.DocumentObject, sub: str, label: str) -> Part.Shape:
    """Shape of the whole object (``sub == ""``) or of one sub-element, never a fallback."""
    # FreeCAD marks sub-elements lost to a topological-naming break with a leading "?".
    if sub.startswith("?"):
        raise LBSourceError(label, sub.lstrip("?"), "sub-element no longer exists")
    try:
        shape = Part.getShape(obj, sub, needSubElement=bool(sub))
    except Exception as exc:
        raise LBSourceError(label, sub, f"cannot resolve ({exc})") from exc
    if shape is None or shape.isNull():
        detail = "sub-element no longer exists" if sub else "object has no shape"
        raise LBSourceError(label, sub, detail)
    return shape


def to_job_plane(
    shape: Part.Shape,
    mode: str,
    job_plane: FreeCAD.Placement,
    direction: FreeCAD.Vector | None = None,
    section_height: float = 0.0,
) -> list[Part.Wire]:
    """Flatten a shape into wires lying in the job plane's local XY (z = 0).

    Face: outer wire and holes of a planar face. Direction: parallel projection along
    ``direction``. Section: slice at ``section_height`` above the job plane.
    Sketches use their own plane transformed into the job plane (FR-043). See D-013.

    ``direction`` is given in global coordinates and points from the model towards the viewer
    (TechDraw's convention); ``None`` means the job plane's normal (a top view). Geometry
    with no faces (sketches, edges) is always flattened in its own plane, whatever the mode.
    Raises LBProjectionError when the shape cannot be flattened in the requested mode.
    """
    if mode not in PROJECTION_MODES:
        raise LBProjectionError(f"unknown projection mode {mode!r}")
    local = shape.copy()
    local.Placement = job_plane.inverse().multiply(local.Placement)

    if not local.Faces:
        try:
            return _flatten_planar(local, _fallback_normal(shape, job_plane))
        except LBProjectionError:
            if mode != "Direction":
                raise
        return _project(local, _local_direction(direction, job_plane))
    if mode == "Face":
        if local.Solids:
            raise LBProjectionError("Face mode needs face sources, not a whole solid")
        wires: list[Part.Wire] = []
        for face in local.Faces:
            if face.findPlane() is None:
                raise LBProjectionError("Face mode needs planar faces")
            wires.extend(_flatten_planar(Part.Compound([face.OuterWire]), None, face))
            for hole in face.Wires:
                if not hole.isSame(face.OuterWire):
                    wires.extend(_flatten_planar(Part.Compound([hole]), None, face))
        return wires
    if mode == "Direction":
        return _project(local, _local_direction(direction, job_plane))
    return _section(local, section_height)


class LBProjectionError(ValueError):
    """A shape cannot be flattened into the job plane in the requested mode."""


_PARALLEL = 1.0 - 1e-9
_LINEAR_TOL = 1e-7
_FUSE_TOL = 1e-4  # mm; merges edges HLR reports twice (e.g. a pocket's rim and floor)


def _to_plane_rotation(normal: FreeCAD.Vector) -> FreeCAD.Rotation:
    """Smallest rotation laying a plane with ``normal`` flat; identity when already flat.

    A face pointing down (anti-parallel) is flat already, so it is not mirrored.
    """
    n = FreeCAD.Vector(normal).normalize()
    if abs(n.z) >= _PARALLEL:
        return FreeCAD.Rotation()
    return FreeCAD.Rotation(n, FreeCAD.Vector(0, 0, 1))


def _drop_to_z0(shape: Part.Shape, rotation: FreeCAD.Rotation) -> Part.Shape:
    """Rotate about the origin, then translate so the (now flat) shape sits at z = 0."""
    out = shape.copy()
    out.Placement = FreeCAD.Placement(FreeCAD.Vector(), rotation).multiply(out.Placement)
    bb = out.BoundBox
    if bb.ZLength > 1e-6 * max(1.0, bb.DiagonalLength):
        raise LBProjectionError("geometry is not planar")
    out.translate(FreeCAD.Vector(0, 0, -(bb.ZMin + bb.ZMax) / 2))
    return out


def _flatten_planar(
    shape: Part.Shape, normal: FreeCAD.Vector | None, face: Part.Face | None = None
) -> list[Part.Wire]:
    """Lay planar geometry flat in the job plane (FR-043) and return its wires."""
    plane = (face or shape).findPlane()
    if plane is not None:
        normal = plane.Axis
    elif normal is None:
        normal = FreeCAD.Vector(0, 0, 1)  # collinear edges: only valid if already flat
    flat = _drop_to_z0(shape, _to_plane_rotation(normal))
    return _wires_from_edges(flat.Edges)


def _fallback_normal(shape: Part.Shape, job_plane: FreeCAD.Placement) -> FreeCAD.Vector:
    """Normal of a sketch's own plane (its Placement Z), used when its edges are collinear."""
    rotation = job_plane.Rotation.inverted().multiply(shape.Placement.Rotation)
    return rotation.multVec(FreeCAD.Vector(0, 0, 1))


def _local_direction(
    direction: FreeCAD.Vector | None, job_plane: FreeCAD.Placement
) -> FreeCAD.Vector:
    if direction is None or direction.Length < _LINEAR_TOL:
        return FreeCAD.Vector(0, 0, 1)
    return job_plane.Rotation.inverted().multVec(FreeCAD.Vector(direction)).normalize()


def _project(shape: Part.Shape, direction: FreeCAD.Vector) -> list[Part.Wire]:
    """Parallel projection along ``direction`` with OCC hidden-line removal (D-013).

    Keeps visible sharp edges and visible silhouettes. Smooth (tangent) edges are dropped:
    they are not cut lines on a laser part.
    """
    n = FreeCAD.Vector(direction).normalize()
    if n.z <= -_PARALLEL:
        rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)  # bottom view, deterministic
    elif n.z >= _PARALLEL:
        rotation = FreeCAD.Rotation()
    else:
        rotation = FreeCAD.Rotation(n, FreeCAD.Vector(0, 0, 1))
    viewed = shape.copy()
    viewed.Placement = FreeCAD.Placement(FreeCAD.Vector(), rotation).multiply(viewed.Placement)

    algo = Part.HLRBRep_Algo()
    algo.add(viewed)
    algo.setProjector(Origin=(0, 0, 0), ZDir=(0, 0, 1), XDir=(1, 0, 0))
    algo.update()
    algo.hide()
    hlr = Part.HLRToShape(algo)
    edges: list[Part.Edge] = []
    for part in (hlr.vCompound(), hlr.outLineVCompound()):
        if part is not None and not part.isNull():
            edges.extend(e for e in part.Edges if e.Length > _LINEAR_TOL)
    if not edges:
        return []
    if len(edges) > 1:
        # HLR does not remove superimposed lines; a fuzzy general fuse merges them.
        edges = edges[0].fuse(edges[1:], _FUSE_TOL).Edges
    flat = _drop_to_z0(Part.Compound(edges), FreeCAD.Rotation())
    return _wires_from_edges(flat.Edges)


def _section(shape: Part.Shape, height: float) -> list[Part.Wire]:
    """Slice at ``height`` above the job plane and drop the cut to z = 0."""
    wires = shape.slice(FreeCAD.Vector(0, 0, 1), float(height))
    out = []
    for wire in wires:
        moved = wire.copy()
        moved.translate(FreeCAD.Vector(0, 0, -float(height)))
        out.append(moved)
    return out


def _wires_from_edges(edges: Sequence[Part.Edge]) -> list[Part.Wire]:
    """Chain edges into wires; open chains are kept so validation can report them."""
    return [Part.Wire(group) for group in Part.sortEdges(list(edges), 1e-5)]


def apply_offset(wires: list[Part.Wire], offset: FreeCAD.Placement) -> list[Part.Wire]:
    """Apply an operation's placement offset (x, y, rotation about Z only) (FR-046).

    Z translation and tilt in ``offset`` are ignored so the wires stay in the job plane.
    """
    yaw = offset.Rotation.toEuler()[0]
    flat = FreeCAD.Placement(
        FreeCAD.Vector(offset.Base.x, offset.Base.y, 0),
        FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), yaw),
    )
    out = []
    for wire in wires:
        moved = wire.copy()
        moved.Placement = flat.multiply(moved.Placement)
        out.append(moved)
    return out
