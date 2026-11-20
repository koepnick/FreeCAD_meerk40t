# SPDX-License-Identifier: LGPL-2.1-or-later
"""W-03 (core half): assemble_job runs merge → transform → dedupe → order → validate."""

from __future__ import annotations

from laserbench.core.ir import (
    IRBounds,
    IRIssue,
    IRJob,
    IRMachine,
    IRMaterial,
    IROperation,
    IRPath,
    IRRegion,
    IRSegment,
)
from laserbench.core.pipeline import assemble_job, job_bounds

REAR_LEFT = IRMachine(id="co2", name="CO2", kind="gantry", width=600, height=400,
                      origin="rear-left")
GALVO = IRMachine(id="g", name="G", kind="galvo", width=150, height=150, origin="center")
PLY = IRMaterial(id="ply3", name="Ply", thickness=3, kerf=0.2)
PRESET = {"cut": {"power": 65, "speed": 20, "kerf": 0.2}, "score": {"power": 20}}


def square(x, y, size) -> IRPath:
    pts = [(x + size, y), (x + size, y + size), (x, y + size), (x, y)]
    return IRPath(start=(x, y), segments=[IRSegment.line(p) for p in pts], closed=True)


def frag(id_, type_="cut", order=0, paths=(), regions=(), settings=None) -> IROperation:
    return IROperation(id=id_, label=id_, type=type_, order=order, colour="#ff0000",
                       settings=settings or {}, paths=list(paths), regions=list(regions))


def test_full_pipeline() -> None:
    plate = frag("Plate", order=1, settings={"power": "70"},
                 paths=[square(0, 0, 100), square(10, 10, 10), square(100, 0, 50)])
    engrave = frag("Logo", "score", order=0, paths=[square(20, 20, 5)])
    job = assemble_job("lid", REAR_LEFT, PLY, [plate, engrave], PRESET,
                       source_document="lid.FCStd")
    assert isinstance(job, IRJob)
    IRJob.from_dict(job.to_dict())  # schema-valid
    assert [op.id for op in job.operations] == ["Logo", "Plate"]  # sorted by order
    logo, cut = job.operations
    assert logo.settings == {"power": 20}
    assert cut.settings == {"kerf": 0.2, "power": 70, "speed": 20}  # override coerced, wins
    # rear-left: job y is flipped into 400 - y.
    assert job.bounds == IRBounds(0, 300, 150, 400)
    # The hole comes before the part around it; the shared edge x=100 is cut once.
    assert cut.paths[0].closed and job_bounds([frag("h", paths=[cut.paths[0]])]) == IRBounds(
        10, 380, 20, 390)
    assert sum(len(p.segments) for p in cut.paths) == 4 + 4 + 3
    assert job.issues == []
    assert job.source_document == "lid.FCStd"


def test_fragment_issues_first_and_moved_to_the_machine_frame() -> None:
    issue = IRIssue(code="KERF_COLLAPSE", message="gone", operation_id="Plate",
                    location=(5, 5))
    broken = IRIssue(code="BROKEN_SOURCE", message="Pad.Face6 missing", operation_id="Plate")
    job = assemble_job("j", REAR_LEFT, PLY, [frag("Plate", paths=[square(0, 0, 10)])], PRESET,
                       fragment_issues=[issue, broken])
    assert [i.code for i in job.issues] == ["KERF_COLLAPSE", "BROKEN_SOURCE"]
    assert job.issues[0].location == (5, 395)


def test_validation_runs_on_the_machine_frame() -> None:
    too_far = frag("Big", paths=[square(-80, -80, 20)])
    job = assemble_job("j", GALVO, PLY, [too_far, frag("Empty", "score", order=1)], PRESET)
    assert [(i.code, i.operation_id) for i in job.issues] == [
        ("OUT_OF_BOUNDS", "Big"), ("EMPTY_OPERATION", "Empty")]


def test_fill_regions_pass_through_transformed() -> None:
    fill = frag("Fill", "fill", regions=[IRRegion(outer=square(0, 0, 10))])
    job = assemble_job("j", REAR_LEFT, PLY, [fill], {})
    assert job.operations[0].regions[0].outer.start == (0, 400)
    assert job.bounds == IRBounds(0, 390, 10, 400)


def test_empty_job() -> None:
    job = assemble_job("j", REAR_LEFT, PLY, [], PRESET)
    assert job.operations == [] and job.bounds is None and job.issues == []


def test_deterministic() -> None:
    frags = [frag("A", paths=[square(i * 15, 0, 10) for i in range(5)])]
    a = assemble_job("j", REAR_LEFT, PLY, frags, PRESET).to_json()
    b = assemble_job("j", REAR_LEFT, PLY, frags, PRESET).to_json()
    assert a == b
