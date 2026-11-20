# SPDX-License-Identifier: LGPL-2.1-or-later
"""LaserBench: a FreeCAD workbench that turns parametric geometry into laser jobs.

This package must stay importable without FreeCAD. Only ``laserbench.fc``,
``laserbench.objects`` and ``laserbench.gui`` may import FreeCAD, and only
inside those subpackages (see docs/ARCHITECTURE.md §2).
"""

__version__ = "0.1.0"
