# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the 3D-view preview from IR (FR-034). Task G-05."""

from __future__ import annotations

import FreeCAD
import Part

from laserbench.core.ir import IROperation


def operation_shape(op: IROperation, job_plane: FreeCAD.Placement) -> Part.Shape:
    """Edges of one job-frame operation, placed on the job plane."""
    raise NotImplementedError("G-05")


def build_preview(operations: list[IROperation], job_plane: FreeCAD.Placement) -> Part.Compound:
    """Compound of all operations' edges. Its bounding box matches the IR bounds."""
    raise NotImplementedError("G-05")
