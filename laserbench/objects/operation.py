# SPDX-License-Identifier: LGPL-2.1-or-later
"""LaserOperation FeaturePython object (FR-040, FR-044, FR-045). Task W-02.

Properties: ARCHITECTURE.md §4.1. App side only: no Qt, no FreeCADGui (NFR-006).

``execute`` runs the geometry half of the pipeline (ARCHITECTURE §3): resolve sources →
flatten into the job plane → placement offset → kerf (Cut only) → array → IR. The result
is stored as an *IR fragment*: an ``IROperation`` in the job frame whose ``settings`` hold
only this operation's overrides (core/pipeline.py merges them with the preset), plus the
issues raised while building it. LaserJob (W-03) reads fragments with ``read_fragment``.

The job plane and kerf come from the LaserJob that lists this operation. An operation that
belongs to no job uses the global XY plane and no kerf, so it still previews.
"""

from __future__ import annotations

import json
from typing import Any

import FreeCAD
import Part

from laserbench.core.ir import IRIssue, IROperation
from laserbench.fc import extract, kerf, to_ir

OP_TYPES = ("Cut", "Score", "Fill")
PROJECTION_MODES = extract.PROJECTION_MODES
KERF_MODES = kerf.KERF_MODES

#: D-007: overrides that get a real, expression-bindable float property on demand.
EXPRESSION_OVERRIDES = ("power", "speed", "passes", "frequency")
OVERRIDES_GROUP = "Overrides"

#: FR-045: colours given to new operations in turn. Saturated and far apart so each
#: operation gets a distinct stroke colour in the SVG (FR-071).
PALETTE = ("#ff0000", "#0000ff", "#00a000", "#ff00ff", "#00a0a0", "#ff8000", "#8000ff",
           "#a0a000")

JOB_TYPE = "LaserBench::LaserJob"
FRAGMENT_VERSION = 1


def _tr(text: str) -> str:
    # QT_TRANSLATE_NOOP equivalent that needs no Qt: property tooltips are translated by
    # FreeCAD's property editor using the "App::Property" context.
    return text


# (type, name, group, tooltip)
_PROPERTIES: tuple[tuple[str, str, str, str], ...] = (
    ("App::PropertyEnumeration", "OpType", "Operation",
     _tr("Cut through, score/engrave along lines, or fill closed regions")),
    ("App::PropertyLinkSubList", "Sources", "Operation",
     _tr("Sketches, faces, edges, solids or Bodies this operation takes its geometry from")),
    ("App::PropertyBool", "Enabled", "Operation",
     _tr("Disabled operations are left out of the job and its exports")),
    ("App::PropertyInteger", "Order", "Operation",
     _tr("Operations run in ascending order")),
    ("App::PropertyColor", "Colour", "Operation",
     _tr("Stroke colour in the preview and the exported SVG")),
    ("App::PropertyEnumeration", "ProjectionMode", "Projection",
     _tr("How solids and faces become 2D: a planar face, a projection, or a section")),
    ("App::PropertyVector", "ProjectionDirection", "Projection",
     _tr("Direction mode: view direction, from the model towards the viewer. "
         "Zero means the job plane's normal (a top view)")),
    ("App::PropertyDistance", "SectionHeight", "Projection",
     _tr("Section mode: height of the cut above the job plane")),
    ("App::PropertyEnumeration", "KerfMode", "Kerf",
     _tr("Cut only. Auto offsets outlines outward and holes inward by half the kerf")),
    ("App::PropertyPlacement", "Offset", "Layout",
     _tr("Moves this operation's geometry within the job (x, y and rotation about Z)")),
    ("App::PropertyIntegerList", "ArrayCount", "Layout",
     _tr("Repeat the geometry [columns, rows] times")),
    ("App::PropertyVector", "ArraySpacing", "Layout",
     _tr("Distance between array copies in x and y")),
    ("App::PropertyMap", "SettingsOverrides", "Overrides",
     _tr("Laser settings that replace the material preset's values for this operation")),
    ("App::PropertyString", "IRFragment", "Internal",
     _tr("Computed IR for this operation (not saved)")),
)


class LaserOperation:
    """Proxy for a ``Part::FeaturePython`` laser operation."""

    Type = "LaserBench::LaserOperation"

    def __init__(self, obj: FreeCAD.DocumentObject) -> None:
        obj.Proxy = self
        self.setup_properties(obj)

    def setup_properties(self, obj: FreeCAD.DocumentObject) -> None:
        """Add any missing properties. Also called on restore, so new versions can add some."""
        existing = set(obj.PropertiesList)
        for prop_type, name, group, tip in _PROPERTIES:
            if name in existing:
                continue
            # Prop_Transient (2): IRFragment's content is a cache and is not saved (D-008).
            obj.addProperty(prop_type, name, group, tip, 2 if name == "IRFragment" else 0)
            if name == "OpType":
                obj.OpType = list(OP_TYPES)
            elif name == "ProjectionMode":
                obj.ProjectionMode = list(PROJECTION_MODES)
            elif name == "KerfMode":
                obj.KerfMode = list(KERF_MODES)
            elif name == "Enabled":
                obj.Enabled = True
            elif name == "ArrayCount":
                obj.ArrayCount = [1, 1]
        obj.setEditorMode("IRFragment", 2)

    def execute(self, obj: FreeCAD.DocumentObject) -> None:
        """Extract → offset → kerf → to IR; store IRFragment and the preview Shape.

        User-correctable problems (a broken link, a face that can't be projected, a loop
        that collapses under kerf) become issues in the fragment. Only a hard failure,
        such as every source being broken, raises so FreeCAD marks the object (D-009).
        """
        op_id = obj.Name
        job_plane, kerf_value = _job_context(obj)
        issues: list[IRIssue] = []
        wires: list[Part.Wire] = []
        failures = 0
        sources = _source_links(obj)
        for link_obj, subnames in sources:
            for sub in list(subnames) or [""]:
                try:
                    wires.extend(self._flatten_source(obj, link_obj, sub, job_plane))
                except extract.LBSourceError as exc:
                    failures += 1
                    issues.append(IRIssue(code="BROKEN_SOURCE", message=str(exc),
                                          operation_id=op_id))
                except extract.LBProjectionError as exc:
                    failures += 1
                    issues.append(IRIssue(
                        code="GEOMETRY_ERROR", operation_id=op_id,
                        message=f"{_link_name(link_obj, sub)}: {exc}"))

        try:
            wires = extract.apply_offset(wires, obj.Offset)
            if obj.OpType == "Cut":
                wires, kerf_issues = kerf.compensate(wires, kerf_value, obj.KerfMode, op_id)
                issues.extend(kerf_issues)
            wires = _array(wires, obj.ArrayCount, obj.ArraySpacing)
            fragment = self._fragment(obj, wires)
        except Exception as exc:  # noqa: BLE001 - recorded, then raised as a hard error
            issues.append(IRIssue(code="GEOMETRY_ERROR", operation_id=op_id,
                                  message=f"{obj.Label}: {exc}"))
            _store(obj, self._fragment(obj, []), issues, Part.Shape())
            raise FreeCAD.Base.FreeCADError(f"{obj.Label}: {exc}") from exc

        _store(obj, fragment, issues, _preview(wires, job_plane))
        if sources and failures == _count_links(sources):
            raise FreeCAD.Base.FreeCADError(
                f"{obj.Label}: none of its sources could be used ({issues[0].message})")

    def _flatten_source(self, obj: FreeCAD.DocumentObject, link_obj: Any, sub: str,
                        job_plane: FreeCAD.Placement) -> list[Part.Wire]:
        [(_, _, shape)] = extract.resolve_sources([(link_obj, [sub] if sub else [])])
        direction = FreeCAD.Vector(obj.ProjectionDirection)
        return extract.to_job_plane(
            shape, obj.ProjectionMode, job_plane,
            direction=None if direction.Length < 1e-12 else direction,
            section_height=obj.SectionHeight.Value,
        )

    def _fragment(self, obj: FreeCAD.DocumentObject, wires: list[Part.Wire]) -> IROperation:
        op_type = obj.OpType.lower()
        paths, regions = [], []
        if op_type == "fill":
            regions = to_ir.wires_to_regions(wires)
        else:
            paths = to_ir.wires_to_paths(wires)
        return IROperation(
            id=obj.Name,
            label=obj.Label,
            type=op_type,
            order=obj.Order,
            colour=colour_hex(obj.Colour),
            settings=override_settings(obj),
            kerf_mode=obj.KerfMode.lower() if op_type == "cut" else "none",
            paths=paths,
            regions=regions,
        )

    def onDocumentRestored(self, obj: FreeCAD.DocumentObject) -> None:  # noqa: N802
        self.setup_properties(obj)

    def dumps(self) -> dict[str, Any] | None:
        return None

    def loads(self, state: dict[str, Any] | None) -> None:
        return None


def normalise_links(sources: list[Any]) -> list[Any]:
    """Make whole-object links survive PropertyLinkSubList assignment.

    The property silently drops ``(obj, [])``; ``(obj, "")`` means the whole object.
    """
    out: list[Any] = []
    for item in sources:
        if isinstance(item, tuple | list) and len(item) == 2:
            link, subs = item
            if isinstance(subs, str):
                out.append((link, subs))
            else:
                out.append((link, list(subs) if subs else ""))
        else:
            out.append((item, ""))
    return out


def _source_links(obj: FreeCAD.DocumentObject) -> list[tuple[Any, tuple[str, ...]]]:
    return [(link, tuple(subs)) for link, subs in obj.Sources]


def _link_name(link_obj: Any, sub: str) -> str:
    try:
        label = link_obj.Label
    except Exception:  # noqa: BLE001 - a deleted object raises on attribute access
        label = "<missing>"
    return f"{label}.{sub}" if sub else label


def _count_links(sources: list[tuple[Any, tuple[str, ...]]]) -> int:
    return sum(len(subs) or 1 for _, subs in sources)


def _job_context(obj: FreeCAD.DocumentObject) -> tuple[FreeCAD.Placement, float]:
    """Job plane and kerf (mm) from the job that lists ``obj``; defaults without a job."""
    job = find_job(obj)
    if job is None:
        return FreeCAD.Placement(), 0.0
    plane = getattr(job, "JobPlane", None) or FreeCAD.Placement()
    kerf_prop = getattr(job, "Kerf", None)
    return plane, float(getattr(kerf_prop, "Value", kerf_prop or 0.0))


def find_job(obj: FreeCAD.DocumentObject) -> FreeCAD.DocumentObject | None:
    """The LaserJob whose Operations list contains ``obj``, if any."""
    for parent in obj.InList:
        proxy = getattr(parent, "Proxy", None)
        if getattr(proxy, "Type", None) == JOB_TYPE and obj in getattr(parent, "Operations", []):
            return parent
    return None


def _array(wires: list[Part.Wire], count: list[int], spacing: FreeCAD.Vector
           ) -> list[Part.Wire]:
    """Repeat ``wires`` on an nx × ny grid (FR-047, expanded in the IR per D-004)."""
    nx, ny = (max(1, int(c)) for c in (list(count) + [1, 1])[:2])
    if nx == 1 and ny == 1:
        return wires
    out: list[Part.Wire] = []
    for j in range(ny):
        for i in range(nx):
            shift = FreeCAD.Vector(i * spacing.x, j * spacing.y, 0)
            for wire in wires:
                copy = wire.copy()
                copy.translate(shift)
                out.append(copy)
    return out


def _preview(wires: list[Part.Wire], job_plane: FreeCAD.Placement) -> Part.Shape:
    """The operation's wires placed back on the job plane, for the 3D view."""
    if not wires:
        return Part.Shape()
    # Baked into the geometry: Part::Feature replaces a shape's Placement with its own.
    return Part.Compound(wires).transformGeometry(job_plane.toMatrix())


def _store(obj: FreeCAD.DocumentObject, fragment: IROperation, issues: list[IRIssue],
           shape: Part.Shape) -> None:
    obj.IRFragment = json.dumps({
        "fragment_version": FRAGMENT_VERSION,
        "operation": fragment.to_dict(),
        "issues": [i.to_dict() for i in issues],
    }, separators=(",", ":"))
    obj.Shape = shape


def read_fragment(obj: FreeCAD.DocumentObject) -> tuple[IROperation, list[IRIssue]]:
    """The operation's IR fragment and its issues, recomputing it first if the cache is empty.

    The fragment is in the job frame, and its ``settings`` are the overrides only.
    """
    if not obj.IRFragment:
        obj.recompute()
    if not obj.IRFragment:
        raise ValueError(f"{obj.Label} has no IR fragment; recompute failed")
    data = json.loads(obj.IRFragment)
    if data.get("fragment_version") != FRAGMENT_VERSION:
        raise ValueError(f"{obj.Label}: unsupported fragment version")
    return (IROperation.from_dict(data["operation"]),
            [IRIssue.from_dict(i) for i in data["issues"]])


def colour_hex(colour: tuple[float, ...]) -> str:
    """A PropertyColor value (floats 0..1) as ``#rrggbb``."""
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in colour[:3])


def _hex_colour(text: str) -> tuple[float, float, float]:
    return tuple(int(text[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def override_settings(obj: FreeCAD.DocumentObject) -> dict[str, Any]:
    """This operation's setting overrides (FR-044).

    ``SettingsOverrides`` values stay strings: core.settings coerces them when it merges
    with the preset. A D-007 float property, when present, wins over the map entry of the
    same key because it is the one that can follow an expression.
    """
    settings: dict[str, Any] = {k: v for k, v in dict(obj.SettingsOverrides).items() if k}
    for key in EXPRESSION_OVERRIDES:
        name = override_property_name(key)
        if name in obj.PropertiesList:
            settings[key] = float(getattr(obj, name))
    return settings


def override_property_name(key: str) -> str:
    """Property name for a D-007 expression-bindable override (``power`` → ``Power``)."""
    return key.capitalize()


def add_override_property(obj: FreeCAD.DocumentObject, key: str,
                          value: float | None = None) -> str:
    """Create the expression-bindable float override for ``key`` (D-007) and return its name.

    Only ``power``, ``speed``, ``passes`` and ``frequency`` get one; other keys belong in
    ``SettingsOverrides``. The initial value is ``value``, else the map entry, else 0.
    """
    if key not in EXPRESSION_OVERRIDES:
        raise ValueError(f"{key!r} has no float override; use SettingsOverrides")
    name = override_property_name(key)
    if name not in obj.PropertiesList:
        obj.addProperty("App::PropertyFloat", name, OVERRIDES_GROUP,
                        _tr("Overrides the material preset's value; can follow an expression"))
        if value is None:
            raw = dict(obj.SettingsOverrides).get(key, "0")
            try:
                value = float(raw)
            except ValueError:
                value = 0.0
        setattr(obj, name, value)
    elif value is not None:
        setattr(obj, name, value)
    return name


def remove_override_property(obj: FreeCAD.DocumentObject, key: str) -> None:
    """Remove a D-007 float override, so the preset (or map) value applies again."""
    name = override_property_name(key)
    if name in obj.PropertiesList:
        obj.removeProperty(name)


def _operations_in(doc: FreeCAD.Document) -> list[FreeCAD.DocumentObject]:
    return [o for o in doc.Objects
            if getattr(getattr(o, "Proxy", None), "Type", None) == LaserOperation.Type]


def make_operation(
    doc: FreeCAD.Document, op_type: str, sources: list[Any], name: str = "LaserOperation"
) -> FreeCAD.DocumentObject:
    """Create an operation object; ``sources`` is a PropertyLinkSubList value.

    ``op_type`` is ``Cut``, ``Score`` or ``Fill`` (any case). The colour comes from the
    palette and the order follows the operations already in the document (FR-045). The
    caller adds the operation to a job's ``Operations``.
    """
    matches = [t for t in OP_TYPES if t.lower() == op_type.lower()]
    if not matches:
        raise ValueError(f"unknown operation type {op_type!r}; expected one of {OP_TYPES}")
    existing = _operations_in(doc)
    obj = doc.addObject("Part::FeaturePython", name)
    LaserOperation(obj)
    obj.OpType = matches[0]
    obj.Sources = normalise_links(sources)
    obj.Order = max((o.Order for o in existing), default=-1) + 1
    obj.Colour = _hex_colour(PALETTE[len(existing) % len(PALETTE)])
    # View providers arrive in W-05; until then FreeCAD's default one is used.
    return obj
