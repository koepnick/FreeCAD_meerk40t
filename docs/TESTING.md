# Testing — LaserBench

## Two test suites

| Suite | Location | Runs under | What goes there |
|---|---|---|---|
| core | `tests/core/` | plain CPython 3.11+, `pytest` | everything in `laserbench/core/` |
| fc | `tests/fc/` | `freecadcmd`, `unittest` | anything that needs FreeCAD or Part |

```bash
pytest tests/core -q                                  # fast, no FreeCAD
pytest tests/core -q --cov=laserbench/core --cov-report=term-missing
freecadcmd tests/fc/run_all.py                        # Linux
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd tests/fc/run_all.py   # macOS
ruff check .
```

Run commands from the repository root. `run_all.py` discovers `tests/fc/test_*.py`.

## Rules
- `tests/core/test_layering.py` must stay green: it fails if any `core/` module imports
  something outside the standard library (NFR-001).
- `core/` line coverage ≥ 90% (NFR-009). Every P0 requirement has at least one automated test;
  name the requirement ID in the test's docstring or module docstring.
- Tests are deterministic: no clocks, no randomness without a fixed seed, no network.
- Don't commit `.FCStd` binaries. Fixtures are built by scripts in `tests/fixtures/` (Q-01).
- Golden files (SVG, JSON) live next to the tests that use them and are compared structurally
  where formatting is not part of the contract.

## CI
`.github/workflows/ci.yml` runs ruff + the core suite on CPython 3.11, and the fc suite under
`freecadcmd` from conda-forge's `freecad` package.

### Install check (real Mod folder)
`tests/gui` puts the repository on `sys.path` itself, so it never runs `InitGui.py` the way
FreeCAD does at startup (via `exec()` with separate globals and locals). The install check
copies the repo into a throwaway `~/.local/share/FreeCAD/v1-1/Mod/FreeCAD_meerk40t`, starts the
real GUI and fails unless the LaserBench workbench is listed, activates and registers its
commands. Run it after touching `InitGui.py`, `Init.py` or `package.xml`:

```bash
xvfb-run -a python tests/install/check_mod_install.py [--freecad /path/to/freecad]
```
