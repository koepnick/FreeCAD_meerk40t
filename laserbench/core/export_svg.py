# SPDX-License-Identifier: LGPL-2.1-or-later
"""Colour-coded SVG export (FR-071, FR-072). Task K-06.

Layout and metadata are fixed by IR_SCHEMA.md §5. The optional MeerK40t operation
groups (§5.1) follow D-006: MeerK40t's own SVG loader turns a ``<g type="op cut" ...>``
with a ``references`` list into an operation holding exactly those elements, with the
given power/speed/passes, instead of guessing from stroke colours.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import quoteattr

from laserbench.core.fsutil import atomic_write_text
from laserbench.core.ir import (
    PRECISION,
    SCHEMA_VERSION,
    IRJob,
    IRMachine,
    IROperation,
    IRPath,
    Point,
)

LB_NAMESPACE = "https://github.com/koepnick/FreeCAD_meerk40t/ns/ir/1"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
INKSCAPE_NAMESPACE = "http://www.inkscape.org/namespaces/inkscape"
HAIRLINE = 0.025  # mm

#: IR operation type → MeerK40t operation node type (D-006).
MEERK40T_OP_TYPES = {"cut": "op cut", "score": "op engrave", "fill": "op raster"}

_SvgMap = Callable[[Point], Point]


def meerk40t_op_type(op: IROperation) -> str:
    """The MeerK40t operation type for an IR operation; hatched fills are vector engraves."""
    return "op engrave" if op.hatched else MEERK40T_OP_TYPES[op.type]


def fmt(value: float) -> str:
    """A number with at most 4 decimals, trailing zeros stripped, never ``-0``."""
    text = f"{round(value, PRECISION):.{PRECISION}f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def svg_transform(machine: IRMachine) -> tuple[_SvgMap, bool]:
    """Machine frame → SVG user units (y down, rear edge at the top).

    Returns the point map and whether it is a reflection, which flips arc sweep.
    """
    w, h = machine.width, machine.height
    if machine.kind == "galvo":
        return (lambda p: (p[0] + w / 2, h / 2 - p[1])), True
    flip_x = machine.origin.endswith("right")  # machine +x runs right-to-left
    flip_y = machine.origin.startswith("front")  # machine +y runs up the screen
    def point(p: Point) -> Point:
        return (w - p[0] if flip_x else p[0], h - p[1] if flip_y else p[1])
    return point, flip_x != flip_y


def path_data(path: IRPath, to_svg: _SvgMap, mirrored: bool) -> str:
    """SVG ``d`` for one IR path. Arcs become ``A`` commands; full circles two halves."""
    def pt(p: Point) -> str:
        x, y = to_svg(p)
        return f"{fmt(x)} {fmt(y)}"

    out = [f"M {pt(path.start)}"]
    for start, seg in path.iter_segments():
        if seg.kind == "line":
            out.append(f"L {pt(seg.end)}")
        elif seg.kind == "poly":
            assert seg.points is not None
            out.extend(f"L {pt(p)}" for p in [*seg.points, seg.end])
        else:
            assert seg.center is not None and seg.ccw is not None
            cx, cy = seg.center
            r = math.hypot(start[0] - cx, start[1] - cy)
            # sweep-flag 1 is the positive-angle direction of the SVG coordinates, which is
            # ccw in the machine frame unless the machine→SVG map is a reflection.
            sweep = int(seg.ccw != mirrored)
            a0 = math.atan2(start[1] - cy, start[0] - cx)
            a1 = math.atan2(seg.end[1] - cy, seg.end[0] - cx)
            delta = ((a1 - a0) if seg.ccw else (a0 - a1)) % math.tau
            full = (abs(seg.end[0] - start[0]) <= 1e-4 and abs(seg.end[1] - start[1]) <= 1e-4)
            if full:
                opposite = (2 * cx - start[0], 2 * cy - start[1])
                for target in (opposite, seg.end):
                    out.append(f"A {fmt(r)} {fmt(r)} 0 0 {sweep} {pt(target)}")
            else:
                large = int(delta > math.pi)
                out.append(f"A {fmt(r)} {fmt(r)} 0 {large} {sweep} {pt(seg.end)}")
    if path.closed:
        out.append("Z")
    return " ".join(out)


def _attrs(pairs: list[tuple[str, str]]) -> str:
    return "".join(f" {k}={quoteattr(v)}" for k, v in pairs)


def _layer_label(op: IROperation) -> str:
    return f"{op.order} {op.label} ({op.type})"


def meerk40t_settings(op: IROperation, machine: IRMachine) -> list[tuple[str, str]]:
    """Map LaserBench settings (IR_SCHEMA §3.6) to MeerK40t operation attributes (D-006).

    Only keys present in the settings are written, so MeerK40t's own defaults apply to
    the rest. Units: MeerK40t power is per mille (1000 = 100 %), speed mm/s, frequency kHz.
    """
    s = op.settings

    def number(key: str) -> float | None:
        v = s.get(key)
        if isinstance(v, bool) or not isinstance(v, int | float):
            return None
        return float(v)

    out: list[tuple[str, str]] = []
    power = number("power")
    if power is not None:
        out.append(("power", fmt(round(power * 10))))
    speed = number("speed")
    if speed is not None:
        out.append(("speed", fmt(speed)))
    passes = number("passes")
    if passes is not None and passes >= 1:
        out += [("passes", str(int(passes))), ("passes_custom", "True")]
    frequency = number("frequency")
    if frequency is not None:
        out.append(("frequency", fmt(frequency)))
    q_pulse = number("q_pulse")
    if q_pulse is not None and machine.kind == "galvo":
        out += [("pulse_width", str(int(round(q_pulse)))), ("pulse_width_enabled", "True")]
    interval = number("hatch_interval")
    if interval is not None and interval > 0 and meerk40t_op_type(op) == "op raster":
        out.append(("dpi", str(int(round(25.4 / interval)))))
    return out


def _element_ids(op: IROperation) -> list[str]:
    count = len(op.paths) if (op.type != "fill" or op.hatched) else len(op.regions)
    return [f"op-{op.id}-{i + 1}" for i in range(count)]


def to_svg(job: IRJob, meerk40t_ops: bool = True) -> str:
    """Render the job as SVG text. Deterministic for a given job (NFR-002).

    ``meerk40t_ops`` adds the empty MeerK40t operation groups (§5.1) that pre-load
    MeerK40t's operations list; other programs ignore them.
    """
    m = job.machine
    to_svg_pt, mirrored = svg_transform(m)
    w, h = fmt(m.width), fmt(m.height)
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        "<svg" + _attrs([
            ("xmlns", SVG_NAMESPACE),
            ("xmlns:inkscape", INKSCAPE_NAMESPACE),
            ("xmlns:lb", LB_NAMESPACE),
            ("version", "1.1"),
            ("width", f"{w}mm"),
            ("height", f"{h}mm"),
            ("viewBox", f"0 0 {w} {h}"),
            ("lb:schema-version", str(SCHEMA_VERSION)),
            ("lb:machine", m.id),
        ]) + ">",
        f"  <title>{_text(job.name)}</title>",
    ]

    if meerk40t_ops:
        for op in job.operations:
            ids = _element_ids(op)
            if not ids:
                continue
            lines.append("  <g" + _attrs([
                ("id", f"mk-{op.id}"),
                ("type", meerk40t_op_type(op)),
                ("label", op.label or op.id),
                ("color", op.colour),
                *meerk40t_settings(op, m),
                ("output", "True"),
                ("references", " ".join(ids)),
            ]) + "/>")

    for op in job.operations:
        lines.append("  <g" + _attrs([
            ("id", f"op-{op.id}"),
            ("inkscape:groupmode", "layer"),
            ("inkscape:label", _layer_label(op)),
            ("lb:type", op.type),
            ("lb:kerf-mode", op.kerf_mode),
            ("lb:settings", json.dumps(op.settings, separators=(",", ":"),
                                       ensure_ascii=False, sort_keys=True)),
        ]) + ">")
        ids = iter(_element_ids(op))
        if op.type == "fill" and not op.hatched:
            for region in op.regions:
                d = " ".join(path_data(p, to_svg_pt, mirrored)
                             for p in [region.outer, *region.holes])
                lines.append("    <path" + _attrs([
                    ("id", next(ids)), ("d", d), ("fill", op.colour), ("stroke", "none"),
                    ("fill-rule", "evenodd"),
                ]) + "/>")
        else:
            for p in op.paths:
                lines.append("    <path" + _attrs([
                    ("id", next(ids)), ("d", path_data(p, to_svg_pt, mirrored)),
                    ("fill", "none"), ("stroke", op.colour),
                    ("stroke-width", fmt(HAIRLINE)),
                ]) + "/>")
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def export_svg(job: IRJob, path: Path, meerk40t_ops: bool = True) -> Path:
    """Write to_svg(job) atomically to path and return it."""
    return atomic_write_text(Path(path), to_svg(job, meerk40t_ops=meerk40t_ops))
