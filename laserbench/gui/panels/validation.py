# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation results panel (FR-060). Task W-06."""

from __future__ import annotations

from typing import Any

from laserbench.core.ir import IRIssue


class ValidationPanel:
    """Lists issues; selecting one selects the operation and zooms to its location."""

    def __init__(self, job_obj: Any) -> None:
        raise NotImplementedError("W-06")

    def show_issues(self, issues: list[IRIssue]) -> None:
        raise NotImplementedError("W-06")
