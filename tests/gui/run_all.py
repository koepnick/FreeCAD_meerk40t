# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI smoke tests: run inside the full FreeCAD GUI, headless under a virtual display.

    xvfb-run -a freecad tests/gui/run_all.py      # Linux
    freecad tests/gui/run_all.py                  # with a display

FreeCAD's GUI doesn't echo stdout reliably, so the result goes to tests/gui/result.txt
and the process exits non-zero on failure. Kept separate from tests/fc because freecadcmd
has no GUI.
"""

import os
import sys
import traceback
import unittest
from pathlib import Path


def _tests_dir() -> Path:
    try:
        return Path(__file__).resolve().parent
    except NameError:
        return Path.cwd() / "tests" / "gui"


def main() -> int:
    tests_dir = _tests_dir()
    repo_root = tests_dir.parent.parent
    for p in (str(repo_root), str(tests_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)
    out = tests_dir / "result.txt"
    with out.open("w", encoding="utf-8", errors="backslashreplace") as stream:
        suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_*.py",
                                                    top_level_dir=str(tests_dir))
        result = unittest.TextTestRunner(verbosity=2, stream=stream).run(suite)
    return 0 if result.wasSuccessful() else 1


try:
    code = main()
except BaseException:  # noqa: BLE001 - anything escaping would otherwise exit 0
    with (_tests_dir() / "result.txt").open("a", encoding="utf-8") as fh:
        traceback.print_exc(file=fh)
    code = 2
os._exit(code)
