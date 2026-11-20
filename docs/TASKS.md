# Task Breakdown — LaserBench

The coordinator loads these into the shared task list. Each task lists: **role**, **depends on**,
**requirements**, **files**, and **done when**. A task is claimable only when all its
dependencies are done.

Task ID prefixes: `C` coordinator · `K` core-dev · `G` geometry-dev · `W` workbench-dev ·
`P` presets-dev · `Q` qa.

---

## Phase 0: Foundations (sequential, coordinator-led)

**Status: done (2026-11-20).** C-01 and C-02 in PR #1, C-03 in the interface-stubs PR.
Every stub raises `NotImplementedError("<task id>")`, so a grep for a task id finds its stubs.

Nothing parallel starts until Phase 0 is merged. This is what stops agents from diverging.

### C-01 Freeze the IR contract
- Role: coordinator · Depends: — · Reqs: FR-070, NFR-002, NFR-007
- Files: `laserbench/core/ir.py`, `docs/IR_SCHEMA.md`
- Done when: dataclasses for IRJob/IROperation/IRPath/IRSegment/IRRegion/IRIssue exist with
  `to_dict`/`from_dict`, stable 4-decimal serialisation, and a `schema_version` check.
  Round-trip tests pass. The schema doc matches the code exactly.

### C-02 Repo skeleton and tooling
- Role: coordinator · Depends: — · Reqs: FR-001, NFR-001
- Files: package layout per CLAUDE.md, `pyproject.toml` (ruff, pytest config), `tools/dev_install.py`,
  `tests/fc/run_all.py` (unittest runner for freecadcmd), `tests/core/test_layering.py`
  (asserts `core` imports under plain CPython with no `FreeCAD` module available), CI workflow
  (pytest on CPython 3.11; freecadcmd job via a conda-forge `freecad` environment).
- Done when: `pytest tests/core` and `freecadcmd tests/fc/run_all.py` both run (even if empty)
  locally and in CI.

### C-03 Interface stubs
- Role: coordinator · Depends: C-01, C-02
- Files: stub modules with signatures, docstrings, and `NotImplementedError` for every module
  listed in ARCHITECTURE §2, plus `api.py`.
- Done when: all lanes can import their dependencies' interfaces. Signatures reviewed.

---

## Phase 1: MVP (parallel lanes)

### Lane K: core-dev (pure Python)
**K-01 Settings merge**: Depends C-03 · FR-021, FR-044 · `core/settings.py`
Done: preset ⊕ override precedence, numeric coercion, unknown keys preserved. Tests.

**K-02 Coordinate transforms**: Depends C-03 · FR-011 · `core/coords.py`
Done: job frame → machine frame for all 4 gantry origins plus galvo centre. Arc direction
is preserved under mirroring (ccw flips on reflection). Tests per origin.

**K-03 Dedupe**: Depends C-03 · FR-054 · `core/dedupe.py`
Done: coincident lines and arcs (both directions, tolerance 1e-4) removed within an
operation, and partial overlaps of collinear lines trimmed. Fixtures: adjacent squares, a
repeated path.

**K-04 Ordering**: Depends C-03 · FR-053 · `core/ordering.py`
Done: containment tree (point-in-polygon on discretised loops), holes before parents,
nearest-neighbour within each level, closed-path start-point rotation to the nearest point.
Deterministic. Tests on nested fixtures.

**K-05 Validation rules**: Depends C-03 · FR-060–064, FR-066 · `core/validate.py`
Done: each issue code implemented, with a test that triggers it.

**K-06 SVG exporter**: Depends C-03, K-02 · FR-071, FR-072 · `core/export_svg.py`
Done: matches IR_SCHEMA §5. Golden-file tests (structure-normalised). Manual check: opens at
the correct size in Inkscape.

**K-07 JSON exporter + atomic write**: Depends C-03 · FR-070, FR-075 · `core/export_json.py`, `core/fsutil.py`

### Lane G: geometry-dev (FreeCAD/Part)
**G-01 Source resolution**: Depends C-03 · FR-041, FR-065 · `fc/extract.py`
Done: sketch, face, edge, solid, and Body sources resolve to shapes. A broken sub-link raises
`LBSourceError(label, subname)`.

**G-02 Projection modes**: Depends G-01 · FR-042, FR-043 · `fc/extract.py`
Done: Face/Direction/Section modes produce closed wires in the job plane. Record the D-013
outcome. Tests: box with pocket, cylinder with hole, rotated sketch.

**G-03 Kerf compensation**: Depends G-02 · FR-050, FR-064 · `fc/kerf.py`
Done: Auto/Inside/Outside/None. Nesting parity decides the offset sign. A collapsed loop
emits KERF_COLLAPSE. Dimensional tests per FR-050 acceptance.

**G-04 Part → IR conversion**: Depends G-02 · FR-051 · `fc/to_ir.py`
Done: lines → line, circular arcs → arc (correct ccw in the job plane), everything else →
poly within tolerance. A max-deviation test is included.

**G-05 Preview builder**: Depends G-04 · FR-034 · `fc/preview.py`
Done: IR → Part.Compound of edges on the job plane, coloured per operation via the view
provider. The bounding box matches IR bounds.

### Lane W: workbench-dev (objects + GUI)
**W-01 Workbench registration**: Depends C-02 · FR-001, FR-003 · `InitGui.py`, `package.xml`, icons
Done: workbench appears, lazy imports, no load-time errors.

**W-02 LaserOperation object**: Depends C-03, G-04 · FR-040, FR-044, FR-045 · `objects/operation.py`
Done: properties per ARCHITECTURE §4.1, `execute` wired to the fc pipeline, restore without
the workbench (NFR-006).

**W-03 LaserJob object**: Depends W-02, K-01..K-05 · FR-030–033 · `objects/job.py`
Done: aggregates operations, runs the core pipeline, stores IR + ValidationSummary, and
recomputes on source change.

**W-04 Commands + task panels**: Depends W-03 · FR-030, FR-032, FR-040 · `gui/commands.py`, `gui/panels/*`
Done: Create Job (choose machine/material), Add Operation from the selection (type,
projection, kerf), reorder, enable/disable.

**W-05 View providers + preview colours**: Depends G-05, W-03 · FR-034 · `gui/viewproviders.py`

**W-06 Validation panel**: Depends W-03 · FR-060 · `gui/panels/validation.py`
Done: lists issues, and clicking one selects/zooms the operation or location.

**W-07 Export + Send commands**: Depends K-06, K-07, P-03, W-03 · FR-070–074 · `gui/commands.py`, `api.py`

**W-08 Public API**: Depends W-03 · FR-080, FR-081 · `api.py`

### Lane P: presets-dev
**P-01 Profiles/presets storage**: Depends C-01 · FR-010, FR-020, NFR-007 · `core/presets.py`
Done: load/save/validate machines.json and materials.json, migrate by version, defaults on
first run.

**P-02 Default data**: Depends P-01, D-012 · FR-012 · `resources/defaults/*.json`
(Machine data is in DECISIONS D-012.)

**P-03 Handoff runner**: Depends C-03 · FR-074 · `core/handoff.py`
Done: placeholder substitution, argument-list subprocess, non-blocking, captures launch
errors, no shell. Tests use a fake executable.

**P-04 Preferences page**: Depends P-01, W-01 · FR-013 · `gui/prefs.py`
(Coordinate with workbench-dev: P-04 is the only presets-dev task in `gui/`, and the
coordinator grants ownership of `gui/prefs.py` for it.)

### Lane Q: qa
**Q-01 Fixture builders**: Depends C-02 · `tests/fixtures/*.py`
Scripts that build .FCStd fixtures headlessly: box_with_pocket, nested_squares,
adjacent_squares, rotated_sketch, open_contour, tiny_hole, spreadsheet_driven_box (finger-joint
panel driven by `Spreadsheet.thk`).

**Q-02 End-to-end tests**: Depends W-08, Q-01 · FR-031, FR-033, FR-081
Done: the headline test passes. Change `Spreadsheet.thk` 3 → 6, recompute, export, and assert
the SVG slot widths changed accordingly.

**Q-03 MeerK40t mapping spike**: Depends K-06 · D-006
Done: written findings in DECISIONS D-006: how MeerK40t imports the SVG (colours, layers,
scale, origin) on both a gantry and a galvo device profile. No laser required (use MeerK40t's
simulate/preview).

**Q-04 Requirements trace audit**: Depends all P0 tasks
Done: table in `docs/TRACE.md` mapping every P0 FR/NFR → test(s). Gaps filed as tasks.

**Q-05 User guide**: Depends W-07 · NFR-010 · `docs/user/`

---

## Phase 2: v1.0 (after the MVP is accepted by the owner)
FR-002, FR-022, FR-035, FR-046, FR-047, FR-052, FR-055, FR-065 polish, FR-073 (DXF), FR-076,
NFR-003 performance profiling, NFR-008. The coordinator breaks these down when Phase 1 closes.

## Phase 3: Later / P2
FR-023, FR-048, FR-056, backend plug-ins (ARCHITECTURE §8).

---

## Dependency graph (Phase 0–1, critical path in bold)

```
C-01 ─┬─ C-03 ─┬─ K-01..K-05 ──────────────┐
C-02 ─┘        ├─ K-06 (needs K-02) ─ Q-03  │
               ├─ G-01 ─ G-02 ─┬─ G-03      │
               │               └─ **G-04 ─ W-02 ─ W-03** ─┬─ W-04, W-06, W-08 ─ Q-02 ─ Q-04
               │                    └─ G-05 ─ W-05         └─ W-07 (needs K-06, K-07, P-03)
               ├─ P-03
C-01 ─ P-01 ─ P-02, P-04
C-02 ─ W-01, Q-01
```
The critical path runs through geometry (G-01→G-04) into the objects (W-02→W-03). Start
geometry-dev first and give it the strongest model if per-teammate model choice is available.
