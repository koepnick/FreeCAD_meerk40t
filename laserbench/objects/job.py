# SPDX-License-Identifier: LGPL-2.1-or-later
"""LaserJob FeaturePython object (FR-030 to FR-033). Task W-03.

Properties: ARCHITECTURE.md §4.1. App side only: no Qt, no FreeCADGui (NFR-006).
"""

from __future__ import annotations

from typing import Any

import FreeCAD

from laserbench.core.ir import IRJob


class LaserJob:
    """Proxy for a ``Part::FeaturePython`` laser job."""

    Type = "LaserBench::LaserJob"

    def __init__(self, obj: FreeCAD.DocumentObject) -> None:
        obj.Proxy = self
        self.setup_properties(obj)

    def setup_properties(self, obj: FreeCAD.DocumentObject) -> None:
        """Add any missing properties. Also called on restore."""
        raise NotImplementedError("W-03")

    def execute(self, obj: FreeCAD.DocumentObject) -> None:
        """Collect operation fragments and run core.pipeline.assemble_job (ARCHITECTURE §3).

        Stores IRCache, ValidationSummary and the preview Shape. User-correctable problems
        become issues; only hard failures raise (D-009).
        """
        raise NotImplementedError("W-03")

    def onDocumentRestored(self, obj: FreeCAD.DocumentObject) -> None:  # noqa: N802
        self.setup_properties(obj)

    def dumps(self) -> dict[str, Any] | None:
        return None

    def loads(self, state: dict[str, Any] | None) -> None:
        return None


def make_job(doc: FreeCAD.Document, machine: str, material: str, name: str = "LaserJob"
             ) -> FreeCAD.DocumentObject:
    """Create a LaserJob for a machine profile id and material preset id (FR-030)."""
    raise NotImplementedError("W-03")


def get_ir(job_obj: FreeCAD.DocumentObject) -> IRJob:
    """The job's last computed IR (recomputing first if the cache is empty)."""
    raise NotImplementedError("W-03")
