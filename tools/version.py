# SPDX-License-Identifier: LGPL-2.1-or-later
"""Check or bump the LaserBench version.

``package.xml`` is the source of truth: it is what FreeCAD's Addon Manager reads and shows.
The same version is repeated in ``laserbench/__init__.py`` (``__version__``, so code and
exported files can report it without parsing XML at runtime) and ``pyproject.toml`` (tooling).
``CHANGELOG.md`` must have a section for it. This script keeps them in step.

    python tools/version.py check                 # all copies agree, changelog has a section
    python tools/version.py check --tag v0.2.0    # ...and the git tag matches (release CI)
    python tools/version.py bump 0.2.0            # set the version and today's date everywhere,
                                                  # and turn "Unreleased" into a 0.2.0 section

Plain Python 3.11 standard library; run from anywhere.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_XML = REPO_ROOT / "package.xml"
INIT_PY = REPO_ROOT / "laserbench" / "__init__.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# MAJOR.MINOR.PATCH, no leading zeros, no pre-release suffix. The Addon Manager compares
# versions as dotted numbers, so a suffix like "-beta" would not sort the way people expect.
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Only the first <version>/<date> in package.xml: the package's own, not a content item's.
_XML_VERSION = re.compile(r"(<version>)([^<]*)(</version>)")
_XML_DATE = re.compile(r"(<date>)([^<]*)(</date>)")
_INIT_VERSION = re.compile(r'^(__version__ = ")([^"]*)(")', re.M)
_PYPROJECT_VERSION = re.compile(r'^(version = ")([^"]*)(")', re.M)
_UNRELEASED = re.compile(r"^## \[Unreleased\][^\n]*\n", re.M)


def _find(pattern: re.Pattern[str], path: Path) -> str:
    match = pattern.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"{path.relative_to(REPO_ROOT)}: no match for {pattern.pattern!r}")
    return match.group(2).strip()


def read_versions() -> dict[str, str]:
    """The version string from each file that carries one, keyed by file name."""
    return {
        "package.xml": _find(_XML_VERSION, PACKAGE_XML),
        "laserbench/__init__.py": _find(_INIT_VERSION, INIT_PY),
        "pyproject.toml": _find(_PYPROJECT_VERSION, PYPROJECT),
    }


def read_date() -> str:
    return _find(_XML_DATE, PACKAGE_XML)


def changelog_has(version: str) -> bool:
    text = CHANGELOG.read_text(encoding="utf-8")
    return re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$",
                     text, re.M) is not None


def problems(tag: str | None = None) -> list[str]:
    """Everything wrong with the version metadata; empty when it is consistent."""
    found: list[str] = []
    versions = read_versions()
    version = versions["package.xml"]
    if not SEMVER.fullmatch(version):
        found.append(f"package.xml version {version!r} is not MAJOR.MINOR.PATCH")
    for name, value in versions.items():
        if value != version:
            found.append(f"{name} has version {value!r} but package.xml has {version!r}")
    date = read_date()
    if not DATE.fullmatch(date):
        found.append(f"package.xml date {date!r} is not YYYY-MM-DD")
    if not changelog_has(version):
        found.append(f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' section")
    if tag is not None and tag != f"v{version}":
        found.append(f"git tag {tag!r} does not match package.xml version (expected v{version})")
    return found


def _sub_once(pattern: re.Pattern[str], path: Path, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, count = pattern.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if count != 1:
        raise ValueError(f"{path.relative_to(REPO_ROOT)}: no match for {pattern.pattern!r}")
    path.write_text(new, encoding="utf-8")


def bump(version: str, date: str) -> None:
    """Write ``version`` and ``date`` everywhere and open a changelog section for them."""
    if not SEMVER.fullmatch(version):
        raise ValueError(f"{version!r} is not MAJOR.MINOR.PATCH (for example 0.2.0)")
    if not DATE.fullmatch(date):
        raise ValueError(f"{date!r} is not YYYY-MM-DD")
    if changelog_has(version):
        raise ValueError(f"CHANGELOG.md already has a section for {version}")
    text = CHANGELOG.read_text(encoding="utf-8")
    if not _UNRELEASED.search(text):
        raise ValueError("CHANGELOG.md has no '## [Unreleased]' heading to release")
    # Keep an empty Unreleased section on top for the next round of changes.
    text = _UNRELEASED.sub(f"## [Unreleased]\n\n## [{version}] - {date}\n", text, count=1)
    CHANGELOG.write_text(text, encoding="utf-8")
    _sub_once(_XML_VERSION, PACKAGE_XML, version)
    _sub_once(_XML_DATE, PACKAGE_XML, date)
    _sub_once(_INIT_VERSION, INIT_PY, version)
    _sub_once(_PYPROJECT_VERSION, PYPROJECT, version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="verify all version copies agree")
    check.add_argument("--tag", help="git tag being released, e.g. v0.2.0")
    bump_p = sub.add_parser("bump", help="set a new version everywhere")
    bump_p.add_argument("version", help="new version, e.g. 0.2.0")
    bump_p.add_argument("--date", default=datetime.date.today().isoformat(),
                        help="release date, YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)

    if args.command == "bump":
        try:
            bump(args.version, args.date)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Version set to {args.version} ({args.date}). Now edit CHANGELOG.md, then run "
              "'python tools/version.py check'.")
        return 0

    found = problems(args.tag)
    if found:
        print("Version check failed:", *(f"  - {p}" for p in found), sep="\n", file=sys.stderr)
        return 1
    print(f"OK: version {read_versions()['package.xml']} ({read_date()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
