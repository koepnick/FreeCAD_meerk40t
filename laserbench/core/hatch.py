# SPDX-License-Identifier: LGPL-2.1-or-later
"""Optional hatch generation for fill operations (FR-052, D-005). Phase 2."""

from __future__ import annotations

from laserbench.core.ir import IRPath, IRRegion


def hatch_regions(regions: list[IRRegion], interval: float, angle_deg: float = 0.0
                  ) -> list[IRPath]:
    """Parallel hatch lines spaced interval mm at angle_deg, clipped to the regions
    and their holes. Alternate lines reverse direction to cut travel."""
    raise NotImplementedError("FR-052 (phase 2)")
