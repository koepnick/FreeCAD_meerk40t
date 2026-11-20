# SPDX-License-Identifier: LGPL-2.1-or-later
# LaserBench workbench registration.
#
# FreeCAD executes this file at GUI startup. Nothing here may import the
# laserbench package eagerly: commands import their modules lazily so a
# broken optional piece never produces a traceback on load (FR-003).

import FreeCAD
import FreeCADGui

# FreeCAD runs this file with exec() inside one of its own functions, passing separate
# globals and locals. Names defined at the top of this file land in those locals, which a
# class body or a method can't see: a module-level helper called from the class body
# raised NameError and FreeCAD silently skipped the whole workbench. So everything the
# class needs is imported or computed inside the class itself. Only FreeCAD and FreeCADGui
# are safe to use bare, because FreeCAD's own init module already has them as globals.
# tests/gui/test_initgui_gui.py and tests/install/ guard this.


class LaserBenchWorkbench(FreeCADGui.Workbench):
    MenuText = FreeCAD.Qt.translate("Workbench", "LaserBench")
    ToolTip = FreeCAD.Qt.translate(
        "Workbench", "Turn parametric FreeCAD geometry into laser jobs"
    )

    def __init__(self) -> None:
        import os

        import laserbench

        # __file__ is unreliable under exec(); the Mod folder is on sys.path, so locate
        # the icon through the package instead.
        self.__class__.Icon = os.path.join(
            os.path.dirname(laserbench.__file__), "resources", "icons", "laserbench.svg"
        )

    def Initialize(self) -> None:
        # Imported here, not at file level, so a broken piece can't stop FreeCAD starting.
        from laserbench.gui import commands

        names = commands.register_commands()
        self.appendToolbar("LaserBench", names)
        self.appendMenu("LaserBench", names)

    def Activated(self) -> None:
        pass

    def Deactivated(self) -> None:
        pass

    def GetClassName(self) -> str:
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(LaserBenchWorkbench())
