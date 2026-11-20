# SPDX-License-Identifier: LGPL-2.1-or-later
"""K-06: colour-coded SVG export (FR-071, FR-072, IR_SCHEMA §5, D-006)."""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from laserbench.core.export_svg import (
    INKSCAPE_NAMESPACE,
    LB_NAMESPACE,
    export_svg,
    fmt,
    meerk40t_settings,
    svg_transform,
    to_svg,
)
from laserbench.core.ir import (
    GANTRY_ORIGINS,
    IRJob,
    IRMachine,
    IRMaterial,
    IROperation,
    IRPath,
    IRRegion,
    IRSegment,
)

HERE = Path(__file__).parent
GOLDEN = HERE / "golden" / "export_svg_rear_left.svg"
SVG = "{http://www.w3.org/2000/svg}"
INK = "{" + INKSCAPE_NAMESPACE + "}"
LB = "{" + LB_NAMESPACE + "}"

CO2 = IRMachine("co2", "CO2 gantry", "gantry", 600, 400, "rear-left")
GALVO = IRMachine("galvo", "Fiber", "galvo", 150, 150, "center")
PLY = IRMaterial("ply3", "Ply", 3, 0.2)


def square(x: float, y: float, s: float) -> IRPath:
    pts = [(x + s, y), (x + s, y + s), (x, y + s), (x, y)]
    return IRPath(start=(x, y), segments=[IRSegment.line(p) for p in pts], closed=True)


def circle(cx: float, cy: float, r: float, ccw: bool = True) -> IRPath:
    return IRPath(start=(cx + r, cy), segments=[IRSegment.arc((cx + r, cy), (cx, cy), ccw)],
                  closed=True)


def sample_job(machine: IRMachine = CO2) -> IRJob:
    slot = IRPath(start=(20, 20), segments=[
        IRSegment.line((40, 20)),
        IRSegment.arc((40, 30), (40, 25), True),           # half circle
        IRSegment.line((20, 30)),
        IRSegment.arc((20, 20), (20, 25), True),
    ], closed=True)
    wave = IRPath(start=(10, 60), segments=[
        IRSegment.poly([(15, 65), (20, 60)], (25, 65)),
        IRSegment.arc((35, 65), (30, 65), False),           # cw half
        IRSegment.arc((40, 70), (40, 65), True),            # ccw three quarters
    ])
    ops = [
        IROperation(id="Engrave", label="Logo", type="score", order=0, colour="#0000ff",
                    settings={"power": 20, "speed": 200}, paths=[wave]),
        IROperation(id="Fill", label="Panel <fill> & co", type="fill", order=1,
                    colour="#00aa00", settings={"hatch_interval": 0.1, "power": 30.5},
                    regions=[IRRegion(outer=square(100, 100, 50),
                                      holes=[circle(125, 125, 10)])]),
        IROperation(id="Cut", label="Outline", type="cut", order=2, colour="#ff0000",
                    settings={"passes": 2, "power": 65, "speed": 20, "kerf": 0.2},
                    kerf_mode="auto", paths=[slot, square(0, 0, 100), circle(50, 50, 5)]),
        IROperation(id="Empty", label="Nothing", type="cut", order=3, colour="#123456"),
    ]
    return IRJob(name="Box lid", machine=machine, material=PLY, operations=ops)


def structure(text: str) -> list:
    """Structure-normalised form: tags, attributes (as dicts) and text, ignoring layout."""
    def walk(el: ET.Element) -> list:
        return [el.tag, dict(sorted(el.attrib.items())), (el.text or "").strip(),
                [walk(c) for c in el]]
    return walk(ET.fromstring(text.encode("utf-8")))


def test_golden_file() -> None:
    """FR-071: structure matches the reviewed golden file (regenerate deliberately)."""
    text = to_svg(sample_job())
    if not GOLDEN.exists():  # pragma: no cover - first run writes it for review
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8", newline="")
    assert structure(text) == structure(GOLDEN.read_text(encoding="utf-8"))


def test_deterministic_and_atomic(tmp_path: Path) -> None:
    """NFR-002: identical bytes every time; export writes the same text."""
    job = sample_job()
    assert to_svg(job) == to_svg(IRJob.from_json(job.to_json()))
    out = export_svg(job, tmp_path / "lid.svg")
    assert out.read_bytes() == to_svg(job).encode("utf-8")


def test_root_size_and_metadata() -> None:
    root = ET.fromstring(to_svg(sample_job()))
    assert root.attrib["width"] == "600mm" and root.attrib["height"] == "400mm"
    assert root.attrib["viewBox"] == "0 0 600 400"
    assert root.attrib[LB + "schema-version"] == "1"
    assert root.attrib[LB + "machine"] == "co2"
    assert root.find(SVG + "title").text == "Box lid"


def test_layers_per_operation() -> None:
    """FR-071/FR-072: one layer per operation in IR order, with parseable metadata."""
    root = ET.fromstring(to_svg(sample_job()))
    layers = [g for g in root.findall(SVG + "g") if g.get(INK + "groupmode") == "layer"]
    assert [g.get("id") for g in layers] == ["op-Engrave", "op-Fill", "op-Cut", "op-Empty"]
    assert layers[1].get(INK + "label") == "1 Panel <fill> & co (fill)"
    cut = layers[2]
    assert cut.get(LB + "type") == "cut" and cut.get(LB + "kerf-mode") == "auto"
    assert json.loads(cut.get(LB + "settings")) == {"kerf": 0.2, "passes": 2, "power": 65,
                                                    "speed": 20}
    for p in cut:
        assert p.get("fill") == "none" and p.get("stroke") == "#ff0000"
        assert p.get("stroke-width") == "0.025"
    (fill,) = layers[1]
    assert fill.get("fill") == "#00aa00" and fill.get("stroke") == "none"
    assert fill.get("fill-rule") == "evenodd"
    assert fill.get("d").count("M ") == 2  # outer + hole as subpaths
    assert len(layers[3]) == 0


def test_meerk40t_operation_groups() -> None:
    """D-006: empty op groups reference the elements and carry MeerK40t settings."""
    root = ET.fromstring(to_svg(sample_job()))
    ops = [g for g in root.findall(SVG + "g") if "type" in g.attrib]
    assert [(g.get("id"), g.get("type")) for g in ops] == [
        ("mk-Engrave", "op engrave"), ("mk-Fill", "op raster"), ("mk-Cut", "op cut")]
    cut = ops[2]
    assert cut.get("references") == "op-Cut-1 op-Cut-2 op-Cut-3"
    assert (cut.get("power"), cut.get("speed"), cut.get("passes"),
            cut.get("passes_custom")) == ("650", "20", "2", "True")
    assert cut.get("color") == "#ff0000" and cut.get("label") == "Outline"
    assert ops[1].get("dpi") == "254" and ops[1].get("power") == "305"
    assert all(len(g) == 0 for g in ops)
    ids = {p.get("id") for p in root.iter(SVG + "path")}
    for g in ops:
        assert set(g.get("references").split()) <= ids
    plain = ET.fromstring(to_svg(sample_job(), meerk40t_ops=False))
    assert not [g for g in plain.findall(SVG + "g") if "type" in g.attrib]


def test_meerk40t_settings_mapping() -> None:
    op = IROperation(id="x", label="", type="cut", order=0, colour="#000000",
                     settings={"frequency": 30, "q_pulse": 100, "passes": 0,
                               "speed": "fast", "power": True})
    assert meerk40t_settings(op, GALVO) == [
        ("frequency", "30"), ("pulse_width", "100"), ("pulse_width_enabled", "True")]
    assert meerk40t_settings(op, CO2) == [("frequency", "30")]
    hatched = IROperation(id="h", label="", type="fill", order=0, colour="#000000",
                          hatched=True, settings={"hatch_interval": 0.1},
                          paths=[square(0, 0, 1)])
    assert meerk40t_settings(hatched, CO2) == []
    root = ET.fromstring(to_svg(IRJob("j", CO2, PLY, [hatched])))
    (mk,) = [g for g in root.findall(SVG + "g") if "type" in g.attrib]
    assert mk.get("type") == "op engrave"
    (p,) = root.iter(SVG + "path")
    assert p.get("stroke") == "#000000" and p.get("fill") == "none"


@pytest.mark.parametrize(("value", "text"), [
    (1.0, "1"), (0.025, "0.025"), (-0.00001, "0"), (2.50000, "2.5"), (123.45678, "123.4568"),
    (-3.1, "-3.1"), (0, "0"),
])
def test_number_format(value: float, text: str) -> None:
    assert fmt(value) == text


@pytest.mark.parametrize("origin", GANTRY_ORIGINS)
def test_rear_edge_at_top(origin: str) -> None:
    """IR_SCHEMA §5: the drawing is the bed from above, rear at the top, left at the left."""
    m = IRMachine("m", "", "gantry", 600, 400, origin)
    to_pt, _ = svg_transform(m)
    rear = 400.0 if origin.startswith("front") else 0.0
    left = 0.0 if origin.endswith("left") else 600.0
    assert to_pt((left, rear)) == (0, 0)  # the rear-left corner is SVG (0, 0)


def test_galvo_centre() -> None:
    to_pt, mirrored = svg_transform(GALVO)
    assert to_pt((0, 0)) == (75, 75)
    assert to_pt((-75, 75)) == (0, 0)  # rear-left of the field
    assert mirrored


# --- arcs: reconstruct each SVG arc's centre (SVG spec F.6.5) and compare --------------

_NUM = r"-?\d+(?:\.\d+)?"


def _svg_arc_centre(p0, p1, r, large, sweep):
    (x1, y1), (x2, y2) = p0, p1
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    k = max(0.0, (r * r - dx * dx - dy * dy) / (dx * dx + dy * dy))
    sign = -1 if large == sweep else 1
    c = sign * math.sqrt(k)
    cx_, cy_ = c * dy, -c * dx
    return (cx_ + (x1 + x2) / 2, cy_ + (y1 + y2) / 2)


@pytest.mark.parametrize("machine", [
    *(IRMachine("m", "", "gantry", 600, 400, o) for o in GANTRY_ORIGINS), GALVO])
def test_arc_centres_survive_every_origin(machine: IRMachine) -> None:
    """Arc direction and large-arc choice reproduce the IR centre after the y-flip."""
    to_pt, _ = svg_transform(machine)
    arcs = [  # (start, end, centre, ccw), machine frame
        ((10, 0), (0, 10), (0, 0), True),     # quarter ccw
        ((10, 0), (0, 10), (0, 0), False),    # three quarters cw
        ((10, 0), (0, -10), (0, 0), True),    # three quarters ccw
        ((5, 5), (-5, 5), (0, 5), False),     # half
    ]
    for start, end, centre, ccw in arcs:
        path = IRPath(start=start, segments=[IRSegment.arc(end, centre, ccw)])
        job = IRJob("j", machine, PLY, [IROperation(id="a", label="", type="score", order=0,
                                                    colour="#000000", paths=[path])])
        root = ET.fromstring(to_svg(job, meerk40t_ops=False))
        d = next(root.iter(SVG + "path")).get("d")
        nums = [float(n) for n in re.findall(_NUM, d)]
        p0 = (nums[0], nums[1])
        r, _, _, large, sweep, x, y = nums[2:9]
        got = _svg_arc_centre(p0, (x, y), r, int(large), int(sweep))
        want = to_pt(centre)
        assert got == pytest.approx(want, abs=1e-3), (start, end, ccw, d)
        # the arc's angular length is kept (large-arc flag)
        a0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
        a1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
        delta = ((a1 - a0) if ccw else (a0 - a1)) % math.tau
        assert int(large) == int(delta > math.pi)


def test_full_circle_is_two_half_arcs() -> None:
    job = IRJob("j", CO2, PLY, [IROperation(id="c", label="", type="cut", order=0,
                                            colour="#ff0000", paths=[circle(50, 50, 5)])])
    d = next(ET.fromstring(to_svg(job)).iter(SVG + "path")).get("d")
    assert d == "M 55 50 A 5 5 0 0 1 45 50 A 5 5 0 0 1 55 50 Z"
