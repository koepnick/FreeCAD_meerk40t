# SPDX-License-Identifier: LGPL-2.1-or-later
"""Kerf compensation with Part.Face.makeOffset2D (FR-050, FR-064). Task G-03."""

from __future__ import annotations

import Part

from laserbench.core.ir import IRIssue

KERF_MODES = ("Auto", "Outside", "Inside", "None")


def compensate(
    wires: list[Part.Wire], kerf: float, mode: str, operation_id: str
) -> tuple[list[Part.Wire], list[IRIssue]]:
    """Offset closed wires by kerf/2 so parts come out at nominal size.

    Auto: outer boundaries outward, holes inward (nesting-depth parity decides).
    Open wires pass through unchanged. A loop whose offset vanishes is dropped and
    reported as KERF_COLLAPSE.
    """
    raise NotImplementedError("G-03")
