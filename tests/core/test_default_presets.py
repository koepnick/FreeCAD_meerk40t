# SPDX-License-Identifier: LGPL-2.1-or-later
"""P-02: the bundled first-run profiles match the owner's machines (FR-012, D-012).

Checked with the IR dataclasses and plain JSON so this test doesn't depend on the loader.
"""

from __future__ import annotations

import json
from pathlib import Path

from laserbench.core.ir import OP_TYPES, IRMachine, IRMaterial

DEFAULTS = Path(__file__).resolve().parents[2] / "laserbench" / "resources" / "defaults"


def load(name: str) -> dict:
    return json.loads((DEFAULTS / name).read_text(encoding="utf-8"))


def test_machines_match_d012() -> None:
    data = load("machines.json")
    assert data["schema_version"] == 1
    machines = {m["id"]: m for m in data["machines"]}
    assert len(machines) == len(data["machines"]) == 2
    co2, fiber = machines["co2-mf1624"], machines["fiber-50w"]
    assert (co2["kind"], co2["width"], co2["height"], co2["origin"]) == (
        "gantry", 600.0, 400.0, "rear-left")
    assert (fiber["kind"], fiber["width"], fiber["height"], fiber["origin"]) == (
        "galvo", 150.0, 150.0, "center")
    for m in machines.values():
        IRMachine(**{k: m[k] for k in ("id", "name", "kind", "width", "height", "origin")})
        assert m["default_kerf"] >= 0
        # No command until the user sets one up: launching a missing program on first
        # Send would only produce an error.
        assert m["send_command"] == []


def test_materials_are_valid_and_belong_to_a_default_machine() -> None:
    data = load("materials.json")
    assert data["schema_version"] == 1
    machine_ids = {m["id"] for m in load("machines.json")["machines"]}
    keys = [(m["machine_id"], m["id"]) for m in data["materials"]]
    assert len(keys) == len(set(keys))
    for m in data["materials"]:
        assert m["machine_id"] in machine_ids
        IRMaterial(id=m["id"], name=m["name"], thickness=m["thickness"], kerf=m["kerf"])
        assert "test first" in m["name"]  # starting points, not tuned values
        assert set(m["settings"]) <= set(OP_TYPES)
        for values in m["settings"].values():
            assert all(isinstance(v, str | int | float | bool) for v in values.values())
    assert {m["machine_id"] for m in data["materials"]} == machine_ids
