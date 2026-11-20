# SPDX-License-Identifier: LGPL-2.1-or-later
"""Filesystem helpers for exports (FR-075). Task K-07."""

from __future__ import annotations

from pathlib import Path


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> Path:
    """Write via a temporary file in the same folder, then rename over path.

    Readers (e.g. MeerK40t watching the file) never see a half-written file.
    """
    raise NotImplementedError("K-07")


def safe_file_stem(name: str) -> str:
    """A job name made safe as a file name on Windows, macOS and Linux."""
    raise NotImplementedError("K-07")


def job_output_path(out_dir: Path, job_name: str, extension: str) -> Path:
    """Stable per-job export path, e.g. out_dir / "Box lid.svg" (FR-075)."""
    raise NotImplementedError("K-07")
