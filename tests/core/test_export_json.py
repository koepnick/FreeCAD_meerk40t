# SPDX-License-Identifier: LGPL-2.1-or-later
"""K-07: IR JSON export (FR-070), atomic writes and stable paths (FR-075)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from laserbench.core import fsutil
from laserbench.core.export_json import export_json, load_json
from laserbench.core.fsutil import atomic_write_text, job_output_path, safe_file_stem
from laserbench.core.ir import (
    IRError,
    IRIssue,
    IRJob,
    IRMachine,
    IRMaterial,
    IROperation,
    IRPath,
    IRSegment,
    IRVersionError,
)


def _job() -> IRJob:
    path = IRPath(start=(0, 0), segments=[IRSegment.line((10, 0)), IRSegment.line((10, 10)),
                                          IRSegment.arc((0, 0), (5, 5), True)], closed=True)
    op = IROperation(id="Cut", label="Outline µ", type="cut", order=0, colour="#FF0000",
                     settings={"power": 65, "speed": 20.0}, kerf_mode="auto", paths=[path])
    return IRJob(name="Box lid", source_document="lid.FCStd",
                 machine=IRMachine("co2", "CO2", "gantry", 600, 400, "rear-left"),
                 material=IRMaterial("ply3", "Ply", 3, 0.2), operations=[op],
                 issues=[IRIssue("OPEN_CONTOUR", "open", "Cut", (1, 2))])


def test_export_round_trip(tmp_path: Path) -> None:
    """FR-070: the exported file loads back to an equal job, byte-identical on re-export."""
    job = _job()
    out = export_json(job, tmp_path / "out" / "lid.json")
    assert out == tmp_path / "out" / "lid.json"
    assert out.read_bytes() == job.to_json().encode("utf-8")
    loaded = load_json(out)
    assert loaded == job
    again = export_json(loaded, tmp_path / "again.json")
    assert again.read_bytes() == out.read_bytes()  # NFR-002


def test_load_rejects_bad_files(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(IRError):
        load_json(bad)
    bad.write_bytes(b"\xff\xfe")
    with pytest.raises(IRError, match="UTF-8"):
        load_json(bad)
    newer = _job().to_dict() | {"schema_version": 99}
    bad.write_text(__import__("json").dumps(newer), encoding="utf-8")
    with pytest.raises(IRVersionError):
        load_json(bad)


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path: Path) -> None:
    """FR-075: re-export overwrites in place; no temp files are left behind."""
    target = tmp_path / "job.svg"
    atomic_write_text(target, "one\n")
    atomic_write_text(target, "two\r\nlines\n")
    assert target.read_bytes() == b"two\r\nlines\n"  # newlines written verbatim
    assert [p.name for p in tmp_path.iterdir()] == ["job.svg"]


def test_atomic_write_failure_keeps_old_file(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "job.json"
    atomic_write_text(target, "old")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(fsutil.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        atomic_write_text(target, "new")
    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["job.json"]


@pytest.mark.parametrize(("name", "stem"), [
    ("Box lid", "Box lid"),
    ("a/b\\c:d*e?f\"g<h>i|j", "a_b_c_d_e_f_g_h_i_j"),
    ("  .hidden. ", "hidden"),
    ("", "job"),
    ("...", "job"),
    ("CON", "CON_"),
    ("com1.part", "com1.part_"),
    ("tab\there", "tab_here"),
    ("Kühlbox", "Kühlbox"),
])
def test_safe_file_stem(name: str, stem: str) -> None:
    assert safe_file_stem(name) == stem


def test_safe_file_stem_is_bounded() -> None:
    assert len(safe_file_stem("x" * 1000)) == 120


def test_job_output_path(tmp_path: Path) -> None:
    assert job_output_path(tmp_path, "Box lid", "svg") == tmp_path / "Box lid.svg"
    assert job_output_path(tmp_path, "a/b", ".json") == tmp_path / "a_b.json"
    with pytest.raises(ValueError):
        job_output_path(tmp_path, "x", "")


def test_presets_use_the_atomic_writer(tmp_path: Path) -> None:
    """presets.py now writes through fsutil (no stray temp files)."""
    from laserbench.core import presets
    presets._write(tmp_path / "machines.json", "machines", [])
    assert os.listdir(tmp_path) == ["machines.json"]
