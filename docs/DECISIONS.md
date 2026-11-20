# Decisions Log — LaserBench

Agents: check here before making a design choice. If the item you need is **OPEN**, stop
and escalate to the coordinator, who escalates to the owner if needed. Never resolve an
OPEN item on your own.

Status values: **DECIDED** · **PROPOSED** (default unless the owner objects) · **OPEN** (needs the owner)

| ID | Status | Topic |
|---|---|---|
| D-001 | DECIDED | Scope: FreeCAD workbench only; laser I/O deferred |
| D-002 | DECIDED | Handoff via file + external command; MeerK40t is the first consumer |
| D-003 | DECIDED | Pure-Python core, no third-party deps in the workbench |
| D-004 | PROPOSED | Arrays expanded in IR (not referenced) |
| D-005 | PROPOSED | Hatching off by default; downstream fills regions |
| D-006 | PROPOSED | How MeerK40t maps SVG colours/layers to operations |
| D-007 | PROPOSED | Expression-bindable overrides for common keys only |
| D-008 | PROPOSED | IR cache properties are transient |
| D-009 | PROPOSED | Error signalling from execute() |
| D-010 | DECIDED | Licence |
| D-011 | DECIDED | Project name |
| D-012 | DECIDED | Minimum FreeCAD version and machine dimensions |
| D-013 | DECIDED | Projection API choice (finalised by task G-02) |
| D-014 | DECIDED | Repository root is the FreeCAD addon folder |
| D-015 | DECIDED | Versioning and releases |

---

### D-001 Scope — DECIDED
The FreeCAD side only. No controller communication, raster, or firmware (REQUIREMENTS §1.3).
*Why:* the owner's priority is a parametric workflow. Existing open-source software (MeerK40t)
already drives both of the owner's controllers (Ruida, EZCAD2 LMC).

### D-002 Handoff — DECIDED
Export SVG + IR JSON, then optionally launch a per-machine command (argument list).
*Why:* a file boundary keeps the backend swappable. If MeerK40t stalls (it's in maintenance
mode as of 2026), another backend can consume the same files or IR.

### D-003 Pure-Python core — DECIDED
`core/` uses the standard library only. *Why:* FreeCAD bundles its own Python, so third-party
packages are friction for users. It's also testable with pytest outside FreeCAD.

### D-004 Arrays — PROPOSED
Expand array copies into concrete paths in the IR. *Trade-off:* bigger files, but every
consumer stays simple.

### D-005 Hatching — PROPOSED
Default: export fill regions as filled SVG shapes and let MeerK40t hatch them. LaserBench
hatching (FR-052) is an opt-in per operation. *Why:* avoid duplicating mature downstream
features in the MVP.

### D-006 MeerK40t SVG mapping — PROPOSED
*Findings (2026-11-20)* from reading MeerK40t's source at tag **0.9.8100**, the only 0.9.81xx
tag (`meerk40t/core/svg_io.py`, `core/elements/elements.py`, `core/parameters.py`,
`balormk/controller.py`, `main.py`). Not yet confirmed by loading a file in a running MeerK40t.

1. **Layers are not operations.** An Inkscape layer (`<g inkscape:groupmode="layer">`) loads as
   a plain group in the Elements tree, named from `inkscape:label`. It does not create or pick
   an operation.
2. **Colour classification is the fallback.** If the file carries no operations, MeerK40t
   classifies each element by stroke colour against the existing operations (exact, then
   fuzzy), then to "default" operations, then auto-generates one. Filled shapes go to a raster
   operation. Results depend on the user's existing operations and classification preferences,
   so colour alone is not a reliable contract.
3. **Operations can be pre-loaded from the SVG.** MeerK40t's own SVG format stores each
   operation as a top-level `<g>` with plain (un-namespaced) attributes: `type="op cut"` (or
   `op engrave`, `op raster`), `id`, `label`, `color`, settings such as `power`, `speed`,
   `passes`, `passes_custom`, `frequency`, `dpi`, and `references="id1 id2"` listing element
   ids. On load (File → Open, or a file named on the command line) such groups become real
   operations holding exactly the referenced elements, and colour classification is skipped.
   *Side effect:* the user's operations that are empty at load time are removed; operations
   that already hold elements are kept. This is the same as opening a MeerK40t-saved SVG.
4. **Units.** MeerK40t `power` is per mille (1000 = 100 %) on both the K40/Ruida and the
   galvo (Balor/LMC) drivers; `speed` is mm/s; `frequency` is kHz. Galvo pulse width is
   `pulse_width` (ns) and only applies with `pulse_width_enabled="True"`. Raster line spacing
   is `dpi`. `passes` only takes effect with `passes_custom="True"`.
5. **Scale.** An SVG with `width`/`height` in mm and a matching `viewBox` loads at true size.
   The default "SVG Viewport is Bed" preference only affects files without physical units.
6. **Command line.** `meerk40t <file.svg>` opens MeerK40t with the file loaded. `-a`/`--auto`
   starts the laser and must never appear in a send command (P-03 refuses it). If MeerK40t is
   already running, a second launch asks "Another instance is running!", and answering No
   loads nothing.

*Decision (proposed):* the SVG keeps the IR_SCHEMA §5 layers (for Inkscape and other
programs) and adds one MeerK40t operation group per non-empty operation (§5.1), mapping
cut → `op cut`, score and hatched fill → `op engrave`, unhatched fill → `op raster`, with the
settings converted as in point 4. Export can turn the groups off. This makes FR-023 largely
unnecessary for MeerK40t: settings travel with each job.

*Owner to verify on 0.9.81xx* (Q-03 still owns the formal spike):
- Open an exported SVG: the Operations tree shows one operation per LaserBench operation,
  in order, with the expected power/speed/passes, each holding the right shapes.
- The design appears at the right size and place on both device profiles, rear edge at the
  top. For the galvo, check that the field centre is the job centre and that the
  orientation matches the lens (MeerK40t has its own flip/rotate device settings).
- A Fill operation's raster settings (`dpi`, power) are sensible on the galvo, or whether a
  hatch is preferred there.
- Exact build number from Help → About.

### D-007 Overrides — PROPOSED
`power`, `speed`, `passes`, and `frequency` get real float properties (expression-bindable).
Other keys go in a string map.

### D-008 Transient caches — PROPOSED
`IRCache`/`IRFragment` are set Transient and recomputed on load. Keeps .FCStd files small and
avoids stale data.

### D-009 Error signalling — PROPOSED
User-correctable problems become validation issues (no exception). Hard failures (e.g. every
source is broken) raise with a clear message so FreeCAD marks the object as errored in the tree.

### D-010 Licence — DECIDED
**LGPL-2.1-or-later**, chosen by the owner on 2026-11-20. It matches FreeCAD and most addons.
Full text in `LICENSE`; `package.xml` references it; source files carry
`# SPDX-License-Identifier: LGPL-2.1-or-later`.
*Consequence:* MIT-licensed MeerK40t code can still be borrowed (MIT is compatible with LGPL),
keeping its copyright notice.

### D-011 Name — DECIDED
**LaserBench**, chosen by the owner on 2026-11-20. Clash check on 2026-11-20: no `laserbench`
project on PyPI (404) and no FreeCAD addon of that name in the FreeCAD-addons index or a web
search. Re-check the Addon Manager index just before the first public release.

### D-012 Versions and machine dimensions — DECIDED
Supplied by the owner on 2026-11-20.

**FreeCAD:** 1.1.4 on every machine (Mac and Linux). LaserBench is developed and CI-tested
against 1.1.x. `package.xml` keeps `freecadmin` at 1.0.0 because NFR-006 promises
FreeCAD ≥ 1.0; 1.0 is supported but not CI-tested.

**Galvo:** OMTech 50 W autofocus fiber, 1064 nm, 210 mm field lens.
| Profile field | Value |
|---|---|
| kind | `galvo` |
| width × height | 150 × 150 mm (manufacturer spec for this lens) |
| origin | `center` |
Preset hints from the spec sheet: frequency 30–60 kHz, pulse width 80–120 ns.

**CO2 gantry:** OMTech Maker MF1624-60, 60 W.
| Profile field | Value |
|---|---|
| kind | `gantry` |
| width × height | 600 × 400 mm (X along the 24 in side) |
| origin | `rear-left` (the owner's current NW corner) |
The spec sheet also says 16 × 24 in, which is 406.4 × 609.6 mm. We use the manufacturer's mm
figure; if the real travel is larger, the owner can enlarge the profile.
*Origin:* the owner is open to changing it. We keep `rear-left` because it matches SVG's
top-left origin and MeerK40t's on-screen bed view, so the exported SVG needs no horizontal flip.
The controller's physical home corner is a MeerK40t device setting and doesn't affect our
files. Q-03 confirms this on the gantry device profile.

**MeerK40t:** reported as "v.98.1". MeerK40t uses four-digit build numbers (e.g. 0.9.7900,
0.9.8200), so this is most likely **0.9.81xx** in the 0.9.8 series. The owner can confirm the
exact build in Help → About. The latest release at the time of writing is 0.9.9000. Q-03 tests
against the owner's version first.

### D-013 Projection API — DECIDED
- **Face:** the face's `OuterWire` and hole wires, laid flat by the smallest rotation that maps
  the face normal onto the job-plane normal (no rotation when parallel or anti-parallel, so a
  bottom face is not mirrored).
- **Direction:** OCC hidden-line removal through `Part.HLRBRep.Algo` + `Part.HLRBRep.HLRToShape`,
  keeping visible sharp edges and visible silhouettes. Smooth (tangent) edges are dropped since
  they are not cut lines. HLR keeps superimposed lines (a pocket's rim and floor), so exact
  duplicates (same endpoints, midpoint and length to 0.1 µm) are dropped before chaining into
  wires. HLR's output edges lack a full 3D representation (`copy()` empties them
  and a boolean fuse crashed OCC 7.9), so each is rebuilt from its curve first. `direction` points from
  the model towards the viewer, as in TechDraw; the default is the job-plane normal.
- **Section:** `Part.Shape.slice` at the section height, then dropped to z = 0.
- **Edge-only shapes** (sketches, edge sources) are always flattened in their own plane,
  whatever the mode (FR-043). Collinear sketches take the plane from their Placement.

*Why:* `Part.makeParallelProjection` projects a wire onto a face, so it cannot handle solids.
`TechDraw.projectEx` runs the same OCC HLR algorithm but fixes the projection X axis itself
and pulls in the TechDraw module; calling HLR from `Part` lets us choose the axes so a top view
maps one-to-one onto the job plane. Verified in CI (freecadcmd, FreeCAD 1.1) on a box with a
pocket, a cylinder with a hole, and a rotated sketch (`tests/fc/test_extract_projection.py`).

### D-014 Repository layout — DECIDED
The repository root is the addon folder: `Init.py`, `InitGui.py` and `package.xml` sit at the
root, and the code is the `laserbench/` package inside it. Docs move under `docs/`.
*Why:* the owner clones the repo directly into FreeCAD's `Mod/` folder, and the Addon Manager
also installs a repository's root as the addon folder (FR-002). `tools/dev_install.py` remains
for checkouts elsewhere.

### D-015 Versioning — DECIDED
Semantic versioning (`MAJOR.MINOR.PATCH`, no suffixes), starting at **0.1.0** because nothing
has been tested on real hardware yet. `package.xml` is the source of truth; `laserbench.__version__`
and `pyproject.toml` repeat it, and `tools/version.py` plus `tests/core/test_version.py` keep
them in step. Releases are tagged `vX.Y.Z` on `main` with a GitHub release and a
`CHANGELOG.md` section. Process in `docs/RELEASING.md`.
*Why:* the owner asked for a meaningful version in the Addon Manager, which shows
`package.xml`'s `<version>`. The Addon Manager flags updates for git installs by commit and for
zip installs by version string inequality, so the version must change whenever a change
should reach zip users.
