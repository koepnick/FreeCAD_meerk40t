# SPDX-License-Identifier: LGPL-2.1-or-later
# LaserBench workbench registration.
#
# FreeCAD executes this file at GUI startup. Nothing here may import the
# laserbench package eagerly: commands import their modules lazily so a
# broken optional piece never produces a traceback on load (FR-003).

import os

import FreeCAD
import FreeCADGui


def _icon_path() -> str:
    # FreeCAD runs this file via exec(), so __file__ is not reliable. The
    # Mod folder that contains this file is on sys.path, and the laserbench
    # package lives inside it.
    import laserbench

    return os.path.join(os.path.dirname(laserbench.__file__), "resources", "icons",
                        "laserbench.svg")


class LaserBenchWorkbench(FreeCADGui.Workbench):
    MenuText = FreeCAD.Qt.translate("Workbench", "LaserBench")
    ToolTip = FreeCAD.Qt.translate(
        "Workbench", "Turn parametric FreeCAD geometry into laser jobs"
    )
    Icon = _icon_path()

    def Initialize(self) -> None:
        # Commands are registered here in later tasks (W-04, W-07).
        self.appendToolbar("LaserBench", [])
        self.appendMenu("LaserBench", [])

    def Activated(self) -> None:
        pass

    def Deactivated(self) -> None:
        pass

    def GetClassName(self) -> str:
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(LaserBenchWorkbench())
