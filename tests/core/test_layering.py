"""NFR-001: laserbench.core is pure standard-library Python.

Two checks: a static scan of every import in core/, and a real import of every
core module in a fresh interpreter where FreeCAD-ish modules are blocked.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "laserbench" / "core"
FORBIDDEN = {
    "FreeCAD", "FreeCADGui", "Part", "Draft", "Sketcher", "TechDraw", "Mesh", "PartDesign",
    "PySide", "PySide2", "PySide6", "PyQt5", "PyQt6", "shiboken2", "shiboken6",
}


def _core_modules() -> list[Path]:
    return sorted(CORE_DIR.rglob("*.py"))


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_core_has_modules() -> None:
    assert _core_modules(), "laserbench/core should contain modules"


def test_core_imports_only_stdlib_and_itself() -> None:
    allowed = set(sys.stdlib_module_names) | {"laserbench", "__future__"}
    offenders = {}
    for path in _core_modules():
        bad = _top_level_imports(path) - allowed
        if bad:
            offenders[str(path.relative_to(REPO_ROOT))] = sorted(bad)
    assert not offenders, f"non-stdlib imports in core: {offenders}"


def test_core_imports_with_freecad_blocked() -> None:
    modules = [
        ".".join(p.relative_to(REPO_ROOT).with_suffix("").parts).removesuffix(".__init__")
        for p in _core_modules()
    ]
    script = f"""
import sys
BLOCKED = {sorted(FORBIDDEN)!r}

class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in BLOCKED:
            raise ImportError('blocked by layering test: ' + name)
        return None

sys.meta_path.insert(0, _Blocker())
sys.path.insert(0, {str(REPO_ROOT)!r})
import importlib
for m in {modules!r}:
    importlib.import_module(m)
leaked = sorted(set(BLOCKED) & set(sys.modules))
assert not leaked, leaked
print('ok')
"""
    # -I: isolated mode, so nothing from the user's site-packages or cwd leaks in.
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
