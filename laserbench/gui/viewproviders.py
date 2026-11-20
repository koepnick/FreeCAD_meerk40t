# SPDX-License-Identifier: LGPL-2.1-or-later
"""View providers for LaserJob and LaserOperation (FR-034). Task W-05."""

from __future__ import annotations

from typing import Any


class ViewProviderLaserJob:
    def __init__(self, vobj: Any) -> None:
        vobj.Proxy = self

    def getIcon(self) -> str:  # noqa: N802
        raise NotImplementedError("W-05")

    def claimChildren(self) -> list[Any]:  # noqa: N802
        """Show operations nested under the job in the tree (FR-032)."""
        raise NotImplementedError("W-05")

    def dumps(self) -> None:
        return None

    def loads(self, state: Any) -> None:
        return None


class ViewProviderLaserOperation:
    def __init__(self, vobj: Any) -> None:
        vobj.Proxy = self

    def getIcon(self) -> str:  # noqa: N802
        raise NotImplementedError("W-05")

    def updateData(self, obj: Any, prop: str) -> None:  # noqa: N802
        """Recolour the preview when Colour changes."""
        raise NotImplementedError("W-05")

    def dumps(self) -> None:
        return None

    def loads(self, state: Any) -> None:
        return None
