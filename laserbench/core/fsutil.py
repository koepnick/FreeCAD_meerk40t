# SPDX-License-Identifier: LGPL-2.1-or-later
"""Filesystem helpers for exports (FR-075). Task K-07."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

# Characters Windows forbids in file names, plus control characters. "/" and "\" too,
# since a job name must never become a sub-folder.
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_STEM = 120  # well under every platform's 255-byte name limit, leaving room for suffixes


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> Path:
    """Write via a temporary file in the same folder, then rename over path.

    Readers (e.g. MeerK40t watching the file) never see a half-written file. The folder
    is created if needed. Newlines are written as given (no platform translation), so the
    output is byte-identical on every OS (NFR-002).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def safe_file_stem(name: str) -> str:
    """A job name made safe as a file name on Windows, macOS and Linux.

    Forbidden characters become ``_``; leading/trailing spaces and dots are dropped
    (Windows strips them silently); reserved device names get a ``_`` suffix; an empty
    result becomes ``"job"``.
    """
    stem = _FORBIDDEN.sub("_", name).strip(" .")
    stem = stem[:_MAX_STEM].rstrip(" .")
    if not stem:
        return "job"
    if stem.split(".", 1)[0].upper() in _RESERVED:
        stem += "_"
    return stem


def job_output_path(out_dir: Path, job_name: str, extension: str) -> Path:
    """Stable per-job export path, e.g. out_dir / "Box lid.svg" (FR-075)."""
    ext = extension.lstrip(".")
    if not ext:
        raise ValueError("extension must not be empty")
    return Path(out_dir) / f"{safe_file_stem(job_name)}.{ext}"
