# SPDX-License-Identifier: LGPL-2.1-or-later
"""K-01: preset ⊕ override merge (FR-021, FR-044)."""

from __future__ import annotations

import pytest

from laserbench.core.ir import IROperation
from laserbench.core.settings import coerce_value, merge_settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("65", 65),
        ("-3", -3),
        (" 12 ", 12),
        ("0.1", 0.1),
        ("1e3", 1000.0),
        ("true", True),
        ("FALSE", False),
        (" True ", True),
        ("fast", "fast"),
        ("", ""),
        ("inf", "inf"),
        ("nan", "nan"),
        ("1,5", "1,5"),
        (7, 7),
        (2.5, 2.5),
        (False, False),
    ],
)
def test_coerce_value(raw, expected) -> None:
    got = coerce_value(raw)
    assert got == expected
    assert type(got) is type(expected)


def test_override_wins_over_preset() -> None:
    preset = {"power": 60, "speed": 20.0, "passes": 1}
    merged = merge_settings(preset, {"power": "45", "passes": "2"})
    assert merged == {"passes": 2, "power": 45, "speed": 20.0}


def test_unknown_keys_from_both_sides_are_kept() -> None:
    merged = merge_settings({"meerk40t.dratio": "0.261"}, {"air_assist": "true"})
    assert merged == {"air_assist": True, "meerk40t.dratio": 0.261}


def test_preset_strings_are_coerced_too() -> None:
    assert merge_settings({"speed": "20"}, {}) == {"speed": 20}


def test_keys_are_sorted_and_inputs_untouched() -> None:
    preset = {"speed": 1, "air": "true"}
    overrides = {"power": "5"}
    merged = merge_settings(preset, overrides)
    assert list(merged) == ["air", "power", "speed"]
    assert preset == {"speed": 1, "air": "true"} and overrides == {"power": "5"}


def test_merged_settings_are_valid_ir() -> None:
    """FR-044: the merged result goes straight into an IROperation."""
    merged = merge_settings({"power": 60.0, "mode": "cut"}, {"power": "70.5", "x": "inf"})
    op = IROperation(id="op1", label="Cut", type="cut", order=0, colour="#ff0000",
                     settings=merged)
    assert op.to_dict()["settings"] == {"mode": "cut", "power": 70.5, "x": "inf"}
