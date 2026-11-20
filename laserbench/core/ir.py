# SPDX-License-Identifier: LGPL-2.1-or-later
"""LaserBench Intermediate Representation (IR): the machine-neutral laser job.

This module is the executable form of ``docs/IR_SCHEMA.md``. The two must match
exactly. Field names and semantics are a frozen contract: changing them needs a
coordinator-approved entry in ``docs/DECISIONS.md`` (CLAUDE.md hard rule 2).

Conventions (details in IR_SCHEMA.md §2):

* Units are millimetres. Angles are not stored; arcs are centre + direction.
* Coordinates are in the *machine frame* of ``IRJob.machine`` (origin corner or
  galvo field centre).
* Serialisation is canonical: fixed key order, floats rounded to 4 decimals,
  ``-0.0`` normalised to ``0.0``, settings keys sorted. The same job always
  produces byte-identical JSON (NFR-002).

Standard library only (NFR-001).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1
UNITS = "mm"
PRECISION = 4
# Endpoints closer than this are the same point (closed-path check, IR_SCHEMA §2.3).
POINT_TOLERANCE = 1e-4

OP_TYPES = ("cut", "score", "fill")
KERF_MODES = ("auto", "outside", "inside", "none")
MACHINE_KINDS = ("gantry", "galvo")
GANTRY_ORIGINS = ("front-left", "front-right", "rear-left", "rear-right")
GALVO_ORIGINS = ("center",)
SEGMENT_KINDS = ("line", "arc", "poly")
PATH_KINDS = ("vector",)
# Reserved for raster engraving (OS-2, ARCHITECTURE §8). Rejected by schema v1 loaders.
RESERVED_PATH_KINDS = ("image",)
SEVERITIES = ("error", "warning")

#: Issue codes and their fixed severity (IR_SCHEMA §3.8). Implemented by core/validate.py
#: and the fc pipeline; listed here so every producer and consumer agrees on the set.
ISSUE_CODES: dict[str, str] = {
    "OUT_OF_BOUNDS": "error",        # FR-061
    "OPEN_CONTOUR": "warning",       # FR-062
    "FILL_NO_REGION": "error",       # FR-063
    "SMALLER_THAN_KERF": "warning",  # FR-064
    "KERF_COLLAPSE": "warning",      # FR-064, G-03
    "BROKEN_SOURCE": "error",        # FR-065
    "SELF_INTERSECTION": "warning",  # FR-066
    "EMPTY_OPERATION": "warning",    # enabled operation produced no geometry
    "GEOMETRY_ERROR": "error",       # hard failure while building an operation (D-009)
}

_COLOUR_RE = re.compile(r"^#[0-9a-f]{6}$")

Point = tuple[float, float]
SettingValue = str | int | float | bool


class IRError(ValueError):
    """The data does not satisfy the IR schema."""


class IRVersionError(IRError):
    """The data declares a schema_version this code does not read."""


# ---------------------------------------------------------------------------
# Canonical number handling
# ---------------------------------------------------------------------------


def _num(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise IRError(f"{where}: expected a number, got {type(value).__name__}")
    x = float(value)
    if not math.isfinite(x):
        raise IRError(f"{where}: number must be finite, got {x!r}")
    # Adding 0.0 turns -0.0 into 0.0 so output never contains "-0.0".
    return round(x, PRECISION) + 0.0


def _point(value: Any, where: str) -> Point:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise IRError(f"{where}: expected a point [x, y]")
    return (_num(value[0], f"{where}[0]"), _num(value[1], f"{where}[1]"))


def _str(value: Any, where: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise IRError(f"{where}: expected a string, got {type(value).__name__}")
    if not allow_empty and not value:
        raise IRError(f"{where}: must not be empty")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise IRError(f"{where}: expected true/false, got {type(value).__name__}")
    return value


def _int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IRError(f"{where}: expected an integer, got {type(value).__name__}")
    return value


def _choice(value: Any, choices: tuple[str, ...], where: str) -> str:
    if value not in choices:
        raise IRError(f"{where}: {value!r} is not one of {', '.join(choices)}")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list | tuple):
        raise IRError(f"{where}: expected a list")
    return list(value)


def _fields(data: Any, where: str, required: tuple[str, ...], optional: tuple[str, ...] = ()
            ) -> Mapping[str, Any]:
    """Check that ``data`` is an object with exactly the allowed keys."""
    if not isinstance(data, Mapping):
        raise IRError(f"{where}: expected an object")
    missing = [k for k in required if k not in data]
    if missing:
        raise IRError(f"{where}: missing field(s) {', '.join(missing)}")
    unknown = sorted(set(data) - set(required) - set(optional))
    if unknown:
        raise IRError(f"{where}: unknown field(s) {', '.join(unknown)}")
    return data


def _setting(value: Any, where: str) -> SettingValue:
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _num(value, where)
    raise IRError(f"{where}: settings values must be string, number or boolean")


def _same_point(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) <= POINT_TOLERANCE and abs(a[1] - b[1]) <= POINT_TOLERANCE


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@dataclass
class IRSegment:
    """One piece of a path. Its start is the previous segment's end (or the path start).

    * ``line``: straight to ``end``.
    * ``arc``: circular arc to ``end`` around ``center``; ``ccw`` gives the direction in
      the machine frame. An arc whose end equals its start is a full circle.
    * ``poly``: polyline through ``points`` (intermediate vertices) then to ``end``.
      Used for curves approximated within the chord tolerance (FR-051).
    """

    kind: str
    end: Point
    center: Point | None = None
    ccw: bool | None = None
    points: list[Point] | None = None

    def __post_init__(self) -> None:
        _choice(self.kind, SEGMENT_KINDS, "segment.kind")
        self.end = _point(self.end, "segment.end")
        if self.kind == "arc":
            if self.center is None or self.ccw is None:
                raise IRError("arc segment needs center and ccw")
            self.center = _point(self.center, "segment.center")
            self.ccw = _bool(self.ccw, "segment.ccw")
        elif self.center is not None or self.ccw is not None:
            raise IRError(f"{self.kind} segment must not have center/ccw")
        if self.kind == "poly":
            if self.points is None:
                raise IRError("poly segment needs points")
            self.points = [
                _point(p, f"segment.points[{i}]")
                for i, p in enumerate(_list(self.points, "segment.points"))
            ]
        elif self.points is not None:
            raise IRError(f"{self.kind} segment must not have points")

    @classmethod
    def line(cls, end: Point) -> IRSegment:
        return cls("line", end)

    @classmethod
    def arc(cls, end: Point, center: Point, ccw: bool) -> IRSegment:
        return cls("arc", end, center=center, ccw=ccw)

    @classmethod
    def poly(cls, points: list[Point], end: Point) -> IRSegment:
        return cls("poly", end, points=list(points))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        if self.kind == "arc":
            assert self.center is not None
            d["center"] = list(self.center)
            d["ccw"] = self.ccw
        elif self.kind == "poly":
            assert self.points is not None
            d["points"] = [list(p) for p in self.points]
        d["end"] = list(self.end)
        return d

    @classmethod
    def from_dict(cls, data: Any) -> IRSegment:
        kind = _fields(data, "segment", ("kind",), ("end", "center", "ccw", "points"))["kind"]
        kind = _choice(kind, SEGMENT_KINDS, "segment.kind")
        required = {"line": ("kind", "end"), "arc": ("kind", "center", "ccw", "end"),
                    "poly": ("kind", "points", "end")}[kind]
        d = _fields(data, f"{kind} segment", required)
        return cls(kind, d["end"], center=d.get("center"), ccw=d.get("ccw"),
                   points=d.get("points"))


@dataclass
class IRPath:
    """A connected chain of segments starting at ``start``.

    ``closed`` paths end where they start (within POINT_TOLERANCE).
    """

    start: Point
    segments: list[IRSegment]
    closed: bool = False
    kind: str = "vector"

    def __post_init__(self) -> None:
        if self.kind in RESERVED_PATH_KINDS:
            raise IRError(f"path kind {self.kind!r} is reserved and not supported in schema "
                          f"v{SCHEMA_VERSION}")
        _choice(self.kind, PATH_KINDS, "path.kind")
        self.start = _point(self.start, "path.start")
        self.closed = _bool(self.closed, "path.closed")
        self.segments = list(self.segments)
        if not self.segments:
            raise IRError("path needs at least one segment")
        for s in self.segments:
            if not isinstance(s, IRSegment):
                raise IRError("path.segments must contain IRSegment objects")
        if self.closed and not _same_point(self.segments[-1].end, self.start):
            raise IRError(f"closed path ends at {self.segments[-1].end}, "
                          f"not at its start {self.start}")

    @property
    def end(self) -> Point:
        return self.segments[-1].end

    def iter_segments(self) -> Iterator[tuple[Point, IRSegment]]:
        """Yield ``(segment_start, segment)`` pairs."""
        current = self.start
        for seg in self.segments:
            yield current, seg
            current = seg.end

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "closed": self.closed,
            "start": list(self.start),
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, data: Any) -> IRPath:
        d = _fields(data, "path", ("kind", "closed", "start", "segments"))
        segments = [IRSegment.from_dict(s) for s in _list(d["segments"], "path.segments")]
        return cls(start=d["start"], segments=segments, closed=d["closed"], kind=d["kind"])


@dataclass
class IRRegion:
    """A closed area for Fill operations: one outer boundary and zero or more holes."""

    outer: IRPath
    holes: list[IRPath] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.holes = list(self.holes)
        for i, p in enumerate([self.outer, *self.holes]):
            if not isinstance(p, IRPath):
                raise IRError("region boundaries must be IRPath objects")
            if not p.closed:
                where = "outer" if i == 0 else f"holes[{i - 1}]"
                raise IRError(f"region.{where} must be a closed path")

    def to_dict(self) -> dict[str, Any]:
        return {"outer": self.outer.to_dict(), "holes": [h.to_dict() for h in self.holes]}

    @classmethod
    def from_dict(cls, data: Any) -> IRRegion:
        d = _fields(data, "region", ("outer", "holes"))
        return cls(outer=IRPath.from_dict(d["outer"]),
                   holes=[IRPath.from_dict(h) for h in _list(d["holes"], "region.holes")])


@dataclass
class IRBounds:
    """Axis-aligned bounding box in the machine frame."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        self.min_x = _num(self.min_x, "bounds.min_x")
        self.min_y = _num(self.min_y, "bounds.min_y")
        self.max_x = _num(self.max_x, "bounds.max_x")
        self.max_y = _num(self.max_y, "bounds.max_y")
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise IRError("bounds: min must not exceed max")

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def to_dict(self) -> dict[str, Any]:
        return {"min_x": self.min_x, "min_y": self.min_y,
                "max_x": self.max_x, "max_y": self.max_y}

    @classmethod
    def from_dict(cls, data: Any) -> IRBounds:
        d = _fields(data, "bounds", ("min_x", "min_y", "max_x", "max_y"))
        return cls(d["min_x"], d["min_y"], d["max_x"], d["max_y"])


# ---------------------------------------------------------------------------
# Job structure
# ---------------------------------------------------------------------------


@dataclass
class IRMachine:
    """Snapshot of the machine profile the job was built for (FR-010, FR-011)."""

    id: str
    name: str
    kind: str
    width: float
    height: float
    origin: str

    def __post_init__(self) -> None:
        _str(self.id, "machine.id", allow_empty=False)
        _str(self.name, "machine.name")
        _choice(self.kind, MACHINE_KINDS, "machine.kind")
        self.width = _num(self.width, "machine.width")
        self.height = _num(self.height, "machine.height")
        if self.width <= 0 or self.height <= 0:
            raise IRError("machine: width and height must be positive")
        origins = GALVO_ORIGINS if self.kind == "galvo" else GANTRY_ORIGINS
        _choice(self.origin, origins, f"machine.origin ({self.kind})")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "width": self.width, "height": self.height, "origin": self.origin}

    @classmethod
    def from_dict(cls, data: Any) -> IRMachine:
        d = _fields(data, "machine", ("id", "name", "kind", "width", "height", "origin"))
        return cls(**d)


@dataclass
class IRMaterial:
    """Snapshot of the material preset the job was built for (FR-020)."""

    id: str
    name: str
    thickness: float
    kerf: float

    def __post_init__(self) -> None:
        _str(self.id, "material.id", allow_empty=False)
        _str(self.name, "material.name")
        self.thickness = _num(self.thickness, "material.thickness")
        self.kerf = _num(self.kerf, "material.kerf")
        if self.thickness < 0 or self.kerf < 0:
            raise IRError("material: thickness and kerf must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name,
                "thickness": self.thickness, "kerf": self.kerf}

    @classmethod
    def from_dict(cls, data: Any) -> IRMaterial:
        d = _fields(data, "material", ("id", "name", "thickness", "kerf"))
        return cls(**d)


@dataclass
class IRIssue:
    """A validation finding (FR-060). Severity is fixed per code (ISSUE_CODES)."""

    code: str
    message: str
    operation_id: str | None = None
    location: Point | None = None
    severity: str = ""

    def __post_init__(self) -> None:
        if self.code not in ISSUE_CODES:
            raise IRError(f"issue.code: unknown code {self.code!r}")
        expected = ISSUE_CODES[self.code]
        if self.severity == "":
            self.severity = expected
        _choice(self.severity, SEVERITIES, "issue.severity")
        if self.severity != expected:
            raise IRError(f"issue {self.code} has severity {expected}, not {self.severity}")
        _str(self.message, "issue.message", allow_empty=False)
        if self.operation_id is not None:
            _str(self.operation_id, "issue.operation_id", allow_empty=False)
        if self.location is not None:
            self.location = _point(self.location, "issue.location")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "operation_id": self.operation_id,
            "location": None if self.location is None else list(self.location),
        }

    @classmethod
    def from_dict(cls, data: Any) -> IRIssue:
        d = _fields(data, "issue", ("code", "severity", "message", "operation_id", "location"))
        return cls(code=d["code"], message=d["message"], operation_id=d["operation_id"],
                   location=d["location"], severity=d["severity"])


@dataclass
class IROperation:
    """One laser action over a set of geometry (FR-040, FR-044, FR-045).

    ``settings`` are the merged preset + override values, passed through verbatim
    (FR-021). Cut and Score carry ``paths``. Fill carries ``regions``; if LaserBench
    hatched it (FR-052) then ``hatched`` is true and the hatch lines are in ``paths``.
    """

    id: str
    label: str
    type: str
    order: int
    colour: str
    settings: dict[str, SettingValue] = field(default_factory=dict)
    kerf_mode: str = "none"
    hatched: bool = False
    paths: list[IRPath] = field(default_factory=list)
    regions: list[IRRegion] = field(default_factory=list)

    def __post_init__(self) -> None:
        _str(self.id, "operation.id", allow_empty=False)
        _str(self.label, "operation.label")
        _choice(self.type, OP_TYPES, "operation.type")
        self.order = _int(self.order, "operation.order")
        self.colour = _str(self.colour, "operation.colour").lower()
        if not _COLOUR_RE.match(self.colour):
            raise IRError(f"operation.colour: {self.colour!r} is not #rrggbb")
        if not isinstance(self.settings, Mapping):
            raise IRError("operation.settings: expected an object")
        self.settings = {
            _str(k, "operation.settings key", allow_empty=False):
                _setting(v, f"operation.settings[{k!r}]")
            for k, v in sorted(self.settings.items())
        }
        _choice(self.kerf_mode, KERF_MODES, "operation.kerf_mode")
        self.hatched = _bool(self.hatched, "operation.hatched")
        if self.hatched and self.type != "fill":
            raise IRError("operation.hatched is only allowed on fill operations")
        self.paths = list(self.paths)
        self.regions = list(self.regions)
        if self.regions and self.type != "fill":
            raise IRError(f"{self.type} operation must not have regions")
        if self.type == "fill" and self.paths and not self.hatched:
            raise IRError("fill operation has paths but is not hatched")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "order": self.order,
            "colour": self.colour,
            "kerf_mode": self.kerf_mode,
            "hatched": self.hatched,
            "settings": dict(self.settings),
            "paths": [p.to_dict() for p in self.paths],
            "regions": [r.to_dict() for r in self.regions],
        }

    @classmethod
    def from_dict(cls, data: Any) -> IROperation:
        d = _fields(data, "operation", ("id", "label", "type", "order", "colour", "kerf_mode",
                                        "hatched", "settings", "paths", "regions"))
        return cls(
            id=d["id"], label=d["label"], type=d["type"], order=d["order"],
            colour=d["colour"], settings=d["settings"], kerf_mode=d["kerf_mode"],
            hatched=d["hatched"],
            paths=[IRPath.from_dict(p) for p in _list(d["paths"], "operation.paths")],
            regions=[IRRegion.from_dict(r) for r in _list(d["regions"], "operation.regions")],
        )


@dataclass
class IRJob:
    """A complete laser job: one machine, one material, ordered operations (FR-030, FR-070)."""

    name: str
    machine: IRMachine
    material: IRMaterial
    operations: list[IROperation] = field(default_factory=list)
    bounds: IRBounds | None = None
    issues: list[IRIssue] = field(default_factory=list)
    source_document: str = ""
    generator: str = "LaserBench"

    def __post_init__(self) -> None:
        _str(self.name, "job.name")
        _str(self.source_document, "job.source_document")
        _str(self.generator, "job.generator")
        if not isinstance(self.machine, IRMachine):
            raise IRError("job.machine must be an IRMachine")
        if not isinstance(self.material, IRMaterial):
            raise IRError("job.material must be an IRMaterial")
        self.operations = list(self.operations)
        self.issues = list(self.issues)
        ids = [op.id for op in self.operations]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise IRError(f"duplicate operation id(s): {', '.join(dupes)}")
        known = set(ids)
        for issue in self.issues:
            if issue.operation_id is not None and issue.operation_id not in known:
                raise IRError(f"issue {issue.code} refers to unknown operation "
                              f"{issue.operation_id!r}")

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "units": UNITS,
            "generator": self.generator,
            "name": self.name,
            "source_document": self.source_document,
            "machine": self.machine.to_dict(),
            "material": self.material.to_dict(),
            "bounds": None if self.bounds is None else self.bounds.to_dict(),
            "operations": [op.to_dict() for op in self.operations],
            "issues": [i.to_dict() for i in self.issues],
        }

    @classmethod
    def from_dict(cls, data: Any) -> IRJob:
        if not isinstance(data, Mapping):
            raise IRError("job: expected an object")
        check_schema_version(data)
        d = _fields(data, "job", ("schema_version", "units", "generator", "name",
                                  "source_document", "machine", "material", "bounds",
                                  "operations", "issues"))
        if d["units"] != UNITS:
            raise IRError(f"job.units: expected {UNITS!r}, got {d['units']!r}")
        return cls(
            name=d["name"],
            machine=IRMachine.from_dict(d["machine"]),
            material=IRMaterial.from_dict(d["material"]),
            operations=[IROperation.from_dict(o) for o in _list(d["operations"],
                                                                 "job.operations")],
            bounds=None if d["bounds"] is None else IRBounds.from_dict(d["bounds"]),
            issues=[IRIssue.from_dict(i) for i in _list(d["issues"], "job.issues")],
            source_document=d["source_document"],
            generator=d["generator"],
        )

    def to_json(self) -> str:
        """Canonical JSON text: compact, UTF-8 safe, newline-terminated (NFR-002)."""
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> IRJob:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise IRError(f"not valid JSON: {exc}") from exc
        return cls.from_dict(data)


def check_schema_version(data: Mapping[str, Any]) -> None:
    """Refuse data from any other schema version explicitly (NFR-007).

    Schema v1 has no predecessors, so there is nothing to migrate yet. When v2
    exists, migrations from older versions go here; newer versions are always refused.
    """
    version = data.get("schema_version")
    if version is None:
        raise IRVersionError("missing schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise IRVersionError(f"schema_version must be an integer, got {version!r}")
    if version > SCHEMA_VERSION:
        raise IRVersionError(f"schema_version {version} is newer than this LaserBench reads "
                             f"({SCHEMA_VERSION}); update LaserBench")
    if version < SCHEMA_VERSION:
        raise IRVersionError(f"schema_version {version} is older than {SCHEMA_VERSION} and "
                             "no migration exists")
