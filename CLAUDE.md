# CLAUDE.md — LaserBench

Every agent on this project reads this file first. Keep it short and current.
The coordinator owns it; teammates propose changes via the coordinator.

## What we are building

A **FreeCAD workbench** that turns parametric FreeCAD geometry into laser jobs.
The user models parts parametrically (Sketcher, PartDesign, Spreadsheet-driven
dimensions), then defines laser *operations* (cut, engrave, fill, score) that
reference that geometry. When the model changes, the laser job recomputes.
The workbench exports a machine-neutral job (JSON intermediate representation)
and a colour-coded SVG that existing laser software (MeerK40t first) can run.

**In scope:** FreeCAD-side modelling, 2D extraction, kerf compensation,
ordering, validation, export, and a generic "hand off to external program" step.
**Out of scope (for now):** talking to laser controllers directly, raster/photo
engraving, firmware, nesting optimisation beyond simple layout.
See `docs/REQUIREMENTS.md` §1.3 for the full out-of-scope list.

## Document map

| File | Read when |
|---|---|
| `docs/REQUIREMENTS.md` | Before starting any task — every task cites requirement IDs |
| `docs/ARCHITECTURE.md` | Before writing code — layers, data model, interfaces, file ownership |
| `docs/IR_SCHEMA.md` | Before touching export, core, or geometry code — this is the frozen contract |
| `docs/DECISIONS.md` | Before making a design choice — check if it is already decided or open |
| `docs/TASKS.md` | To claim work — tasks, dependencies, acceptance criteria |
| `docs/TEAM.md` | Coordinator playbook: roles, spawn prompts, review gates |
| `docs/TESTING.md` | Before writing or running tests |

## Hard rules

1. **Layering is enforced.** `laserbench/core/` must never import `FreeCAD`,
   `Part`, `FreeCADGui`, or Qt. It is pure Python 3.11 standard library only.
   This keeps it testable with plain `pytest` and reusable by future backends.
2. **The IR schema is a contract.** Do not change `docs/IR_SCHEMA.md` or
   `laserbench/core/ir.py` field names/semantics without a coordinator-approved
   entry in `docs/DECISIONS.md`. Additive optional fields still need an entry.
3. **Stay in your lane.** Only edit files your role owns
   (`docs/ARCHITECTURE.md` §7). Need a change elsewhere? Message the owner.
4. **No laser I/O.** Nothing in this repo opens USB, serial, or network
   connections to a laser. The only external action is launching a
   user-configured command with an exported file path.
5. **Units are millimetres** everywhere internally. Convert at the edges.
6. **Do not guess on open decisions.** If a task depends on an item marked
   `OPEN` in `docs/DECISIONS.md`, stop and escalate to the coordinator.
7. **Every task ends green:** relevant tests pass, `ruff check` clean,
   acceptance criteria in `docs/TASKS.md` demonstrably met.

## Tech constraints

- FreeCAD **1.0 or later** (bundled Python 3.11). Verify against the current
  stable release before pinning; record the result in `docs/DECISIONS.md`.
- Qt via FreeCAD's shim: `from PySide import QtCore, QtGui` (not PySide2/6
  directly) so the code survives FreeCAD's Qt migrations.
- No third-party Python dependencies inside the workbench. FreeCAD's bundled
  interpreter makes pip installs painful for end users.
- Must run on macOS (Apple Silicon), Linux, and Windows.
- Licence: LGPL-2.1-or-later (D-010). New source files start with
  `# SPDX-License-Identifier: LGPL-2.1-or-later`.

## Commands

```bash
# Pure-Python core tests (fast, no FreeCAD needed)
pytest tests/core -q

# FreeCAD-dependent tests (headless)
freecadcmd tests/fc/run_all.py
# macOS: /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd tests/fc/run_all.py

# Lint
ruff check .

# Install for manual testing: either clone straight into FreeCAD's Mod dir
# (e.g. ~/.local/share/FreeCAD/v1-1/Mod/FreeCAD_meerk40t), or symlink a checkout there:
python tools/dev_install.py
```

## Repository layout

The **repository root is the FreeCAD addon folder** (D-014): FreeCAD loads `Init.py` and
`InitGui.py` from the root and puts the root on `sys.path`, so `import laserbench` works.

```
Init.py                # non-GUI init (keep trivial)
InitGui.py             # workbench registration (lazy imports only)
package.xml            # Addon Manager metadata
laserbench/            # the Python package
  __init__.py
  api.py               # public scripting facade (FR-080)
  core/                # PURE PYTHON — no FreeCAD imports
  fc/                  # FreeCAD geometry adapters (Part/OCC)
  objects/             # FeaturePython proxies (Job, Operation, Machine ref)
  gui/                 # commands, view providers, task panels, prefs page
  resources/           # icons, default presets JSON, UI files
tests/
  core/                # pytest
  fc/                  # freecadcmd-run tests (run_all.py)
  fixtures/            # scripts that BUILD .FCStd fixtures (don't commit binaries)
docs/
tools/
pyproject.toml         # ruff/pytest config only; not a pip package
```

## Style

- Python 3.11, type hints on all public functions, dataclasses for data.
- `ruff` defaults plus isort. Line length 100.
- Docstrings on public API; comments explain *why*, not *what*.
- User-facing strings wrapped for translation: `QT_TRANSLATE_NOOP` /
  `FreeCAD.Qt.translate` in GUI code.
