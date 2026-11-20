# Architecture — LaserBench

Status: **Draft v0.1** · Owner: coordinator

## 1. Principles

1. **The parametric source of truth stays in FreeCAD.** LaserBench objects hold references and
   settings, never copies of geometry that could go stale.
2. **Thin FreeCAD shell, thick pure-Python core.** Anything that doesn't need OpenCASCADE lives
   in `core/` and is tested with plain pytest.
3. **One neutral contract (the IR)** sits between "FreeCAD geometry" and "anything downstream".
   Exporters and future machine backends consume only the IR.
4. **Settings are opaque.** LaserBench passes laser settings through. It interprets only what it
   must act on itself (kerf, hatch spacing, tabs).

## 2. Layer diagram

```
┌─────────────────────────────────────────────────────────────┐
│ gui/        Commands · TaskPanels · ViewProviders · Prefs   │  FreeCADGui + Qt
├─────────────────────────────────────────────────────────────┤
│ objects/    LaserJob · LaserOperation (FeaturePython proxies)│  FreeCAD (App)
├─────────────────────────────────────────────────────────────┤
│ fc/         extract (sources → Part wires in job plane)     │  FreeCAD + Part (OCC)
│             kerf (offset2D) · to_ir (Part → IR paths)        │
│             preview (IR → Part.Compound for 3D view)         │
├─────────────────────────────────────────────────────────────┤
│ core/       ir · settings merge · ordering · dedupe ·       │  PURE PYTHON
│             validate · hatch · export_svg/json/dxf · presets │  (stdlib only)
│             handoff (subprocess)                             │
└─────────────────────────────────────────────────────────────┘
api.py — public scripting facade across all layers (FR-080)
```

Imports may point **down** only. `core` imports nothing above it. `fc` may import `core`.
`objects` may import `fc` and `core`. `gui` may import everything.

## 3. Recompute pipeline

```
LaserOperation.execute(obj)
  1. resolve sources (PropertyLinkSubList)            fc/extract.py
     └─ broken link → raise LBSourceError (FR-065)
  2. to 2D wires in the job plane (projection mode)    fc/extract.py
  3. apply operation placement offset (FR-046)         fc/extract.py
  4. kerf compensation if Cut (FR-050)                 fc/kerf.py   (Part.Face.makeOffset2D)
  5. convert to IR paths (lines/arcs/polylines)        fc/to_ir.py
  6. store IR fragment on obj (hidden string property) + set obj.Shape for preview

LaserJob.execute(obj)
  1. collect enabled operations' IR fragments in Order
  2. merge settings: preset ⊕ operation overrides       core/settings.py
  3. dedupe (FR-054) → order (FR-053) → hatch? (FR-052) core/
  4. transform to the machine coordinate convention     core/coords.py
  5. validate (FR-060..066)                             core/validate.py
  6. store the full IR JSON on obj (hidden) + preview Shape + validation summary
```

Export commands read the stored IR and call `core/export_*.py`. They never re-run geometry.

### Why store IR on the object
Export and validation display stay instant, and headless export (FR-081) only needs a recompute.
The hidden property is excluded from the user-visible property editor
(`setEditorMode(..., 2)`) and marked transient (D-008) so it doesn't bloat the saved file.

## 4. Data model

### 4.1 Document objects (FeaturePython)

**LaserJob** (`objects/job.py`), `Part::FeaturePython` so it can carry a preview Shape.
| Property | Type | Notes |
|---|---|---|
| MachineProfile | App::PropertyString | profile id (key into profiles JSON) |
| MaterialPreset | App::PropertyString | preset id |
| Thickness | App::PropertyLength | expression-bindable, informational and section height default |
| Kerf | App::PropertyLength | defaults from preset; expression-bindable override |
| JobPlane | App::PropertyPlacement | plane that geometry is projected onto (default XY) |
| Operations | App::PropertyLinkList | ordered children |
| OutputDir | App::PropertyPath | FR-075 |
| ExportFormats | App::PropertyStringList | `svg`, `json`, `dxf` |
| IRCache | App::PropertyString | hidden, transient |
| ValidationSummary | App::PropertyStringList | read-only |

**LaserOperation** (`objects/operation.py`), `Part::FeaturePython`.
| Property | Type | Notes |
|---|---|---|
| OpType | App::PropertyEnumeration | Cut, Score, Fill |
| Sources | App::PropertyLinkSubList | sketches, faces, edges, solids, bodies |
| ProjectionMode | App::PropertyEnumeration | Face, Direction, Section |
| ProjectionDirection | App::PropertyVector | for Direction mode |
| SectionHeight | App::PropertyDistance | for Section mode |
| KerfMode | App::PropertyEnumeration | Auto, Outside, Inside, None |
| Offset | App::PropertyPlacement | FR-046 (only x, y, and rotation about Z used) |
| ArrayCount | App::PropertyIntegerList | [nx, ny] FR-047 |
| ArraySpacing | App::PropertyVector | |
| Enabled | App::PropertyBool | |
| Order | App::PropertyInteger | |
| Colour | App::PropertyColor | |
| SettingsOverrides | App::PropertyMap | string→string, values parsed as numbers where possible |
| IRFragment | App::PropertyString | hidden, transient |

Note on PropertyMap: it isn't expression-bindable. For expression-driven overrides, the common
keys (`power`, `speed`, `passes`, `frequency`) get real `App::PropertyFloat` properties in an
`Overrides` group, created on demand (D-007).

### 4.2 Persistent user data (JSON, in `FreeCAD.getUserAppDataDir()/LaserBench/`)
- `machines.json`: list of MachineProfile
- `materials.json`: list of MaterialPreset, keyed by machine id
- Both carry `schema_version` (NFR-007). Format in `IR_SCHEMA.md` §4.

### 4.3 IR
Defined in `docs/IR_SCHEMA.md`. Python dataclasses live in `core/ir.py`, with `to_dict()` and
`from_dict()`. **Frozen after Phase 0.**

## 5. Key technical notes for implementers

- **Projection:** use `TechDraw.projectEx` or `Part.Shape.project`/`makeParallelProjection` for
  Direction mode. Use `Part.Shape.slice(normal, d)` for Section mode. For Face mode, take
  `face.OuterWire` and `face.Wires[1:]` and transform into the job plane. Evaluate which
  projection API is most robust in FreeCAD 1.0 during task G-02 and record the choice in DECISIONS.
- **Kerf:** `Part.Face(wire).makeOffset2D(±kerf/2, join=0 (arc), fill=False, openResult=False)`
  per closed loop. Decide the sign by whether a loop is outer or a hole (nesting depth parity).
  Loops whose offset vanishes (hole too small) produce a validation warning (FR-064), not a crash.
- **Curves → IR:** `Part.Line` → line, `Part.Circle`/arc of circle → arc (center, radius, start,
  end, ccw). Ellipses and B-splines → `edge.discretize(Deflection=tol)` polyline.
- **Topological naming:** FreeCAD 1.0 includes partial TNP mitigation. Prefer whole-sketch and
  whole-body sources in examples and docs. On a missing sub-element, raise `LBSourceError` with
  the label and sub-name. Never fall back silently to another face.
- **Recompute safety:** `execute()` must never raise to FreeCAD except to signal a hard error.
  Catch, record into ValidationSummary, set an empty Shape, and mark the object with an error
  state via `obj.setStatus` or by raising a `FreeCAD.Base.FreeCADError` with a clear message
  (D-009).
- **Restore without the workbench (NFR-006):** proxies implement `dumps()`/`loads()` returning
  plain dicts (FreeCAD ≥ 0.22 naming; older `__getstate__` is also accepted). No Qt in App-side
  proxies.

## 6. Public API sketch (`laserbench/api.py`)

```python
make_job(doc, machine: str, material: str, name="LaserJob") -> LaserJob
add_operation(job, op_type: str, sources: list, **props) -> LaserOperation
recompute(job) -> ValidationReport
export(job, formats=("svg", "json"), out_dir=None) -> dict[str, Path]
send(job) -> subprocess.Popen | None
export_document(path: str | Path, formats=("svg", "json")) -> list[Path]   # headless
load_profiles() / save_profiles(...) / load_presets() / save_presets(...)
```

## 7. File ownership (for parallel agents)

| Path | Owner role |
|---|---|
| `laserbench/core/ir.py`, `docs/IR_SCHEMA.md` | **Coordinator** (frozen after Phase 0) |
| `laserbench/core/**` (everything else) | core-dev |
| `laserbench/fc/**` | geometry-dev |
| `laserbench/objects/**`, `laserbench/api.py` | workbench-dev |
| `laserbench/gui/**`, `laserbench/resources/**`, `InitGui.py`, `Init.py`, `package.xml` | workbench-dev |
| `laserbench/core/presets.py`, `laserbench/core/handoff.py`, `resources/defaults/*.json` | presets-dev |
| `tests/core/**` | core-dev (+ presets-dev for their modules) |
| `tests/fc/**`, `tests/fixtures/**` | qa |
| `docs/user/**` | qa |
| `CLAUDE.md`, `docs/*.md` (except user/) | Coordinator |
| `tools/**`, CI config, `pyproject.toml` | Coordinator |

Shared-file edits go through the owner. If two roles both need to change the same file, the
coordinator splits the file or sequences the tasks.

## 8. Extension points (deliberately left open)

- **Backends:** `core/backends/` (future). Interface: `class Backend: def run(ir: IRJob) -> None`.
  Candidates: a MeerK40t console bridge, galvoplotter (LMC) direct, Ruida UDP, G-code
  (grblHAL/FluidNC). None are implemented in this phase (OS-1).
- **Raster:** IR has a reserved `image` path kind (unused now) so OS-2 can be added later.
- **Nesting:** `core/layout.py` exposes `layout(parts, area) -> placements`. P2 has shelf
  packing only. Swappable.
