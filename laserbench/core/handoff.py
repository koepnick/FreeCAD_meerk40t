# SPDX-License-Identifier: LGPL-2.1-or-later
"""Launch the user's laser program with the exported files (FR-074). Task P-03.

Argument lists only, never a shell string (no shell injection). No laser I/O (OS-1).
LaserBench hands the files over and stops there: it never asks the laser program to start
a job, so ``build_argv`` refuses MeerK40t's auto-start options (D-006).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath

PLACEHOLDERS = ("{svg}", "{json}", "{dxf}", "{job_name}")
_PLACEHOLDER_RE = re.compile(r"\{(svg|json|dxf|job_name)\}")

# MeerK40t console words that plan, spool or start a laser job (meerk40t/main.py, -e/-b).
_MEERK40T_JOB_WORDS = re.compile(r"\b(start|spool\w*|plan\w*|burn\w*|execute)\b", re.I)


class HandoffError(RuntimeError):
    """The command could not be built or started. The message is shown to the user."""


def build_argv(template: Sequence[str], files: Mapping[str, Path], job_name: str) -> list[str]:
    """Substitute placeholders in each argument. ``files`` maps "svg"/"json"/"dxf" to paths.

    Placeholders may sit inside a longer argument (``--file={svg}``). Each argument stays
    one argument whatever the substituted text contains. A placeholder whose file was not
    exported raises HandoffError, as does an empty template or a MeerK40t auto-start option.
    """
    if not template or not str(template[0]).strip():
        raise HandoffError("This machine has no send command. Set one in the machine profile, "
                           'e.g. ["meerk40t", "{svg}"].')

    def substitute(arg: str) -> str:
        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            if key == "job_name":
                return job_name
            if key not in files:
                raise HandoffError(f"The send command uses {{{key}}}, but no {key.upper()} "
                                   f"file was exported. Add {key!r} to the job's export "
                                   "formats or remove it from the command.")
            return str(Path(files[key]))
        return _PLACEHOLDER_RE.sub(repl, arg)

    argv = [substitute(str(a)) for a in template]
    _refuse_auto_start([str(a) for a in template])
    return argv


def _is_meerk40t(arg: str) -> bool:
    # PurePath of the platform would not split "C:\..." on Linux; check both separators.
    name = re.split(r"[\\/]", arg)[-1].lower()
    return "meerk40t" in name


def _refuse_auto_start(template: list[str]) -> None:
    """Reject options that would make MeerK40t run the job by itself.

    Only arguments after the MeerK40t program are checked, so wrappers such as
    ``open -a MeerK40t --args {svg}`` (macOS) keep their own options.
    """
    try:
        first = next(i for i, a in enumerate(template) if _is_meerk40t(a))
    except StopIteration:
        return
    args = template[first + 1:]
    refuse = HandoffError("The send command would make MeerK40t start the laser job by "
                          "itself. LaserBench only opens the file; remove the auto-start "
                          "option and start the job in MeerK40t.")
    for i, a in enumerate(args):
        if a in ("--auto", "-a") or (re.fullmatch(r"-[A-Za-z]+", a) and "a" in a[1:]
                                     and not a.startswith("-e")):
            raise refuse
        if a.startswith("--auto="):
            raise refuse
        if a in ("-b", "--batch") or a.startswith("--batch="):
            raise HandoffError("The send command passes MeerK40t a console batch file, which "
                               "could start the laser. LaserBench does not allow -b/--batch.")
        command = None
        if a in ("-e", "--execute") and i + 1 < len(args):
            command = args[i + 1]
        elif a.startswith("--execute="):
            command = a.split("=", 1)[1]
        elif a.startswith("-e") and len(a) > 2:
            command = a[2:]
        if command is not None and _MEERK40T_JOB_WORDS.search(command):
            raise refuse


def launch(argv: Sequence[str], cwd: Path | None = None) -> subprocess.Popen[bytes]:
    """Start the command without waiting for it. Launch failures raise HandoffError.

    The child gets no stdin and its output is discarded, so it can never block FreeCAD.
    On Windows it starts without a console window; elsewhere in its own session so it
    outlives FreeCAD.
    """
    if not argv:
        raise HandoffError("Nothing to launch: the command is empty.")
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": None if cwd is None else os.fspath(cwd),
        "shell": False,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True
    program = PurePath(argv[0]).name or argv[0]
    try:
        return subprocess.Popen(list(argv), **kwargs)  # type: ignore[call-overload]
    except FileNotFoundError as exc:
        raise HandoffError(f"Cannot start {program!r}: program not found. Check the machine "
                           "profile's send command (use the full path if it is not on PATH)."
                           ) from exc
    except PermissionError as exc:
        raise HandoffError(f"Cannot start {program!r}: permission denied.") from exc
    except OSError as exc:
        raise HandoffError(f"Cannot start {program!r}: {exc}") from exc
