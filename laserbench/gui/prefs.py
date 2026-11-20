# SPDX-License-Identifier: LGPL-2.1-or-later
"""Preferences page for machine profiles and material presets (FR-013). Task P-04.

Owned by presets-dev for P-04 (ARCHITECTURE §7).
"""

from __future__ import annotations

from typing import Any


class LaserBenchPrefsPage:
    """Qt widget page registered with FreeCADGui.addPreferencePage."""

    def __init__(self, parent: Any = None) -> None:
        raise NotImplementedError("P-04")

    def saveSettings(self) -> None:  # noqa: N802
        raise NotImplementedError("P-04")

    def loadSettings(self) -> None:  # noqa: N802
        raise NotImplementedError("P-04")
