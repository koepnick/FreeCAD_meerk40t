# SPDX-License-Identifier: LGPL-2.1-or-later
"""Merge preset settings with per-operation overrides (FR-021, FR-044). Task K-01.

Settings are opaque pass-through values. Precedence, lowest to highest:
material preset for the operation type < operation overrides. Unknown keys are kept.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from laserbench.core.ir import SettingValue

_INT_RE = re.compile(r"^[+-]?\d+$")
_BOOLS = {"true": True, "false": False}


def coerce_value(raw: SettingValue) -> SettingValue:
    """Turn a string from a PropertyMap into int, float or bool where it parses as one.

    "65" becomes 65, "0.1" becomes 0.1, "true"/"false" become booleans
    (case-insensitive). Other strings and non-strings are returned unchanged.

    Surrounding whitespace is ignored when parsing. "inf" and "nan" stay strings, because
    the IR only holds finite numbers.
    """
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text.lower() in _BOOLS:
        return _BOOLS[text.lower()]
    if _INT_RE.match(text):
        return int(text)
    try:
        number = float(text)
    except ValueError:
        return raw
    return number if math.isfinite(number) else raw


def merge_settings(
    preset: Mapping[str, SettingValue],
    overrides: Mapping[str, SettingValue],
) -> dict[str, SettingValue]:
    """Return preset settings with overrides applied on top, values coerced, keys sorted.

    Every key from either side is kept, including ones LaserBench doesn't know (FR-021).
    """
    merged = {**preset, **overrides}
    return {key: coerce_value(merged[key]) for key in sorted(merged)}
