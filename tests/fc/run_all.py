"""Run the FreeCAD-dependent tests under freecadcmd.

    freecadcmd tests/fc/run_all.py

freecadcmd executes this file with exec(), so ``__file__`` may be missing and a
plain ``sys.exit`` code is not always propagated. We locate the tests from the
current directory as a fallback and exit with ``os._exit`` so CI sees failures.
"""

import os
import sys
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


code = main()
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
