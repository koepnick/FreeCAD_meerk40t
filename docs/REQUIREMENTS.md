# Requirements — LaserBench FreeCAD Workbench

Status: **Draft v0.1** · Owner: project owner (human) · Maintainer: coordinator

Priority key: **P0** = MVP, must ship · **P1** = expected in v1.0 · **P2** = nice to have / later.
Every requirement has an ID. Tasks and tests cite these IDs.

---

## 1. Context

### 1.1 Problem
The owner prototypes parametrically in FreeCAD and runs two lasers:
- a **CO2 gantry laser** with a Ruida controller, and
- an **OMTech 50 W galvo fiber laser** with a BJJCZ LMC (EZCAD2-class) board.

Current laser software (LightBurn, Inkscape) is not parametric. A dimension change
in FreeCAD means re-exporting, re-importing, and re-assigning layers and settings by hand.
LightBurn's platform support is also shrinking (Linux dropped; the macOS outlook is uncertain).

### 1.2 Goal
Keep the parametric chain unbroken from model to laser job: change a spreadsheet
value, recompute, export, run. Do not rebuild what existing open-source laser
software already does well (rastering, motion planning, controller protocols).

### 1.3 Out of scope (this phase)
- OS-1 Direct communication with any laser controller (USB, serial, Ethernet).
- OS-2 Raster/photo/greyscale image engraving.
- OS-3 Controller firmware or hardware changes.
- OS-4 True nesting optimisation (irregular-shape packing, sheet-yield optimisation).
- OS-5 Camera alignment, rotary attachments, Z/autofocus control.
- OS-6 Running a laser from inside FreeCAD (start/stop/pause/frame).

These stay out so a backend layer can be added later without reworking the FreeCAD side.
See ARCHITECTURE §8 (extension points).

### 1.4 Users and environment
- Primary user: experienced FreeCAD user, comfortable with Python, prototypes in wood/acrylic (CO2) and metal marking (fiber).
- Machines: Mac Mini M1 (fiber host), Linux (CO2 host). The workbench must work on both, and on Windows.
- Downstream consumer: MeerK40t (supports Ruida and EZCAD2 LMC) via file handoff.

---

## 2. Functional requirements

### 2.1 Workbench and installation
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-001 | P0 | The workbench installs as a standard FreeCAD addon (folder in `Mod/`, valid `package.xml`). | Appears in the workbench selector after restart. `package.xml` validates against the FreeCAD addon schema. |
| FR-002 | P1 | The workbench can be installed through FreeCAD's Addon Manager from a git URL. | Fresh FreeCAD install → Addon Manager → custom repo → install → works. |
| FR-003 | P0 | Loading the workbench never slows FreeCAD startup noticeably and never errors if optional pieces are missing. | No tracebacks in Report View on load. Imports are lazy inside commands. |

### 2.2 Machine profiles
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-010 | P0 | The user can define **machine profiles**: name, kind (`gantry` or `galvo`), work area (W×H mm), origin convention, default kerf. | Profiles persist across sessions as JSON in FreeCAD's user data dir. |
| FR-011 | P0 | Galvo profiles define a centred field (e.g. 110×110 mm) with origin at the field centre. Gantry profiles define the origin corner (front-left, rear-left, etc.). | Exported coordinates match the convention. A unit test covers each origin option. |
| FR-012 | P1 | Ship two default profiles matching the owner's machines (sizes in D-012). | Defaults load on first run and are user-editable. |
| FR-013 | P1 | A preferences page manages profiles (add, edit, duplicate, delete). | All CRUD works without a restart. |

### 2.3 Material presets
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-020 | P0 | The user can define **material presets** per machine: name, nominal thickness, kerf, and per-operation-type settings. | Persist as JSON. Keyed by machine profile. |
| FR-021 | P0 | Preset laser settings are **opaque pass-through** key/values (power %, speed, passes, frequency, Q-pulse, hatch interval…). LaserBench stores and exports them but does not interpret them, except `kerf` and `hatch_interval` (FR-052). | IR export contains the settings verbatim. Adding a new key needs no code change. |
| FR-022 | P1 | Import and export presets as a JSON file so they can be shared or backed up. | Round-trip test passes. |
| FR-023 | P2 | Seed presets from a MeerK40t operations/material export, if its format allows. | Depends on D-006. |

### 2.4 Laser Job object
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-030 | P0 | The user can create a **LaserJob** document object (FeaturePython) that links a machine profile and a material preset. | Appears in the tree. Properties are editable. Survives save/reload. |
| FR-031 | P0 | Job properties are expression-bindable (e.g. `Thickness = Spreadsheet.thk`, `Kerf = Spreadsheet.kerf`). | Changing the spreadsheet cell and recomputing updates the job output. |
| FR-032 | P0 | A job contains an ordered list of **LaserOperation** children. | Tree shows operations nested under the job. Order is user-adjustable. |
| FR-033 | P0 | The job recomputes automatically when any referenced geometry changes (FreeCAD dependency graph). | Edit a sketch dimension → job marked touched → recompute → updated output. |
| FR-034 | P0 | The job shows a 2D **preview** in the 3D view: coloured by operation, drawn on a plane representing the machine work area or field. | Visual check plus a test that the preview Shape bounding box equals the IR bounds. |
| FR-035 | P1 | Multiple jobs per document (e.g. one per machine or per sheet). | Two jobs export independently. |

### 2.5 Laser Operations
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-040 | P0 | Operation types: **Cut** (through-cut, closed contours), **Score/Engrave-Vector** (follow lines, open or closed), **Fill** (closed regions to be hatched or filled downstream). | Each type exports with its own layer/colour and type tag in the IR. |
| FR-041 | P0 | Operation **sources** can be any of: Sketch, face(s), edge(s), a whole solid, or a Body. Stored as `App::PropertyLinkSubList`. | Each source kind has an fc test. |
| FR-042 | P0 | Solid and face sources are converted to 2D via a **projection mode**: (a) a selected planar face (outline + holes), (b) projection along a direction onto the job plane, (c) a section at a given height. | Tests: a box with a pocket gives correct outer and inner loops for each mode. |
| FR-043 | P0 | Sketches export in their own plane, transformed into the job plane (respecting Placement). | A rotated sketch exports flattened and correctly placed. |
| FR-044 | P0 | Each operation can override any preset setting. Overrides are expression-bindable. | IR shows the merged settings. Override precedence is tested. |
| FR-045 | P0 | Operations have `Enabled`, `Order`, and `Colour` (auto-assigned from a palette, user-overridable). | A disabled operation is absent from the export. |
| FR-046 | P1 | Operation **placement offset** (x, y, rotation) within the job, expression-bindable, for laying out several parts. | Offset applied in the IR. Tested. |
| FR-047 | P1 | **Array helper**: repeat an operation's geometry N×M with spacing. | IR contains N×M copies, or an array reference (decided by D-004). |
| FR-048 | P2 | **Simple layout**: shelf-pack the bounding boxes of selected operations into the work area. | No overlaps. Everything inside bounds or flagged. |

### 2.6 Geometry processing
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-050 | P0 | **Kerf compensation** for Cut operations. Modes: `None`, `Outside`, `Inside`, `Auto` (outer boundaries offset outward and holes offset inward by kerf/2, so parts come out at nominal size). | Test: a 50 mm square with 0.2 mm kerf in Auto mode gives a 50.2 mm path. A 10 mm hole gives a 9.8 mm path. |
| FR-051 | P0 | Arcs and circles are kept as arcs where the IR allows. B-splines are approximated to a configurable chord tolerance (default 0.01 mm). | Max deviation ≤ tolerance (tested). |
| FR-052 | P1 | Optional **hatch generation** for Fill operations inside LaserBench, using preset `hatch_interval` and `hatch_angle`. Off by default; downstream software may fill instead (D-005). | Hatch lines stay inside region boundaries and respect holes. Tested. |
| FR-053 | P0 | **Cut ordering**: inner contours before the outer contour that encloses them (so parts don't drop before their holes are cut). Then nearest-neighbour ordering to cut travel. | Tests on nested-contour fixtures. Order is deterministic. |
| FR-054 | P0 | **Duplicate/overlap removal**: coincident edges from adjacent parts or repeated geometry are de-duplicated within an operation, so the laser doesn't cut the same line twice. | A two-adjacent-squares fixture exports the shared edge once. |
| FR-055 | P1 | **Common-line option** across operations: off by default, explicit opt-in. | Tested when on. |
| FR-056 | P2 | **Tabs/bridges** on Cut contours (count or spacing, width). Expression-bindable. | Gaps at the expected positions. |

### 2.7 Validation
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-060 | P0 | Validate before export and show results in a panel, with errors and warnings. | Each rule below has a test fixture that triggers it. |
| FR-061 | P0 | Error: geometry outside the machine work area or galvo field. | — |
| FR-062 | P0 | Warning: open contour in a Cut operation (with its location). | — |
| FR-063 | P0 | Error: Fill operation with no closed regions. | — |
| FR-064 | P1 | Warning: feature smaller than the kerf (slot narrower than kerf, hole diameter < 2×kerf). | — |
| FR-065 | P0 | Error: broken source link (e.g. a topological-naming break after a model edit), naming the operation and the missing sub-element. | Rename or delete a referenced face → clear error, not a traceback. |
| FR-066 | P1 | Warning: self-intersecting contour. | — |

### 2.8 Export and handoff
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-070 | P0 | Export the **IR JSON** (see `IR_SCHEMA.md`). | Validates against the schema. Round-trip load test. |
| FR-071 | P0 | Export **SVG**: mm units, correct viewBox for the machine area, one `<g>` per operation with id/label, a distinct stroke colour per operation, hairline stroke, no fills for Cut/Score, fill for Fill operations (unless hatched). | Opens at correct scale in Inkscape and MeerK40t. A golden-file test compares structure. |
| FR-072 | P0 | The SVG embeds operation metadata (type, settings) in a namespaced attribute or `<metadata>`, so downstream tools could map it automatically. | Present and parseable. |
| FR-073 | P1 | Export DXF (R12/R2000 LINE/ARC/LWPOLYLINE), one layer per operation. | Opens in LibreCAD at correct scale. |
| FR-074 | P0 | **Send command**: a per-machine-profile command template, e.g. `meerk40t "{svg}"`, run after export with placeholders `{svg}`, `{json}`, `{dxf}`, `{job_name}`. | Runs non-blocking. Errors are shown. No shell injection (argument list, not a shell string). |
| FR-075 | P1 | Export to a stable per-job path (configurable) so external tools can watch or reload the file. | Re-export overwrites atomically (write to temp file, then rename). |
| FR-076 | P1 | Batch: export all jobs in the document with one command. | — |

### 2.9 Macro and scripting API
| ID | Pri | Requirement | Acceptance |
|---|---|---|---|
| FR-080 | P0 | Every GUI action is also available from Python (`import laserbench; laserbench.api.make_job(...)`). | The API is documented in docstrings and used by the fc tests. |
| FR-081 | P1 | Headless export: `freecadcmd -c "import laserbench.api as a; a.export_document('x.FCStd')"`. | Works without a GUI. Covered by a CI test. |

---

## 3. Non-functional requirements

| ID | Pri | Requirement |
|---|---|---|
| NFR-001 | P0 | **Layering**: `core/` is pure Python standard library (no FreeCAD, Part, or Qt imports). Enforced by a test that imports `core` in plain CPython. |
| NFR-002 | P0 | **Determinism**: the same document produces byte-identical IR/SVG (stable ordering, fixed float formatting to 4 decimals). |
| NFR-003 | P0 | **Performance**: recomputing a job with 500 contours / 20k segments takes < 2 s on an M1. Export takes < 1 s. |
| NFR-004 | P0 | **Robustness**: no uncaught exceptions reach the user. Failures are shown in the validation panel or Report View with an actionable message. |
| NFR-005 | P0 | **Cross-platform**: macOS arm64, Linux x86_64, Windows x86_64. Paths via `pathlib`. Subprocess via argument lists. |
| NFR-006 | P0 | **Compatibility**: FreeCAD ≥ 1.0. Documents saved by LaserBench open in FreeCAD without LaserBench installed (objects degrade gracefully, no crash). |
| NFR-007 | P1 | **Schema versioning**: the IR and preset JSON carry `schema_version`. Loaders migrate or refuse older/newer versions explicitly. |
| NFR-008 | P1 | **i18n-ready**: user strings wrapped for translation. |
| NFR-009 | P0 | **Test coverage**: `core/` ≥ 90% line coverage. Every P0 FR has at least one automated test. |
| NFR-010 | P1 | **Docs**: user guide (install, first job, presets, handoff to MeerK40t) in `docs/user/`. |

---

## 4. Assumptions to confirm (owner)

- A-1 MeerK40t can load an SVG and map operations by stroke colour. *(D-006: it can, but operation groups in the SVG are more reliable; verify on the owner's build)*
- A-2 Galvo field 150 × 150 mm; gantry bed 600 × 400 mm, origin rear-left. *(confirmed, D-012)*
- A-3 The owner's FreeCAD version: 1.1.4 on all machines. *(confirmed, D-012)*
- A-4 A typical job size is a handful of parts and hundreds, not tens of thousands, of contours.

## 5. Glossary
- **Job**: one export unit, targeting one machine profile and one material.
- **Operation**: a set of geometry plus one laser action type and its settings.
- **IR**: Intermediate Representation, the machine-neutral JSON job description.
- **Kerf**: width of material removed by the beam.
- **Galvo field**: square working area of a galvo scanner, origin at its centre.
