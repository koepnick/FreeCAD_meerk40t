# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI commands (FR-030, FR-032, FR-040, FR-070 to FR-074). Tasks W-04, W-07.

Imports FreeCADGui and Qt lazily inside functions so this module imports headless.
"""

from __future__ import annotations

COMMANDS: tuple[str, ...] = (
    "LaserBench_CreateJob",
    "LaserBench_AddOperation",
    "LaserBench_Validate",
    "LaserBench_Export",
    "LaserBench_Send",
)


def register_commands() -> list[str]:
    """Register every command with FreeCADGui and return their names (for InitGui)."""
    raise NotImplementedError("W-04")
