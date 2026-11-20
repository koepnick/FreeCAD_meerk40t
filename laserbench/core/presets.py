# SPDX-License-Identifier: LGPL-2.1-or-later
"""Machine profiles and material presets (FR-010, FR-020, NFR-007). Task P-01.

File formats: IR_SCHEMA.md §4. The caller passes the data folder (normally
``FreeCAD.getUserAppDataDir()/LaserBench``) so this module stays FreeCAD-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from laserbench.core.ir import IRMachine, IRMaterial, SettingValue

MACHINES_FILE = "machines.json"
MATERIALS_FILE = "materials.json"


class PresetError(ValueError):
    """A profile or preset file is invalid or has an unsupported schema_version."""


@dataclass
class MachineProfile:
    """One laser machine (FR-010, FR-011). ``send_command`` is an argument list (FR-074)."""

    id: str
    name: str
    kind: str
    width: float
    height: float
    origin: str
    default_kerf: float = 0.0
    send_command: list[str] = field(default_factory=list)

    def to_ir(self) -> IRMachine:
        """Snapshot for an IRJob."""
        raise NotImplementedError("P-01")


@dataclass
class MaterialPreset:
    """Material settings for one machine, keyed by operation type (FR-020, FR-021)."""

    id: str
    machine_id: str
    name: str
    thickness: float
    kerf: float
    settings: dict[str, dict[str, SettingValue]] = field(default_factory=dict)

    def to_ir(self) -> IRMaterial:
        """Snapshot for an IRJob."""
        raise NotImplementedError("P-01")

    def settings_for(self, op_type: str) -> dict[str, SettingValue]:
        """Settings for one operation type, with ``kerf`` included for cut."""
        raise NotImplementedError("P-01")


def load_machines(data_dir: Path) -> list[MachineProfile]:
    """Read machines.json from ``data_dir``; raises PresetError on bad data or version."""
    raise NotImplementedError("P-01")


def save_machines(data_dir: Path, machines: list[MachineProfile]) -> None:
    """Write machines.json atomically, with the current schema_version."""
    raise NotImplementedError("P-01")


def load_materials(data_dir: Path) -> list[MaterialPreset]:
    """Read materials.json from ``data_dir``; raises PresetError on bad data or version."""
    raise NotImplementedError("P-01")


def save_materials(data_dir: Path, materials: list[MaterialPreset]) -> None:
    """Write materials.json atomically, with the current schema_version."""
    raise NotImplementedError("P-01")


def ensure_defaults(data_dir: Path) -> None:
    """On first run, copy the bundled default profiles and presets into ``data_dir`` (FR-012)."""
    raise NotImplementedError("P-01")
