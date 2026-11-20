# SPDX-License-Identifier: LGPL-2.1-or-later
"""Machine profiles and material presets (FR-010, FR-020, NFR-007). Task P-01.

File formats: IR_SCHEMA.md §4. The caller passes the data folder (normally
``FreeCAD.getUserAppDataDir()/LaserBench``) so this module stays FreeCAD-free.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from laserbench.core.ir import (
    OP_TYPES,
    SCHEMA_VERSION,
    IRError,
    IRMachine,
    IRMaterial,
    SettingValue,
    check_schema_version,
)

MACHINES_FILE = "machines.json"
MATERIALS_FILE = "materials.json"
#: Bundled first-run data (task P-02), copied by ensure_defaults.
DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "resources" / "defaults"


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
        return IRMachine(id=self.id, name=self.name, kind=self.kind, width=self.width,
                         height=self.height, origin=self.origin)

    def to_dict(self) -> dict[str, Any]:
        """The machines.json entry for this profile (IR_SCHEMA §4)."""
        return {"id": self.id, "name": self.name, "kind": self.kind, "width": self.width,
                "height": self.height, "origin": self.origin,
                "default_kerf": self.default_kerf, "send_command": list(self.send_command)}

    @classmethod
    def from_dict(cls, data: Any) -> MachineProfile:
        """Parse and validate one machines.json entry; raises PresetError."""
        d = _object(data, "machine", ("id", "name", "kind", "width", "height", "origin"),
                    ("default_kerf", "send_command"))
        where = f"machine {d['id']!r}"
        command = d.get("send_command", [])
        if not isinstance(command, list) or not all(isinstance(a, str) for a in command):
            raise PresetError(f"{where}: send_command must be a list of strings")
        profile = cls(id=d["id"], name=d["name"], kind=d["kind"], width=d["width"],
                      height=d["height"], origin=d["origin"],
                      default_kerf=_length(d.get("default_kerf", 0.0), f"{where}.default_kerf"),
                      send_command=list(command))
        try:
            ir = profile.to_ir()  # checks id, kind, size and origin with the IR's rules
        except IRError as exc:
            raise PresetError(f"{where}: {exc}") from exc
        profile.width, profile.height = ir.width, ir.height
        return profile


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
        return IRMaterial(id=self.id, name=self.name, thickness=self.thickness, kerf=self.kerf)

    def settings_for(self, op_type: str) -> dict[str, SettingValue]:
        """Settings for one operation type, with ``kerf`` included for cut."""
        settings = dict(self.settings.get(op_type.lower(), {}))
        if op_type.lower() == "cut":
            settings["kerf"] = self.kerf
        return settings

    def to_dict(self) -> dict[str, Any]:
        """The materials.json entry for this preset (IR_SCHEMA §4)."""
        return {"id": self.id, "machine_id": self.machine_id, "name": self.name,
                "thickness": self.thickness, "kerf": self.kerf,
                "settings": {t: dict(v) for t, v in self.settings.items()}}

    @classmethod
    def from_dict(cls, data: Any) -> MaterialPreset:
        """Parse and validate one materials.json entry; raises PresetError."""
        d = _object(data, "material", ("id", "machine_id", "name", "thickness", "kerf"),
                    ("settings",))
        where = f"material {d['id']!r}"
        settings = d.get("settings", {})
        if not isinstance(settings, Mapping):
            raise PresetError(f"{where}: settings must be an object")
        parsed: dict[str, dict[str, SettingValue]] = {}
        for op_type, values in settings.items():
            if op_type not in OP_TYPES:
                raise PresetError(f"{where}: unknown operation type {op_type!r} in settings")
            if not isinstance(values, Mapping):
                raise PresetError(f"{where}: settings.{op_type} must be an object")
            for key, value in values.items():
                if not isinstance(value, str | int | float | bool) or (
                        isinstance(value, float) and not math.isfinite(value)):
                    raise PresetError(f"{where}: settings.{op_type}.{key} must be a string, "
                                      "number or boolean")
            parsed[op_type] = dict(values)
        preset = cls(id=d["id"], machine_id=_text(d["machine_id"], f"{where}.machine_id"),
                     name=d["name"], thickness=_length(d["thickness"], f"{where}.thickness"),
                     kerf=_length(d["kerf"], f"{where}.kerf"), settings=parsed)
        try:
            preset.to_ir()
        except IRError as exc:
            raise PresetError(f"{where}: {exc}") from exc
        return preset


def load_machines(data_dir: Path) -> list[MachineProfile]:
    """Read machines.json from ``data_dir``; raises PresetError on bad data or version."""
    items = _read(data_dir / MACHINES_FILE, "machines")
    machines = [MachineProfile.from_dict(item) for item in items]
    _unique([m.id for m in machines], MACHINES_FILE)
    return machines


def save_machines(data_dir: Path, machines: list[MachineProfile]) -> None:
    """Write machines.json atomically, with the current schema_version."""
    _unique([m.id for m in machines], MACHINES_FILE)
    _write(data_dir / MACHINES_FILE, "machines", [m.to_dict() for m in machines])


def load_materials(data_dir: Path) -> list[MaterialPreset]:
    """Read materials.json from ``data_dir``; raises PresetError on bad data or version."""
    items = _read(data_dir / MATERIALS_FILE, "materials")
    materials = [MaterialPreset.from_dict(item) for item in items]
    _unique([f"{m.machine_id}/{m.id}" for m in materials], MATERIALS_FILE)
    return materials


def save_materials(data_dir: Path, materials: list[MaterialPreset]) -> None:
    """Write materials.json atomically, with the current schema_version."""
    _unique([f"{m.machine_id}/{m.id}" for m in materials], MATERIALS_FILE)
    _write(data_dir / MATERIALS_FILE, "materials", [m.to_dict() for m in materials])


def ensure_defaults(data_dir: Path, defaults_dir: Path | None = None) -> None:
    """On first run, copy the bundled default profiles and presets into ``data_dir`` (FR-012).

    Only missing files are created, so user edits are never overwritten. A file with no
    bundled default starts as an empty list.
    """
    source = DEFAULTS_DIR if defaults_dir is None else defaults_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, key in ((MACHINES_FILE, "machines"), (MATERIALS_FILE, "materials")):
        target = data_dir / name
        if target.exists():
            continue
        bundled = source / name
        if bundled.is_file():
            shutil.copyfile(bundled, target)
        else:
            _write(target, key, [])


def find_machine(machines: list[MachineProfile], machine_id: str) -> MachineProfile:
    """The profile with ``machine_id``; raises KeyError naming it."""
    for m in machines:
        if m.id == machine_id:
            return m
    raise KeyError(f"no machine profile {machine_id!r}")


def find_material(materials: list[MaterialPreset], machine_id: str, material_id: str
                  ) -> MaterialPreset:
    """The preset ``material_id`` for ``machine_id``; raises KeyError naming both."""
    for m in materials:
        if m.machine_id == machine_id and m.id == material_id:
            return m
    raise KeyError(f"no material preset {material_id!r} for machine {machine_id!r}")


# --- helpers ---------------------------------------------------------------------------


def _object(data: Any, what: str, required: tuple[str, ...], optional: tuple[str, ...] = ()
            ) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise PresetError(f"each {what} must be an object")
    label = data.get("id", "?")
    missing = [k for k in required if k not in data]
    if missing:
        raise PresetError(f"{what} {label!r}: missing field(s) {', '.join(missing)}")
    unknown = sorted(set(data) - set(required) - set(optional))
    if unknown:
        raise PresetError(f"{what} {label!r}: unknown field(s) {', '.join(unknown)}")
    return data


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise PresetError(f"{where}: expected a non-empty string")
    return value


def _length(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise PresetError(f"{where}: expected a finite number")
    if value < 0:
        raise PresetError(f"{where}: must not be negative")
    return float(value)


def _unique(keys: list[str], filename: str) -> None:
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise PresetError(f"{filename}: duplicate id(s) {', '.join(dupes)}")


def _read(path: Path, key: str) -> list[Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PresetError(f"{path.name} not found in {path.parent}") from exc
    except (OSError, ValueError) as exc:
        raise PresetError(f"{path.name}: cannot read ({exc})") from exc
    if not isinstance(data, Mapping):
        raise PresetError(f"{path.name}: expected a JSON object")
    try:
        check_schema_version(data)
    except IRError as exc:
        raise PresetError(f"{path.name}: {exc}") from exc
    unknown = sorted(set(data) - {"schema_version", key})
    if unknown:
        raise PresetError(f"{path.name}: unknown field(s) {', '.join(unknown)}")
    items = data.get(key)
    if not isinstance(items, list):
        raise PresetError(f"{path.name}: {key!r} must be a list")
    return items


def _write(path: Path, key: str, items: list[dict[str, Any]]) -> None:
    """Write via a temporary file in the same folder and an atomic rename."""
    # core/fsutil.py (K-07) will offer the same; switch to it once it lands.
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"schema_version": SCHEMA_VERSION, key: items}, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
