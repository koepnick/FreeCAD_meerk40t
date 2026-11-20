# SPDX-License-Identifier: LGPL-2.1-or-later
"""LaserOperation FeaturePython object (FR-040, FR-044, FR-045). Task W-02.

Properties: ARCHITECTURE.md §4.1. App side only: no Qt, no FreeCADGui (NFR-006).
"""

from __future__ import annotations

from typing import Any

import FreeCAD

OP_TYPES = ("Cut", "Score", "Fill")


class LaserOperation:
    """Proxy for a ``Part::FeaturePython`` laser operation."""

    Type = "LaserBench::LaserOperation"

    def __init__(self, obj: FreeCAD.DocumentObject) -> None:
        obj.Proxy = self
        self.setup_properties(obj)

    def setup_properties(self, obj: FreeCAD.DocumentObject) -> None:
        """Add any missing properties. Also called on restore, so new versions can add some."""
        raise NotImplementedError("W-02")

    def execute(self, obj: FreeCAD.DocumentObject) -> None:
        """Extract → offset → kerf → to IR; store IRFragment and the preview Shape."""
        raise NotImplementedError("W-02")

    def onDocumentRestored(self, obj: FreeCAD.DocumentObject) -> None:  # noqa: N802
        self.setup_properties(obj)

    def dumps(self) -> dict[str, Any] | None:
        return None

    def loads(self, state: dict[str, Any] | None) -> None:
        return None


def make_operation(
    doc: FreeCAD.Document, op_type: str, sources: list[Any], name: str = "LaserOperation"
) -> FreeCAD.DocumentObject:
    """Create an operation object; ``sources`` is a PropertyLinkSubList value."""
    raise NotImplementedError("W-02")
