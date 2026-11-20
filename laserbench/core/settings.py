# SPDX-License-Identifier: LGPL-2.1-or-later
"""Merge preset settings with per-operation overrides (FR-021, FR-044). Task K-01.

Settings are opaque pass-through values. Precedence, lowest to highest:
material preset for the operation type < operation overrides. Unknown keys are kept.
"""

from __future__ import annotations

from collections.abc import Mapping

from laserbench.core.ir import SettingValue


def coerce_value(raw: SettingValue) -> SettingValue:
    """Turn a string from a PropertyMap into int, float or bool where it parses as one.

    "65" becomes 65, "0.1" becomes 0.1, "true"/"false" become booleans
    (case-insensitive). Other strings and non-strings are returned unchanged.
    """
    raise NotImplementedError("K-01")


def merge_settings(
    preset: Mapping[str, SettingValue],
    overrides: Mapping[str, SettingValue],
) -> dict[str, SettingValue]:
    """Return preset settings with overrides applied on top, values coerced, keys sorted."""
    raise NotImplementedError("K-01")
