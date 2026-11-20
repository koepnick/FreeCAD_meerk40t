# SPDX-License-Identifier: LGPL-2.1-or-later
"""P-03: send-command handoff (FR-074). Uses a fake executable, never a laser program."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from laserbench.core.handoff import PLACEHOLDERS, HandoffError, build_argv, launch

FAKE = """
import json, sys, time
from pathlib import Path
time.sleep(float(sys.argv[2]))
Path(sys.argv[1]).write_text(json.dumps(sys.argv[3:]), encoding="utf-8")
"""


def test_placeholders_substituted_per_argument(tmp_path: Path) -> None:
    files = {"svg": tmp_path / "Box lid.svg", "json": tmp_path / "Box lid.json"}
    argv = build_argv(["meerk40t", "{svg}", "--name={job_name}", "{json}"], files, "Box lid")
    assert argv == ["meerk40t", str(files["svg"]), "--name=Box lid", str(files["json"])]
    assert PLACEHOLDERS == ("{svg}", "{json}", "{dxf}", "{job_name}")


def test_hostile_job_name_stays_one_argument(tmp_path: Path) -> None:
    """No shell: quotes, semicolons and spaces in a name are just characters."""
    name = 'x"; rm -rf ~; echo "'
    argv = build_argv(["prog", "{job_name}", "{unknown}"], {}, name)
    assert argv == ["prog", name, "{unknown}"]


def test_missing_file_and_empty_template() -> None:
    with pytest.raises(HandoffError, match="DXF"):
        build_argv(["prog", "{dxf}"], {"svg": Path("a.svg")}, "j")
    with pytest.raises(HandoffError, match="no send command"):
        build_argv([], {}, "j")
    with pytest.raises(HandoffError, match="no send command"):
        build_argv(["  "], {}, "j")


@pytest.mark.parametrize("template", [
    ["meerk40t", "-a", "{svg}"],
    ["meerk40t", "--auto", "{svg}"],
    ["meerk40t", "--auto=1", "{svg}"],
    ["/opt/MeerK40t/meerk40t", "-za", "{svg}"],
    ["python", "C:\\tools\\meerk40t.py", "{svg}", "-qa"],
    ["MeerK40t.exe", "-e", "start", "{svg}"],
    ["meerk40t", "--execute=plan copy preprocess validate blob spool", "{svg}"],
    ["meerk40t", "-ePlan0 spool", "{svg}"],
    ["meerk40t", "-b", "jobs.txt", "{svg}"],
    ["meerk40t", "--batch=jobs.txt", "{svg}"],
])
def test_meerk40t_auto_start_is_refused(template: list[str]) -> None:
    """LaserBench never makes MeerK40t start the laser by itself."""
    with pytest.raises(HandoffError):
        build_argv(template, {"svg": Path("j.svg")}, "j")


@pytest.mark.parametrize("template", [
    ["meerk40t", "{svg}"],
    ["open", "-a", "MeerK40t", "--args", "{svg}"],          # macOS: -a belongs to open
    ["meerk40t", "-e", "device activate 1", "{svg}"],       # choose the galvo device
    ["inkscape", "-a", "{svg}"],                            # not MeerK40t: not our business
])
def test_harmless_commands_allowed(template: list[str]) -> None:
    assert build_argv(template, {"svg": Path("j.svg")}, "j")[-1] == "j.svg"


def test_launch_is_non_blocking_and_passes_args(tmp_path: Path) -> None:
    script = tmp_path / "fake laser.py"
    script.write_text(FAKE, encoding="utf-8")
    out = tmp_path / "argv.json"
    argv = build_argv([sys.executable, str(script), str(out), "1.0", "{svg}", "a b;c"],
                      {"svg": tmp_path / "x y.svg"}, "j")
    t0 = time.monotonic()
    proc = launch(argv, cwd=tmp_path)
    assert time.monotonic() - t0 < 0.9  # returned before the child finished sleeping
    assert proc.poll() is None
    assert proc.wait(timeout=30) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == [str(tmp_path / "x y.svg"), "a b;c"]


def test_launch_errors_are_handoff_errors(tmp_path: Path) -> None:
    with pytest.raises(HandoffError, match="not found"):
        launch([str(tmp_path / "no-such-program")])
    with pytest.raises(HandoffError, match="empty"):
        launch([])
    if sys.platform != "win32":
        plain = tmp_path / "not-executable"
        plain.write_text("x", encoding="utf-8")
        with pytest.raises(HandoffError, match="permission denied"):
            launch([str(plain)])
