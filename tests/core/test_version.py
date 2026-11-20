# SPDX-License-Identifier: LGPL-2.1-or-later
"""Release metadata: package.xml, laserbench.__version__, pyproject.toml and CHANGELOG.md agree.

package.xml is what FreeCAD's Addon Manager reads, so it is the source of truth. This test is
how CI catches a version bumped in one place but not the others (see docs/RELEASING.md).
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

import laserbench

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_tool():
    spec = importlib.util.spec_from_file_location("lb_version_tool",
                                                  REPO_ROOT / "tools" / "version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


version_tool = _load_tool()


def test_repository_version_metadata_is_consistent():
    assert version_tool.problems() == []


def test_package_version_matches_package_xml():
    assert laserbench.__version__ == version_tool.read_versions()["package.xml"]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A copy of the four version files, with the tool pointed at the copies."""
    (tmp_path / "laserbench").mkdir()
    for attr, rel in [("PACKAGE_XML", "package.xml"), ("INIT_PY", "laserbench/__init__.py"),
                      ("PYPROJECT", "pyproject.toml"), ("CHANGELOG", "CHANGELOG.md")]:
        shutil.copy(REPO_ROOT / rel, tmp_path / rel)
        monkeypatch.setattr(version_tool, attr, tmp_path / rel)
    monkeypatch.setattr(version_tool, "REPO_ROOT", tmp_path)
    return tmp_path


def test_mismatch_is_reported(sandbox):
    init = sandbox / "laserbench" / "__init__.py"
    init.write_text(init.read_text().replace(laserbench.__version__, "9.9.9"))
    assert any("laserbench/__init__.py" in p for p in version_tool.problems())


def test_tag_must_match(sandbox):
    current = laserbench.__version__
    assert version_tool.problems(tag=f"v{current}") == []
    assert any("git tag" in p for p in version_tool.problems(tag="v99.0.0"))


@pytest.mark.parametrize("bad", ["1.0", "1.0.0-beta", "01.2.3", "v1.2.3"])
def test_bump_rejects_non_semver(sandbox, bad):
    with pytest.raises(ValueError):
        version_tool.bump(bad, "2030-01-01")


def test_bump_updates_every_copy(sandbox):
    version_tool.bump("99.1.0", "2030-01-02")
    assert set(version_tool.read_versions().values()) == {"99.1.0"}
    assert version_tool.read_date() == "2030-01-02"
    changelog = (sandbox / "CHANGELOG.md").read_text()
    assert "## [Unreleased]\n\n## [99.1.0] - 2030-01-02\n" in changelog
    assert version_tool.problems() == []
    with pytest.raises(ValueError):
        version_tool.bump("99.1.0", "2030-01-03")
