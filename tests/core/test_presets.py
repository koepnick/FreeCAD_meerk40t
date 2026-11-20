# SPDX-License-Identifier: LGPL-2.1-or-later
"""P-01: machine profiles and material presets on disk (FR-010, FR-020, NFR-007)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laserbench.core import presets
from laserbench.core.ir import IRMachine, IRMaterial
from laserbench.core.presets import (
    MachineProfile,
    MaterialPreset,
    PresetError,
    ensure_defaults,
    find_machine,
    find_material,
    load_machines,
    load_materials,
    save_machines,
    save_materials,
)

CO2 = {"id": "co2", "name": "CO2 gantry", "kind": "gantry", "width": 600.0, "height": 400.0,
       "origin": "rear-left", "default_kerf": 0.2, "send_command": ["meerk40t", "{svg}"]}
PLY = {"id": "ply3", "machine_id": "co2", "name": "Birch ply 3 mm", "thickness": 3.0,
       "kerf": 0.2,
       "settings": {"cut": {"power": 65, "speed": 20, "passes": 1},
                    "score": {"power": 20, "speed": 200},
                    "fill": {"power": 30, "speed": 300, "hatch_interval": 0.1}}}


def write(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_schema_example_round_trips(tmp_path: Path) -> None:
    """IR_SCHEMA §4's examples load, save and load again unchanged."""
    write(tmp_path / "machines.json", {"schema_version": 1, "machines": [CO2]})
    write(tmp_path / "materials.json", {"schema_version": 1, "materials": [PLY]})
    machines, materials = load_machines(tmp_path), load_materials(tmp_path)
    assert machines[0].to_dict() == CO2
    assert materials[0].to_dict() == PLY
    out = tmp_path / "out"
    save_machines(out, machines)
    save_materials(out, materials)
    assert load_machines(out) == machines and load_materials(out) == materials
    saved = json.loads((out / "machines.json").read_text())
    assert saved["schema_version"] == 1
    assert not [p for p in out.iterdir() if p.name.endswith(".tmp")]


def test_to_ir_and_settings_for() -> None:
    machine = MachineProfile.from_dict(CO2)
    material = MaterialPreset.from_dict(PLY)
    assert machine.to_ir() == IRMachine(id="co2", name="CO2 gantry", kind="gantry",
                                        width=600, height=400, origin="rear-left")
    assert material.to_ir() == IRMaterial(id="ply3", name="Birch ply 3 mm", thickness=3,
                                          kerf=0.2)
    assert material.settings_for("cut") == {"power": 65, "speed": 20, "passes": 1,
                                            "kerf": 0.2}
    assert material.settings_for("Score") == {"power": 20, "speed": 200}
    assert "kerf" not in material.settings_for("fill")
    material.settings_for("score")["power"] = 99  # a copy, not the preset itself
    assert material.settings["score"]["power"] == 20


def test_missing_optional_fields_default() -> None:
    m = MachineProfile.from_dict({k: v for k, v in CO2.items()
                                  if k not in ("default_kerf", "send_command")})
    assert (m.default_kerf, m.send_command) == (0.0, [])
    p = MaterialPreset.from_dict({k: v for k, v in PLY.items() if k != "settings"})
    assert p.settings == {} and p.settings_for("cut") == {"kerf": 0.2}


def test_unknown_settings_keys_pass_through(tmp_path: Path) -> None:
    """FR-021: a new key needs no code change."""
    ply = {**PLY, "settings": {"cut": {"q_pulse": 120, "air": True, "mode": "x"}}}
    p = MaterialPreset.from_dict(ply)
    assert p.settings_for("cut") == {"q_pulse": 120, "air": True, "mode": "x", "kerf": 0.2}


@pytest.mark.parametrize(("change", "message"), [
    ({"kind": "plasma"}, "kind"),
    ({"origin": "center"}, "origin"),
    ({"width": 0}, "positive"),
    ({"default_kerf": -1}, "negative"),
    ({"send_command": "meerk40t {svg}"}, "list of strings"),
    ({"colour": "red"}, "unknown field"),
    ({"id": ""}, "id"),
])
def test_bad_machine(change, message) -> None:
    with pytest.raises(PresetError, match=message):
        MachineProfile.from_dict({**CO2, **change})


def test_missing_machine_field() -> None:
    with pytest.raises(PresetError, match="missing field"):
        MachineProfile.from_dict({k: v for k, v in CO2.items() if k != "width"})


@pytest.mark.parametrize(("change", "message"), [
    ({"kerf": -0.1}, "negative"),
    ({"thickness": "3"}, "number"),
    ({"machine_id": ""}, "machine_id"),
    ({"settings": {"raster": {}}}, "unknown operation type"),
    ({"settings": {"cut": 5}}, "must be an object"),
    ({"settings": {"cut": {"power": [1, 2]}}}, "string, number or boolean"),
    ({"settings": {"cut": {"power": float("inf")}}}, "string, number or boolean"),
    ({"settings": []}, "must be an object"),
])
def test_bad_material(change, message) -> None:
    with pytest.raises(PresetError, match=message):
        MaterialPreset.from_dict({**PLY, **change})


@pytest.mark.parametrize(("data", "message"), [
    ({"machines": []}, "missing schema_version"),
    ({"schema_version": 2, "machines": []}, "newer"),
    ({"schema_version": 0, "machines": []}, "older"),
    ({"schema_version": 1}, "must be a list"),
    ({"schema_version": 1, "machines": [], "extra": 1}, "unknown field"),
    ([], "JSON object"),
    ({"schema_version": 1, "machines": [CO2, CO2]}, "duplicate"),
    ({"schema_version": 1, "machines": ["co2"]}, "must be an object"),
])
def test_bad_machines_file(tmp_path: Path, data, message) -> None:
    write(tmp_path / "machines.json", data)
    with pytest.raises(PresetError, match=message):
        load_machines(tmp_path)


def test_unreadable_and_missing_files(tmp_path: Path) -> None:
    (tmp_path / "materials.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PresetError, match="cannot read"):
        load_materials(tmp_path)
    with pytest.raises(PresetError, match="not found"):
        load_machines(tmp_path)


def test_same_material_id_on_two_machines_is_fine(tmp_path: Path) -> None:
    other = {**PLY, "machine_id": "galvo"}
    write(tmp_path / "materials.json", {"schema_version": 1, "materials": [PLY, other]})
    assert len(load_materials(tmp_path)) == 2
    write(tmp_path / "materials.json", {"schema_version": 1, "materials": [PLY, PLY]})
    with pytest.raises(PresetError, match="duplicate id"):
        load_materials(tmp_path)
    with pytest.raises(PresetError, match="duplicate id"):
        save_materials(tmp_path, [MaterialPreset.from_dict(PLY)] * 2)


def test_find_helpers() -> None:
    machines = [MachineProfile.from_dict(CO2)]
    materials = [MaterialPreset.from_dict(PLY)]
    assert find_machine(machines, "co2") is machines[0]
    assert find_material(materials, "co2", "ply3") is materials[0]
    with pytest.raises(KeyError, match="nope"):
        find_machine(machines, "nope")
    with pytest.raises(KeyError, match="ply3.*galvo"):
        find_material(materials, "galvo", "ply3")


def test_ensure_defaults_copies_bundled_files_once(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    write(bundled / "machines.json", {"schema_version": 1, "machines": [CO2]})
    data = tmp_path / "user" / "LaserBench"
    ensure_defaults(data, bundled)
    assert [m.id for m in load_machines(data)] == ["co2"]
    assert load_materials(data) == []  # no bundled materials: starts empty
    save_machines(data, [])  # the user deletes every profile...
    ensure_defaults(data, bundled)
    assert load_machines(data) == []  # ...and first-run defaults don't come back


def test_ensure_defaults_uses_the_package_folder_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(presets, "DEFAULTS_DIR", tmp_path / "missing")
    ensure_defaults(tmp_path / "data")
    assert load_machines(tmp_path / "data") == []
