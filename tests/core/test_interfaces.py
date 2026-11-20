# SPDX-License-Identifier: LGPL-2.1-or-later
"""C-03: every core interface module imports and documents its public API."""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import laserbench.core

CORE_MODULES = sorted(
    f"laserbench.core.{m.name}" for m in pkgutil.iter_modules(laserbench.core.__path__)
)
EXPECTED = {
    "coords", "dedupe", "export_dxf", "export_json", "export_svg", "fsutil", "handoff",
    "hatch", "ir", "layout", "ordering", "pipeline", "presets", "settings", "validate",
}


def test_all_planned_core_modules_exist() -> None:
    assert {m.rsplit(".", 1)[1] for m in CORE_MODULES} >= EXPECTED


def _public_callables(module: object) -> list[tuple[str, object]]:
    return [
        (name, obj)
        for name, obj in vars(module).items()
        if not name.startswith("_")
        and (inspect.isfunction(obj) or inspect.isclass(obj))
        and getattr(obj, "__module__", None) == module.__name__  # type: ignore[attr-defined]
    ]


@pytest.mark.parametrize("name", CORE_MODULES)
def test_module_imports_and_is_documented(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__doc__, f"{name} needs a module docstring"
    for attr, obj in _public_callables(module):
        assert obj.__doc__, f"{name}.{attr} needs a docstring"


@pytest.mark.parametrize("name", CORE_MODULES)
def test_public_functions_are_fully_annotated(name: str) -> None:
    module = importlib.import_module(name)
    for attr, obj in _public_callables(module):
        if inspect.isfunction(obj):
            hints = obj.__annotations__
            params = inspect.signature(obj).parameters
            missing = [p for p in params if p not in hints]
            assert not missing and "return" in hints, f"{name}.{attr} lacks type hints"
