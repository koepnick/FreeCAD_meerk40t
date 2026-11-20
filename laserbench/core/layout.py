# SPDX-License-Identifier: LGPL-2.1-or-later
"""Simple layout of parts in the work area (FR-048, ARCHITECTURE §8). Phase 3."""

from __future__ import annotations

from dataclasses import dataclass

from laserbench.core.ir import IRBounds


@dataclass(frozen=True)
class Placement:
    """Where a part goes: translation in mm and rotation in degrees about Z."""

    x: float
    y: float
    rotation: float = 0.0


def shelf_pack(sizes: list[tuple[float, float]], area: IRBounds, spacing: float = 2.0
               ) -> list[Placement | None]:
    """Shelf-pack bounding boxes into ``area``. None marks a part that does not fit."""
    raise NotImplementedError("FR-048 (phase 3)")
