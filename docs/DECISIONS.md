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
| D-006 | OPEN | How MeerK40t maps SVG colours/layers to operations |
| D-007 | PROPOSED | Expression-bindable overrides for common keys only |
| D-008 | PROPOSED | IR cache properties are transient |
| D-009 | PROPOSED | Error signalling from execute() |
| D-010 | OPEN | Licence |
| D-011 | OPEN | Project name |
| D-012 | OPEN | Minimum FreeCAD version and machine dimensions |
| D-013 | PROPOSED | Projection API choice (finalised by task G-02) |
| D-014 | DECIDED | Repository root is the FreeCAD addon folder |

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

### D-006 MeerK40t SVG mapping — OPEN
Needs a spike (task Q-03): does MeerK40t create one operation per stroke colour on SVG import?
Does it read Inkscape layer labels? Can operation settings be pre-loaded (e.g. by a console
command or a saved operations file)? The answer decides how much of FR-072 is useful and
whether FR-023 is possible. **Owner input:** confirm the MeerK40t version you run.

### D-007 Overrides — PROPOSED
`power`, `speed`, `passes`, and `frequency` get real float properties (expression-bindable).
Other keys go in a string map.

### D-008 Transient caches — PROPOSED
`IRCache`/`IRFragment` are set Transient and recomputed on load. Keeps .FCStd files small and
avoids stale data.

### D-009 Error signalling — PROPOSED
User-correctable problems become validation issues (no exception). Hard failures (e.g. every
source is broken) raise with a clear message so FreeCAD marks the object as errored in the tree.

### D-010 Licence — OPEN
Proposed LGPL-2.1-or-later (matches FreeCAD and most addons). MIT is an alternative if
MeerK40t code might be borrowed later (MeerK40t is MIT). **Owner decides.**

### D-011 Name — OPEN
"LaserBench" is a working name. Check the Addon Manager index and PyPI for clashes before release.

### D-012 Versions and machine dimensions — OPEN
Owner to supply: FreeCAD version on the Mac and on Linux; galvo field size (lens-dependent);
CO2 bed size and origin corner; MeerK40t version.

*Known so far (2026-11-20):* the owner's Linux checkout lives in
`~/.local/share/FreeCAD/v1-1/Mod/`, so Linux runs **FreeCAD 1.1**. `package.xml` keeps
`freecadmin` at 1.0.0 (NFR-006) until the Mac version is known. Still needed: the Mac FreeCAD
version, both machine sizes, the CO2 origin corner, and the MeerK40t version.

### D-013 Projection API — PROPOSED
Start with `Part.Shape.slice` (Section) and face wires (Face). For Direction, evaluate
`TechDraw.projectEx` against `Part.Shape.makeParallelProjection` in task G-02 for robustness
on curved solids. Record the result here.

### D-014 Repository layout — DECIDED
The repository root is the addon folder: `Init.py`, `InitGui.py` and `package.xml` sit at the
root, and the code is the `laserbench/` package inside it. Docs move under `docs/`.
*Why:* the owner clones the repo directly into FreeCAD's `Mod/` folder, and the Addon Manager
also installs a repository's root as the addon folder (FR-002). `tools/dev_install.py` remains
for checkouts elsewhere.
