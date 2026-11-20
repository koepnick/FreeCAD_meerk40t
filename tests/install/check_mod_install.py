# SPDX-License-Identifier: LGPL-2.1-or-later
"""Install LaserBench the way a user does, start the real FreeCAD GUI, check it loads.

The GUI tests in tests/gui put the repository on sys.path themselves, so they never run
InitGui.py the way FreeCAD does at startup. This script does: it copies the repository
into ``<fake home>/.local/share/FreeCAD/v1-1/Mod/FreeCAD_meerk40t`` (what a git clone or the
Addon Manager produces), starts ``freecad`` with a throwaway HOME, and fails if the
LaserBench workbench is missing, can't be activated, or FreeCAD logged an init error.

    xvfb-run -a python tests/install/check_mod_install.py [--freecad PATH]

Plain Python (any 3.x); it only drives FreeCAD as a subprocess. Linux only.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).resolve().with_name("probe_gui.py")
FOLDER_NAME = "FreeCAD_meerk40t"  # what `git clone` of this repo produces


def install(home: Path) -> Path:
    mod = home / ".local" / "share" / "FreeCAD" / "v1-1" / "Mod" / FOLDER_NAME
    shutil.copytree(REPO_ROOT, mod, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "result.txt"))
    return mod


def run(freecad: str, timeout: int) -> int:
    with tempfile.TemporaryDirectory(prefix="lb-install-") as tmp:
        home = Path(tmp)
        mod = install(home)
        out = home / "probe.txt"
        env = dict(os.environ, HOME=str(home), LB_PROBE_OUT=str(out),
                   XDG_DATA_HOME=str(home / ".local" / "share"),
                   XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_CACHE_HOME=str(home / ".cache"))
        # cwd is the fake home so the repo checkout itself is not importable by accident.
        proc = subprocess.run([freecad, str(PROBE)], cwd=home, env=env, timeout=timeout,
                              capture_output=True, text=True, errors="replace")
        log = proc.stdout + proc.stderr
        report = out.read_text(encoding="utf-8") if out.exists() else ""
        print(report or "(probe wrote no report)")

        problems = []
        init_errors = [ln for ln in log.splitlines()
                       if "During initialization the error" in ln and FOLDER_NAME in ln]
        problems += [f"FreeCAD init error: {ln.strip()}" for ln in init_errors]
        fields = dict(ln.split(": ", 1) for ln in report.splitlines() if ": " in ln)
        if "LaserBenchWorkbench" not in fields.get("workbenches", "").split():
            problems.append("LaserBenchWorkbench is not in FreeCADGui.listWorkbenches()")
        else:
            if fields.get("active") != "LaserBenchWorkbench":
                problems.append(f"activating LaserBench gave {fields.get('active')!r}")
            if "LaserBench_CreateJob" not in fields.get("commands", "").split():
                problems.append("LaserBench commands were not registered on activation")
            if not fields.get("icon", "").endswith("laserbench.svg") or \
                    not Path(fields["icon"]).is_file():
                problems.append(f"workbench icon missing: {fields.get('icon')!r}")
            if not fields.get("module", "").startswith(str(mod)):
                problems.append(f"laserbench imported from {fields.get('module')!r}, "
                                f"not from the installed copy {mod}")
        if "probe error" in report:
            problems.append("the probe raised inside FreeCAD (see report above)")
        if problems:
            print("FreeCAD output:\n" + log)
            print("FAIL\n" + "\n".join(f"  - {p}" for p in problems))
            return 1
        print("OK")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freecad", default=shutil.which("freecad") or "freecad",
                        help="FreeCAD GUI executable (default: freecad on PATH)")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    return run(args.freecad, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
