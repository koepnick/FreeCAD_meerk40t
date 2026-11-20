# SPDX-License-Identifier: LGPL-2.1-or-later
"""Runs inside the FreeCAD GUI started by check_mod_install.py. Not a unittest module.

Reports which workbenches FreeCAD registered from the user's Mod folder, and whether
LaserBench activates and registers its commands, to the file named by LB_PROBE_OUT.
"""

import os
import traceback

out_path = os.environ["LB_PROBE_OUT"]
lines = []
try:
    import FreeCAD
    import FreeCADGui

    workbenches = FreeCADGui.listWorkbenches()
    lines.append("workbenches: " + " ".join(sorted(workbenches)))
    wb = workbenches.get("LaserBenchWorkbench")
    if wb is not None:
        lines.append("icon: " + str(getattr(wb, "Icon", "")))
        FreeCADGui.activateWorkbench("LaserBenchWorkbench")
        lines.append("active: " + FreeCADGui.activeWorkbench().name())
        lines.append("commands: " + " ".join(
            c for c in FreeCADGui.listCommands() if c.startswith("LaserBench_")))
        lines.append("module: " + __import__("laserbench").__file__)
    lines.append("freecad: " + ".".join(FreeCAD.Version()[:3]))
except BaseException:  # noqa: BLE001 - report everything, the GUI would swallow it
    lines.append("probe error:\n" + traceback.format_exc())
with open(out_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
os._exit(0)
