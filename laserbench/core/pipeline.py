# SPDX-License-Identifier: LGPL-2.1-or-later
"""The pure-Python half of LaserJob.execute (ARCHITECTURE §3, steps 2-5).

Owned by core-dev; called by objects/job.py (W-03). Keeping it here means the whole job
pipeline after geometry extraction is testable with plain pytest.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from laserbench.core import coords
from laserbench.core.dedupe import dedupe_paths
from laserbench.core.ir import (
    IRBounds,
    IRIssue,
    IRJob,
    IRMachine,
    IRMaterial,
    IROperation,
    Point,
    SettingValue,
)
from laserbench.core.ordering import order_paths
from laserbench.core.settings import merge_settings
from laserbench.core.validate import path_bounds, validate_job


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
    are kept ahead of the validation issues. Their locations are in the job frame, like the
    fragments, and are moved into the machine frame with them.

    Validation sees the geometry before dedupe (see below). Paths are deduplicated and
    ordered after the transform, so cutting starts from the
    machine origin and each operation continues from where the previous one ended.
    """
    transformed: list[IROperation] = []
    operations: list[IROperation] = []
    here: Point = (0.0, 0.0)
    for frag in sorted(fragments, key=lambda f: (f.order, f.id)):
        settings = merge_settings(preset_settings.get(frag.type, {}), frag.settings)
        op = coords.to_machine_operation(replace(frag, settings=settings), machine)
        transformed.append(op)
        if op.paths:
            op = replace(op, paths=order_paths(dedupe_paths(op.paths), start=here))
            last = op.paths[-1]
            here = last.segments[-1].end if last.segments else last.start
        operations.append(op)

    moved = [
        issue if issue.location is None
        else replace(issue, location=coords.to_machine_point(issue.location, machine))
        for issue in (fragment_issues or [])
    ]
    # Validate the geometry as modelled, before dedupe: two parts sharing an edge are both
    # closed contours, even though the shared edge is then cut only once.
    modelled = IRJob(name=name, machine=machine, material=material, operations=transformed)
    return IRJob(name=name, machine=machine, material=material, operations=operations,
                 bounds=job_bounds(operations), source_document=source_document,
                 issues=moved + validate_job(modelled))


def job_bounds(operations: list[IROperation]) -> IRBounds | None:
    """Bounds of every path and region boundary, arc extremes included; None when empty."""
    boxes = [path_bounds(p) for op in operations for p in op.paths]
    boxes += [path_bounds(b) for op in operations for r in op.regions
              for b in (r.outer, *r.holes)]
    if not boxes:
        return None
    return IRBounds(min(b.min_x for b in boxes), min(b.min_y for b in boxes),
                    max(b.max_x for b in boxes), max(b.max_y for b in boxes))
