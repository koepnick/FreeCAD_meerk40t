# SPDX-License-Identifier: LGPL-2.1-or-later
"""C-03: every FreeCAD-side interface module imports under freecadcmd and is documented."""

import importlib
import inspect
import unittest

MODULES = (
    "laserbench.api",
    "laserbench.fc.extract",
    "laserbench.fc.kerf",
    "laserbench.fc.preview",
    "laserbench.fc.to_ir",
    "laserbench.objects.job",
    "laserbench.objects.operation",
    "laserbench.gui.commands",
    "laserbench.gui.panels.validation",
    "laserbench.gui.prefs",
    "laserbench.gui.viewproviders",
)


class TestInterfaces(unittest.TestCase):
    def test_modules_import_and_are_documented(self) -> None:
        for name in MODULES:
            with self.subTest(module=name):
                module = importlib.import_module(name)
                self.assertTrue(module.__doc__, f"{name} needs a module docstring")
                for attr, obj in vars(module).items():
                    if attr.startswith("_") or getattr(obj, "__module__", None) != name:
                        continue
                    if inspect.isfunction(obj):
                        self.assertTrue(obj.__doc__, f"{name}.{attr} needs a docstring")

    def test_source_error_names_the_sub_element(self) -> None:
        from laserbench.fc.extract import LBSourceError

        err = LBSourceError("Pad", "Face6", "missing")
        self.assertEqual((err.label, err.subname), ("Pad", "Face6"))
        self.assertIn("Pad.Face6", str(err))
