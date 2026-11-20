"""C-01: IR dataclasses, canonical serialisation, and schema_version handling."""

from __future__ import annotations

import json

import pytest

from laserbench.core import ir
from laserbench.core.ir import (
    IRBounds,
    IRError,
    IRIssue,
    IRJob,
    IRMachine,
    IRMaterial,
    IROperation,
    IRPath,
    IRRegion,
    IRSegment,
    IRVersionError,
)


def square(x: float, y: float, size: float) -> IRPath:
    return IRPath(
        start=(x, y),
        segments=[
            IRSegment.line((x + size, y)),
            IRSegment.line((x + size, y + size)),
            IRSegment.line((x, y + size)),
            IRSegment.line((x, y)),
        ],
        closed=True,
    )


def circle(cx: float, cy: float, r: float) -> IRPath:
    return IRPath(start=(cx + r, cy), segments=[IRSegment.arc((cx + r, cy), (cx, cy), True)],
                  closed=True)


def sample_job() -> IRJob:
    cut = IROperation(
        id="LaserOperation",
        label="Outline",
        type="cut",
        order=1,
        colour="#FF0000",
        settings={"speed": 20, "power": 65.5, "passes": 1, "air": True, "note": "ply"},
        kerf_mode="auto",
        paths=[square(10, 10, 50), circle(35, 35, 5)],
    )
    score = IROperation(
        id="LaserOperation001",
        label="Text",
        type="score",
        order=2,
        colour="#0000ff",
        settings={"speed": 200},
        paths=[IRPath(start=(12, 12), segments=[
            IRSegment.poly([(13, 12.5), (14, 13.25)], (15, 14)),
            IRSegment.arc((20, 14), (17.5, 14), False),
        ])],
    )
    fill = IROperation(
        id="LaserOperation002",
        label="Logo",
        type="fill",
        order=3,
        colour="#00aa00",
        settings={"hatch_interval": 0.1, "hatch_angle": 45},
        regions=[IRRegion(outer=square(70, 10, 20), holes=[circle(80, 20, 3)])],
    )
    return IRJob(
        name="Box lid",
        machine=IRMachine(id="co2", name="CO2 gantry", kind="gantry", width=600, height=400,
                          origin="rear-left"),
        material=IRMaterial(id="ply3", name="Birch ply 3 mm", thickness=3, kerf=0.2),
        operations=[cut, score, fill],
        bounds=IRBounds(10, 10, 90, 60),
        issues=[IRIssue("OPEN_CONTOUR", "Open contour in Text", "LaserOperation001", (12, 12))],
        source_document="lid.FCStd",
    )


# --- round trip ------------------------------------------------------------


def test_dict_round_trip_is_identity() -> None:
    job = sample_job()
    again = IRJob.from_dict(job.to_dict())
    assert again == job
    assert again.to_dict() == job.to_dict()


def test_json_round_trip_is_byte_identical() -> None:
    text = sample_job().to_json()
    assert IRJob.from_json(text).to_json() == text


def test_json_is_deterministic_across_builds() -> None:
    assert sample_job().to_json() == sample_job().to_json()


def test_json_survives_a_generic_json_reload() -> None:
    # A consumer that reads and re-dumps with the same settings must not change bytes.
    text = sample_job().to_json()
    redumped = json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False) + "\n"
    assert redumped == text


def test_top_level_key_order_is_fixed() -> None:
    keys = list(json.loads(sample_job().to_json()))
    assert keys == ["schema_version", "units", "generator", "name", "source_document",
                    "machine", "material", "bounds", "operations", "issues"]


def test_minimal_job_round_trip() -> None:
    job = IRJob(name="", machine=IRMachine("g", "", "galvo", 110, 110, "center"),
                material=IRMaterial("steel", "", 0, 0))
    assert IRJob.from_json(job.to_json()) == job
    assert json.loads(job.to_json())["bounds"] is None


# --- canonical numbers ----------------------------------------------------


def test_floats_rounded_to_four_decimals() -> None:
    seg = IRSegment.line((1.234567, 2.00004999))
    assert seg.end == (1.2346, 2.0)


def test_negative_zero_normalised() -> None:
    path = IRPath(start=(-0.0, -0.00001), segments=[IRSegment.line((1, 0))])
    assert "-0" not in json.dumps(path.to_dict())


def test_ints_become_floats_in_geometry() -> None:
    assert IRSegment.line((1, 2)).to_dict()["end"] == [1.0, 2.0]


def test_settings_sorted_and_typed() -> None:
    op = sample_job().operations[0]
    assert list(op.settings) == sorted(op.settings)
    assert op.settings["speed"] == 20 and isinstance(op.settings["speed"], int)
    assert op.settings["air"] is True


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "1", None, True])
def test_non_finite_or_non_numbers_rejected(bad: object) -> None:
    with pytest.raises(IRError):
        IRSegment.line((bad, 0))  # type: ignore[arg-type]


def test_settings_reject_nested_values() -> None:
    with pytest.raises(IRError):
        IROperation("a", "", "cut", 0, "#000000", settings={"x": [1, 2]})  # type: ignore[dict-item]


# --- schema_version (NFR-007) ----------------------------------------------


def test_newer_schema_version_refused() -> None:
    d = sample_job().to_dict()
    d["schema_version"] = ir.SCHEMA_VERSION + 1
    with pytest.raises(IRVersionError, match="newer"):
        IRJob.from_dict(d)


def test_older_schema_version_refused() -> None:
    d = sample_job().to_dict()
    d["schema_version"] = 0
    with pytest.raises(IRVersionError, match="older"):
        IRJob.from_dict(d)


@pytest.mark.parametrize("value", [None, "1", 1.0, True])
def test_bad_schema_version_refused(value: object) -> None:
    d = sample_job().to_dict()
    if value is None:
        del d["schema_version"]
    else:
        d["schema_version"] = value
    with pytest.raises(IRVersionError):
        IRJob.from_dict(d)


def test_version_errors_are_ir_errors() -> None:
    assert issubclass(IRVersionError, IRError)


# --- strict loading -------------------------------------------------------


def test_unknown_field_rejected() -> None:
    d = sample_job().to_dict()
    d["operations"][0]["extra"] = 1
    with pytest.raises(IRError, match="unknown field"):
        IRJob.from_dict(d)


def test_missing_field_rejected() -> None:
    d = sample_job().to_dict()
    del d["material"]["kerf"]
    with pytest.raises(IRError, match="missing"):
        IRJob.from_dict(d)


def test_wrong_units_rejected() -> None:
    d = sample_job().to_dict()
    d["units"] = "in"
    with pytest.raises(IRError, match="units"):
        IRJob.from_dict(d)


def test_invalid_json_text() -> None:
    with pytest.raises(IRError):
        IRJob.from_json("{not json")


def test_reserved_image_path_kind_rejected() -> None:
    d = sample_job().to_dict()
    d["operations"][0]["paths"][0]["kind"] = "image"
    with pytest.raises(IRError, match="reserved"):
        IRJob.from_dict(d)


def test_line_segment_with_arc_fields_rejected() -> None:
    with pytest.raises(IRError, match="unknown field"):
        IRSegment.from_dict({"kind": "line", "end": [0, 0], "ccw": True})


# --- structural rules -----------------------------------------------------


def test_closed_path_must_return_to_start() -> None:
    with pytest.raises(IRError, match="closed path"):
        IRPath(start=(0, 0), segments=[IRSegment.line((1, 0))], closed=True)


def test_closed_path_tolerance() -> None:
    IRPath(start=(0, 0), segments=[IRSegment.line((1, 0)), IRSegment.line((0.00005, 0))],
           closed=True)


def test_empty_path_rejected() -> None:
    with pytest.raises(IRError):
        IRPath(start=(0, 0), segments=[])


def test_arc_needs_center_and_direction() -> None:
    with pytest.raises(IRError):
        IRSegment("arc", (1, 1))


def test_iter_segments_yields_starts() -> None:
    path = square(0, 0, 1)
    starts = [s for s, _ in path.iter_segments()]
    assert starts == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert path.end == (0.0, 0.0)


def test_region_boundaries_must_be_closed() -> None:
    open_path = IRPath(start=(0, 0), segments=[IRSegment.line((1, 0))])
    with pytest.raises(IRError, match="closed"):
        IRRegion(outer=open_path)


def test_regions_only_on_fill() -> None:
    with pytest.raises(IRError):
        IROperation("a", "", "cut", 0, "#000000", regions=[IRRegion(square(0, 0, 1))])


def test_unhatched_fill_has_no_paths() -> None:
    with pytest.raises(IRError):
        IROperation("a", "", "fill", 0, "#000000", paths=[square(0, 0, 1)])


def test_hatched_only_on_fill() -> None:
    with pytest.raises(IRError):
        IROperation("a", "", "score", 0, "#000000", hatched=True)


def test_colour_normalised_and_validated() -> None:
    assert IROperation("a", "", "cut", 0, "#ABCDEF").colour == "#abcdef"
    with pytest.raises(IRError):
        IROperation("a", "", "cut", 0, "red")


def test_galvo_origin_is_center_only() -> None:
    with pytest.raises(IRError):
        IRMachine("g", "", "galvo", 110, 110, "front-left")
    with pytest.raises(IRError):
        IRMachine("c", "", "gantry", 600, 400, "center")


def test_duplicate_operation_ids_rejected() -> None:
    job = sample_job()
    with pytest.raises(IRError, match="duplicate"):
        IRJob(job.name, job.machine, job.material, [job.operations[0], job.operations[0]])


def test_issue_must_reference_known_operation() -> None:
    job = sample_job()
    with pytest.raises(IRError, match="unknown operation"):
        IRJob(job.name, job.machine, job.material, job.operations,
              issues=[IRIssue("EMPTY_OPERATION", "nothing", "nope")])


def test_issue_severity_fixed_by_code() -> None:
    assert IRIssue("OUT_OF_BOUNDS", "outside").severity == "error"
    with pytest.raises(IRError):
        IRIssue("OUT_OF_BOUNDS", "outside", severity="warning")
    with pytest.raises(IRError):
        IRIssue("MADE_UP", "x")


def test_has_errors() -> None:
    job = sample_job()
    assert not job.has_errors
    job.issues.append(IRIssue("OUT_OF_BOUNDS", "outside"))
    assert job.has_errors


def test_bounds_properties_and_order() -> None:
    b = IRBounds(1, 2, 4, 8)
    assert (b.width, b.height) == (3, 6)
    with pytest.raises(IRError):
        IRBounds(5, 0, 1, 1)
