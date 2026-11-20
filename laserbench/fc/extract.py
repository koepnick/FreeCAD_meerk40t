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
    """
    raise NotImplementedError("G-02")


def apply_offset(wires: list[Part.Wire], offset: FreeCAD.Placement) -> list[Part.Wire]:
    """Apply an operation's placement offset (x, y, rotation about Z only) (FR-046)."""
    raise NotImplementedError("G-02")
