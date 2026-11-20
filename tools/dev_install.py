"""Link this checkout into FreeCAD's user Mod folder for manual testing.

Not needed if you cloned the repository straight into the Mod folder (the repo
root *is* the addon folder). Otherwise this creates a symlink (a directory
junction on Windows) named ``LaserBench`` in the newest versioned Mod folder it
finds, or in the folder given with ``--mod-dir``.

Usage:
    python tools/dev_install.py [--mod-dir PATH] [--name NAME] [--remove]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def freecad_user_dirs() -> list[Path]:
    """Candidate FreeCAD user data directories for this platform, newest layout first."""
    home = Path.home()
    if sys.platform == "darwin":
        bases = [home / "Library" / "Application Support" / "FreeCAD"]
    elif sys.platform == "win32":
        bases = [Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "FreeCAD"]
    else:
        xdg = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        bases = [xdg / "FreeCAD", home / ".FreeCAD"]
    return bases


def _version_key(path: Path) -> tuple[int, ...]:
    # "v1-1" -> (1, 1); anything unparsable sorts first.
    try:
        return tuple(int(p) for p in path.name.lstrip("v").split("-"))
    except ValueError:
        return ()


def find_mod_dir() -> Path:
    """Return the Mod folder of the newest FreeCAD user data dir (FreeCAD >= 1.0 uses vX-Y)."""
    for base in freecad_user_dirs():
        if not base.is_dir():
            continue
        versioned = sorted(
            (p for p in base.iterdir() if p.is_dir() and p.name.startswith("v")),
            key=_version_key,
        )
        if versioned:
            return versioned[-1] / "Mod"
        return base / "Mod"
    raise SystemExit("Could not find a FreeCAD user data folder. Pass --mod-dir explicitly.")


def _is_junction(path: Path) -> bool:
    # Path.is_junction() only exists on Python >= 3.12.
    return bool(getattr(path, "is_junction", lambda: False)())


def link(target: Path, link_path: Path) -> None:
    if sys.platform == "win32":
        # Junctions need no admin rights, unlike symlinks.
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link_path), str(target)], check=True)
    else:
        link_path.symlink_to(target, target_is_directory=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mod-dir", type=Path, help="FreeCAD Mod folder to install into")
    parser.add_argument("--name", default="LaserBench", help="folder name inside Mod")
    parser.add_argument("--remove", action="store_true", help="remove the link instead")
    args = parser.parse_args(argv)

    mod_dir = args.mod_dir or find_mod_dir()
    if REPO_ROOT.parent.resolve() == mod_dir.resolve():
        print(f"This checkout is already inside {mod_dir}; nothing to do.")
        return 0

    link_path = mod_dir / args.name
    if args.remove:
        if link_path.is_symlink() or _is_junction(link_path):
            link_path.unlink()
            print(f"Removed {link_path}")
        else:
            print(f"{link_path} is not a link; leaving it alone.")
        return 0

    mod_dir.mkdir(parents=True, exist_ok=True)
    if link_path.exists() or link_path.is_symlink():
        print(f"{link_path} already exists; remove it first (--remove).")
        return 1
    link(REPO_ROOT, link_path)
    print(f"Linked {link_path} -> {REPO_ROOT}. Restart FreeCAD to load the workbench.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
