# IR Schema — LaserBench

Status: **v1, frozen at end of Phase 0** · Owner: coordinator · Code: `laserbench/core/ir.py`

The IR (Intermediate Representation) is the machine-neutral description of one laser job.
Everything downstream (SVG/DXF exporters, validation display, future backends) reads only
the IR. This document and `core/ir.py` must match exactly. Changing a field name or meaning,
or adding an optional field, needs a coordinator-approved entry in `DECISIONS.md`.

---

## 1. Overview

```
IRJob
├── machine: IRMachine         snapshot of the machine profile
├── material: IRMaterial       snapshot of the material preset
├── bounds: IRBounds | null    extent of all geometry
├── operations: [IROperation]  in execution order
│   ├── paths:   [IRPath]      Cut, Score, hatched Fill
│   │   └── segments: [IRSegment]   line | arc | poly
│   └── regions: [IRRegion]    Fill (outer + holes, all closed IRPaths)
└── issues: [IRIssue]          validation findings
```

## 2. Conventions

### 2.1 Units
Millimetres for every length and coordinate. `units` is always `"mm"`; loaders reject anything
else. Conversion to other units happens only in exporters.

### 2.2 Coordinate frame
All coordinates are in the **machine frame** of `job.machine`:

| `machine.kind` | `origin` | (0, 0) is | +x points | +y points |
|---|---|---|---|---|
| gantry | `front-left` | front-left corner of the bed | right | to the rear |
| gantry | `front-right` | front-right corner | left | to the rear |
| gantry | `rear-left` | rear-left corner | right | to the front |
| gantry | `rear-right` | rear-right corner | left | to the front |
| galvo | `center` | centre of the field | right | to the rear |

"Front" is the side the operator stands at; directions are as seen from above. A gantry bed
therefore spans `0 ≤ x ≤ width`, `0 ≤ y ≤ height`. A galvo field spans
`-width/2 ≤ x ≤ width/2`, `-height/2 ≤ y ≤ height/2`. The transform from the FreeCAD job plane
into this frame is `core/coords.py` (task K-02). Mirroring origins (front-right, rear-left)
flip arc direction, and the transform must flip `ccw` accordingly.

### 2.3 Numbers and tolerance
- Every float is rounded to **4 decimal places** when an IR object is constructed, and `-0.0`
  becomes `0.0`. NaN and infinity are rejected.
- Geometry numbers are always floats (`1` becomes `1.0`). Settings keep their type (§3.6).
- Two points within **1e-4 mm** on both axes are the same point (`POINT_TOLERANCE`).

### 2.4 Canonical JSON (NFR-002)
`IRJob.to_json()` produces the canonical form:
- compact separators (`,` and `:`, no spaces, no indentation), UTF-8 (`ensure_ascii=False`),
  one trailing newline;
- object keys in the order listed in §3 (not alphabetical), except `settings`, whose keys are
  sorted;
- list order is meaningful and preserved (operations in execution order, paths in cut order).

The same job always serialises to byte-identical text. Loading and re-dumping is the identity.

### 2.5 Strict loading
`from_dict`/`from_json` reject unknown fields, missing fields, wrong types and out-of-range enum
values with `IRError`. This catches contract drift between producers and consumers early.

---

## 3. Objects

All fields are required in JSON. "null" is written where the table allows it.

### 3.1 IRJob (top level)
| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | `1`. See §6. |
| `units` | string | always `"mm"` |
| `generator` | string | producer name, default `"LaserBench"` |
| `name` | string | job label |
| `source_document` | string | FreeCAD document file name or `""`. No timestamps or absolute paths, so output stays deterministic. |
| `machine` | IRMachine | |
| `material` | IRMaterial | |
| `bounds` | IRBounds \| null | null when there is no geometry or bounds were not computed |
| `operations` | [IROperation] | execution order; `id`s are unique |
| `issues` | [IRIssue] | each `operation_id` (if not null) names an operation in this job |

### 3.2 IRMachine
| Field | Type | Notes |
|---|---|---|
| `id` | string | profile id, non-empty |
| `name` | string | display name |
| `kind` | `"gantry"` \| `"galvo"` | |
| `width`, `height` | float > 0 | bed or field size, mm |
| `origin` | string | gantry: `front-left`, `front-right`, `rear-left`, `rear-right`; galvo: `center` |

### 3.3 IRMaterial
| Field | Type | Notes |
|---|---|---|
| `id` | string | preset id, non-empty |
| `name` | string | |
| `thickness` | float ≥ 0 | mm |
| `kerf` | float ≥ 0 | mm, the value kerf compensation used |

### 3.4 IRBounds
`min_x`, `min_y`, `max_x`, `max_y` (floats, min ≤ max), axis-aligned in the machine frame,
including arc extremes. FR-034 tests compare the preview bounding box against this.

### 3.5 IROperation
| Field | Type | Notes |
|---|---|---|
| `id` | string | stable, unique in the job (the FreeCAD object `Name`) |
| `label` | string | user-visible label |
| `type` | `"cut"` \| `"score"` \| `"fill"` | FR-040 |
| `order` | int | the operation's `Order` property |
| `colour` | string | `#rrggbb`, lowercase |
| `kerf_mode` | `"auto"` \| `"outside"` \| `"inside"` \| `"none"` | what was applied (FR-050); `"none"` for score/fill |
| `hatched` | bool | true only for fill operations hatched by LaserBench (FR-052) |
| `settings` | object | §3.6 |
| `paths` | [IRPath] | cut/score geometry, or hatch lines when `hatched` |
| `regions` | [IRRegion] | fill operations only |

Rules: `regions` must be empty unless `type` is `fill`. A fill operation has `paths` only when
`hatched` is true (its `regions` are kept for reference). Disabled operations are not in the IR.

### 3.6 Settings
The merged preset + override settings (FR-021, FR-044), passed through verbatim. Keys are
non-empty strings, sorted. Values are string, integer, float (rounded per §2.3) or boolean;
nested objects and lists are not allowed. LaserBench itself interprets only `kerf`,
`hatch_interval` and `hatch_angle`. Well-known keys (not required): `power` (%), `speed`
(mm/s), `passes`, `frequency` (kHz), `q_pulse` (ns), `hatch_interval` (mm), `hatch_angle` (deg).

### 3.7 IRPath and IRSegment
**IRPath**
| Field | Type | Notes |
|---|---|---|
| `kind` | `"vector"` | `"image"` is reserved for raster (OS-2); v1 loaders reject it |
| `closed` | bool | if true, the last segment ends at `start` (within tolerance) |
| `start` | [x, y] | |
| `segments` | [IRSegment] | at least one; each starts where the previous one ended |

**IRSegment**, key order as listed:
| `kind` | Fields | Meaning |
|---|---|---|
| `line` | `kind`, `end` | straight line to `end` |
| `arc` | `kind`, `center`, `ccw`, `end` | circular arc around `center` to `end`, counter-clockwise in the machine frame if `ccw`. Radius is the distance from `center` to the start. `end` equal to the start means a full circle. |
| `poly` | `kind`, `points`, `end` | polyline through `points` (intermediate vertices, may be empty) then to `end`. Used for ellipses and B-splines discretised within the chord tolerance (FR-051). |

Fields not listed for a kind must be absent.

### 3.8 IRRegion
`outer`: closed IRPath. `holes`: list of closed IRPaths inside it. Used for Fill.

### 3.9 IRIssue
| Field | Type | Notes |
|---|---|---|
| `code` | string | one of the codes below |
| `severity` | `"error"` \| `"warning"` | fixed by the code |
| `message` | string | non-empty, user-facing, actionable |
| `operation_id` | string \| null | operation it concerns |
| `location` | [x, y] \| null | machine-frame point to zoom to |

| Code | Severity | Requirement |
|---|---|---|
| `OUT_OF_BOUNDS` | error | FR-061 |
| `OPEN_CONTOUR` | warning | FR-062 |
| `FILL_NO_REGION` | error | FR-063 |
| `SMALLER_THAN_KERF` | warning | FR-064 |
| `KERF_COLLAPSE` | warning | FR-064, G-03 (offset loop vanished) |
| `BROKEN_SOURCE` | error | FR-065 |
| `SELF_INTERSECTION` | warning | FR-066 |
| `EMPTY_OPERATION` | warning | enabled operation produced no geometry |
| `GEOMETRY_ERROR` | error | hard failure building an operation (D-009) |

Adding a code is an additive contract change (needs a DECISIONS entry).

---

## 4. Machine profiles and material presets (user data JSON)

Stored in `FreeCAD.getUserAppDataDir()/LaserBench/`. Owned by presets-dev (`core/presets.py`,
task P-01); this section fixes the file format. Same number rules as §2.3; `schema_version`
handling as §6.

`machines.json`
```json
{"schema_version": 1,
 "machines": [
   {"id": "co2", "name": "CO2 gantry", "kind": "gantry",
    "width": 600.0, "height": 400.0, "origin": "rear-left",
    "default_kerf": 0.2,
    "send_command": ["meerk40t", "{svg}"]}
 ]}
```
`id`, `kind`, `width`, `height`, `origin` follow §3.2. `send_command` is an argument list
(never a shell string) with placeholders `{svg}`, `{json}`, `{dxf}`, `{job_name}` (FR-074);
an empty list means no command.

`materials.json`
```json
{"schema_version": 1,
 "materials": [
   {"id": "ply3", "machine_id": "co2", "name": "Birch ply 3 mm",
    "thickness": 3.0, "kerf": 0.2,
    "settings": {"cut": {"power": 65, "speed": 20, "passes": 1},
                 "score": {"power": 20, "speed": 200},
                 "fill": {"power": 30, "speed": 300, "hatch_interval": 0.1}}}
 ]}
```
`settings` maps operation type to an opaque settings object (§3.6). `(machine_id, id)` is unique.

---

## 5. SVG export mapping (FR-071, FR-072)

Implemented by `core/export_svg.py` (task K-06). The MeerK40t additions in §5.1 follow D-006
(proposed; to be confirmed by Q-03).

- Root: `width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}"`, where W×H is the machine
  width×height. One user unit = 1 mm. The first child is `<title>{job name}</title>`.
- The drawing is the bed or field seen from above, **rear edge at the top**. Exporters convert
  machine-frame coordinates (§2.2) to SVG coordinates (y down) with the origin-specific flip.
- One `<g>` per operation, in IR order: `id="op-{id}"`,
  `inkscape:groupmode="layer"`, `inkscape:label="{order} {label} ({type})"`.
- Cut and score: `fill="none"`, `stroke="{colour}"`, hairline `stroke-width="0.025"`.
  Fill (not hatched): `fill="{colour}"`, `stroke="none"`, `fill-rule="evenodd"`, one `<path>`
  per region (outer + holes as subpaths). Hatched fill: stroked like score.
- Each geometry element has `id="op-{id}-{n}"`, n counting from 1 within the operation
  (one per path, or one per region for an unhatched fill).
- Arcs become SVG `A` commands; full circles become two half-arcs.
- Metadata namespace `xmlns:lb="https://github.com/koepnick/FreeCAD_meerk40t/ns/ir/1"`. Each
  operation group carries `lb:type`, `lb:kerf-mode` and `lb:settings` (canonical compact JSON of
  `settings`). The root carries `lb:schema-version` and `lb:machine`.
- Numbers are written with the same 4-decimal rounding, trailing zeros stripped.

### 5.1 MeerK40t operation groups (D-006)
Unless turned off at export, the file also carries one empty top-level `<g>` per operation that
has geometry, before the layers, in IR order. MeerK40t reads these as its operations; other
programs ignore them. Attributes are un-namespaced, as MeerK40t writes them:

| Attribute | Value |
|---|---|
| `id` | `mk-{id}` |
| `type` | `op cut` (cut), `op engrave` (score, hatched fill), `op raster` (unhatched fill) |
| `label` | operation label (id if empty) |
| `color` | operation colour |
| `power` | settings `power` × 10 (per mille), if set |
| `speed` | settings `speed` (mm/s), if set |
| `passes`, `passes_custom="True"` | settings `passes`, if set and ≥ 1 |
| `frequency` | settings `frequency` (kHz), if set |
| `pulse_width`, `pulse_width_enabled="True"` | settings `q_pulse` (ns), galvo only |
| `dpi` | round(25.4 / `hatch_interval`), `op raster` only |
| `output` | `True` |
| `references` | space-separated element ids of the operation |

Settings that are absent or not numbers are left out, so MeerK40t's defaults apply.

---

## 6. Versioning (NFR-007)

`schema_version` is an integer, currently **1**. It changes on any change to this document's
fields or meanings. Loaders call `check_schema_version()`:
- newer than the code → refuse with `IRVersionError` ("update LaserBench");
- older → migrate if a migration exists, otherwise refuse with `IRVersionError`;
- missing or not an integer → refuse.

v1 has no predecessors, so no migrations exist yet.
