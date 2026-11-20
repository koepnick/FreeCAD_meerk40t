# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run the FreeCAD-dependent tests under freecadcmd.

    freecadcmd tests/fc/run_all.py

freecadcmd executes this file with exec(), so ``__file__`` may be missing and a
plain ``sys.exit`` code is not always propagated. We locate the tests from the
current directory as a fallback and exit with ``os._exit`` so CI sees failures.

freecadcmd also reports an exception escaping this script and then exits 0, so any
crash of the runner itself is caught here and turned into a non-zero exit code.
Output is written with ``backslashreplace`` so a non-ASCII docstring can't crash the
runner on a machine whose console encoding is ASCII.
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
        return Path.cwd() / "tests" / "fc"


def main() -> int:
    tests_dir = _tests_dir()
    repo_root = tests_dir.parent.parent
    for p in (str(repo_root), str(tests_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_*.py",
                                                top_level_dir=str(tests_dir))
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    return 0 if result.wasSuccessful() else 1


try:
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(errors="backslashreplace")
    code = main()
except BaseException:  # noqa: BLE001 - anything escaping here would otherwise exit 0
    traceback.print_exc()
    code = 2
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
