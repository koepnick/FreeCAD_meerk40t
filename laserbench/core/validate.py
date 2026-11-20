# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation rules producing IRIssues (FR-060 to FR-064, FR-066). Task K-05.

Issue codes and severities are fixed by IR_SCHEMA.md §3.9 / ir.ISSUE_CODES.
BROKEN_SOURCE, KERF_COLLAPSE and GEOMETRY_ERROR come from the fc pipeline, not from here.
"""

from __future__ import annotations

from laserbench.core.ir import IRIssue, IRJob, IROperation


def check_bounds(job: IRJob) -> list[IRIssue]:
    """OUT_OF_BOUNDS for geometry outside the machine work area or galvo field (FR-061)."""
    raise NotImplementedError("K-05")


def check_open_contours(op: IROperation) -> list[IRIssue]:
    """OPEN_CONTOUR for each open path in a cut operation, located at its start (FR-062)."""
    raise NotImplementedError("K-05")


def check_fill_regions(op: IROperation) -> list[IRIssue]:
    """FILL_NO_REGION for a fill operation without closed regions (FR-063)."""
    raise NotImplementedError("K-05")


def check_smaller_than_kerf(op: IROperation, kerf: float) -> list[IRIssue]:
    """SMALLER_THAN_KERF for slots narrower than kerf or holes under 2 × kerf (FR-064)."""
    raise NotImplementedError("K-05")


def check_self_intersection(op: IROperation) -> list[IRIssue]:
    """SELF_INTERSECTION for each self-intersecting closed path (FR-066)."""
    raise NotImplementedError("K-05")


def check_empty(op: IROperation) -> list[IRIssue]:
    """EMPTY_OPERATION when an enabled operation produced no geometry."""
    raise NotImplementedError("K-05")


def validate_job(job: IRJob) -> list[IRIssue]:
    """Run every rule above. Order: job-level rules, then each operation in IR order."""
    raise NotImplementedError("K-05")
