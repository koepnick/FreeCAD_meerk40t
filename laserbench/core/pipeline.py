# SPDX-License-Identifier: LGPL-2.1-or-later
"""The pure-Python half of LaserJob.execute (ARCHITECTURE §3, steps 2-5).

Owned by core-dev; called by objects/job.py (W-03). Keeping it here means the whole job
pipeline after geometry extraction is testable with plain pytest.
"""

from __future__ import annotations

from collections.abc import Mapping

from laserbench.core.ir import (
    IRIssue,
    IRJob,
    IRMachine,
    IRMaterial,
    IROperation,
    SettingValue,
)


def assemble_job(
    name: str,
    machine: IRMachine,
    material: IRMaterial,
    fragments: list[IROperation],
    preset_settings: Mapping[str, Mapping[str, SettingValue]],
    fragment_issues: list[IRIssue] | None = None,
    source_document: str = "",
) -> IRJob:
    """Build the final IRJob from per-operation fragments in the job frame.

    Steps: sort by order → merge settings (settings.py) → dedupe → order paths →
    transform to the machine frame (coords.py) → compute bounds → validate.
    ``fragments`` carry operation overrides in ``settings``; ``preset_settings`` maps
    operation type to the material preset's settings. ``fragment_issues`` are issues
    raised while building fragments (BROKEN_SOURCE, KERF_COLLAPSE, GEOMETRY_ERROR); they
    are kept ahead of the validation issues.
    """
    raise NotImplementedError("W-03 / K-01..K-05")
