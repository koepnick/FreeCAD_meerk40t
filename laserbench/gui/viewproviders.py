# SPDX-License-Identifier: LGPL-2.1-or-later
"""View providers for LaserJob and LaserOperation (FR-034). Task W-05.

The job draws its preview with each operation's edges in that operation's colour, plus a
dashed outline of the machine's bed or galvo field on the job plane. Operations nest under
their job in the tree (FR-032), draw in their own colour, and turn grey when disabled.

FreeCADGui and Coin are imported lazily so this module imports under freecadcmd; FreeCAD
restores these proxies by module and class name when a document is opened.
"""

from __future__ import annotations

import os
from typing import Any

#: Colour of disabled operations and of the bed outline.
GREY = (0.6, 0.6, 0.6)
LINE_WIDTH = 2.0


def _icon() -> str:
    import laserbench

    return os.path.join(os.path.dirname(laserbench.__file__), "resources", "icons",
                        "laserbench.svg")


def rgb(colour: tuple[float, ...]) -> tuple[float, float, float]:
    """A PropertyColor value as an (r, g, b) tuple, dropping alpha."""
    r, g, b = (float(c) for c in tuple(colour)[:3])
    return (r, g, b)


def edge_colours(shape: Any, colours: list[tuple[float, float, float]]
                 ) -> list[tuple[float, float, float]] | None:
    """Per-edge colours for a compound whose sub-shapes are the operations, in order.

    Returns None when the shape does not line up with the operations (e.g. mid-recompute),
    so the caller can fall back to one colour.
    """
    if shape is None or shape.isNull():
        return None
    subs = shape.SubShapes
    if len(subs) != len(colours):
        return None
    out: list[tuple[float, float, float]] = []
    for sub, colour in zip(subs, colours, strict=True):
        out.extend([colour] * len(sub.Edges))
    return out if len(out) == len(shape.Edges) else None


def work_area_corners(kind: str, width: float, height: float) -> list[tuple[float, float]]:
    """The bed or field outline in the job frame (core/coords.py), as a closed loop."""
    if kind == "galvo":
        x0, y0 = -width / 2, -height / 2
    else:
        x0, y0 = 0.0, 0.0
    x1, y1 = x0 + width, y0 + height
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


class ViewProviderLaserJob:
    """Coloured preview, bed outline and the operations as tree children."""

    def __init__(self, vobj: Any) -> None:
        vobj.Proxy = self

    def attach(self, vobj: Any) -> None:
        """Add the bed outline node to the job's scene graph."""
        from pivy import coin

        self.Object = vobj.Object
        self.outline_coords = coin.SoCoordinate3()
        self.outline = coin.SoSeparator()
        self.outline_transform = coin.SoTransform()
        colour = coin.SoBaseColor()
        colour.rgb.setValue(*GREY)
        style = coin.SoDrawStyle()
        style.lineWidth = 1
        style.linePattern = 0x0F0F  # dashed: it is a reference, not geometry to cut
        lines = coin.SoLineSet()
        for node in (self.outline_transform, colour, style, self.outline_coords, lines):
            self.outline.addChild(node)
        # The root node sits outside the display-mode switch that Visibility drives, so the
        # outline gets its own switch.
        self.outline_switch = coin.SoSwitch()
        self.outline_switch.addChild(self.outline)
        self.outline_switch.whichChild = 0 if vobj.Visibility else -1
        vobj.RootNode.addChild(self.outline_switch)
        self.update_outline(vobj.Object)

    def getIcon(self) -> str:  # noqa: N802
        return _icon()

    def claimChildren(self) -> list[Any]:  # noqa: N802
        """Show operations nested under the job in the tree (FR-032)."""
        return list(getattr(self.Object, "Operations", []) or [])

    def updateData(self, obj: Any, prop: str) -> None:  # noqa: N802
        if prop == "Shape":
            self.colour_edges(obj)
        elif prop in ("MachineProfile", "JobPlane"):
            self.update_outline(obj)

    def onChanged(self, vobj: Any, prop: str) -> None:  # noqa: N802
        if prop == "Visibility" and hasattr(self, "outline_switch"):
            self.outline_switch.whichChild = 0 if vobj.Visibility else -1

    def colour_edges(self, obj: Any) -> None:
        """Give each operation's edges its colour (FR-034)."""
        from laserbench.objects.job import enabled_operations

        vobj = obj.ViewObject
        if vobj is None:
            return
        vobj.LineWidth = LINE_WIDTH
        colours = [rgb(op.Colour) for op in enabled_operations(obj)]
        per_edge = edge_colours(obj.Shape, colours)
        if per_edge:
            vobj.LineColorArray = per_edge
        elif colours:
            vobj.LineColor = colours[0]

    def update_outline(self, obj: Any) -> None:
        """Redraw the dashed bed/field outline for the job's machine and plane."""
        if not hasattr(self, "outline_coords"):
            return
        from laserbench.objects.job import resolve_presets

        corners: list[tuple[float, float]] = []
        try:
            machine, _ = resolve_presets(obj.MachineProfile, obj.MaterialPreset)
        except (KeyError, ValueError, OSError):
            pass  # the job reports the bad id itself; just draw no outline
        else:
            corners = work_area_corners(machine.kind, machine.width, machine.height)
        self.outline_coords.point.setNum(0)
        self.outline_coords.point.setValues(0, len(corners), [(x, y, 0.0) for x, y in corners])
        plane = obj.JobPlane
        self.outline_transform.translation.setValue(tuple(plane.Base))
        self.outline_transform.rotation.setValue(tuple(plane.Rotation.Q))

    def outline_points(self) -> list[tuple[float, float, float]]:
        """The outline's corner points in the job plane's local frame (for tests)."""
        if not hasattr(self, "outline_coords"):
            return []
        return [tuple(p) for p in self.outline_coords.point.getValues()]

    def dumps(self) -> None:
        return None

    def loads(self, state: Any) -> None:
        return None


class ViewProviderLaserOperation:
    """The operation's own geometry in its colour; grey when disabled."""

    def __init__(self, vobj: Any) -> None:
        vobj.Proxy = self

    def attach(self, vobj: Any) -> None:
        self.Object = vobj.Object

    def getIcon(self) -> str:  # noqa: N802
        return _icon()

    def updateData(self, obj: Any, prop: str) -> None:  # noqa: N802
        """Recolour the preview when Colour changes."""
        if prop in ("Colour", "Enabled", "Shape"):
            self.recolour(obj)

    def recolour(self, obj: Any) -> None:
        """Apply the operation's colour, or grey if it is disabled (FR-045)."""
        vobj = obj.ViewObject
        if vobj is None or not hasattr(obj, "Colour"):
            return
        vobj.LineWidth = LINE_WIDTH
        vobj.LineColor = rgb(obj.Colour) if getattr(obj, "Enabled", True) else GREY

    def dumps(self) -> None:
        return None

    def loads(self, state: Any) -> None:
        return None


def attach_view_provider(obj: Any) -> None:
    """Give a LaserJob or LaserOperation its view provider (GUI only; no-op headless)."""
    import FreeCAD

    if not FreeCAD.GuiUp or getattr(obj, "ViewObject", None) is None:
        return
    kind = getattr(getattr(obj, "Proxy", None), "Type", None)
    if kind == "LaserBench::LaserJob":
        ViewProviderLaserJob(obj.ViewObject)
        obj.ViewObject.Proxy.colour_edges(obj)
    elif kind == "LaserBench::LaserOperation":
        ViewProviderLaserOperation(obj.ViewObject)
        obj.ViewObject.Proxy.recolour(obj)
