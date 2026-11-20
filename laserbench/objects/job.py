# SPDX-License-Identifier: LGPL-2.1-or-later
"""LaserJob FeaturePython object (FR-030 to FR-033). Task W-03.

Properties: ARCHITECTURE.md §4.1. App side only: no Qt, no FreeCADGui (NFR-006).

The job links a machine profile and a material preset by id. They are looked up through
``resolve_presets``, which reads the user's JSON files (``core/presets.py``); tests and
scripts can swap the lookup with ``set_preset_resolver``.

Operations read the job's ``Kerf`` and ``JobPlane`` while they recompute, but they don't
link to the job (that would be a cycle, since the job links them). So each fragment records
the kerf and plane it was built with, and the job rebuilds any operation whose fragment is
stale before assembling. That keeps an expression such as ``Kerf = Spreadsheet.kerf``
correct after a single recompute (FR-031).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import FreeCAD
import Part

from laserbench.core import presets
from laserbench.core.ir import IRIssue, IRJob, IRMaterial, IROperation
from laserbench.core.pipeline import assemble_job
from laserbench.fc.preview import build_preview
from laserbench.objects import operation as op_mod

DEFAULT_FORMATS = ["svg", "json"]

Resolver = Callable[[str, str], tuple[presets.MachineProfile, presets.MaterialPreset]]


def _tr(text: str) -> str:
    return text  # QT_TRANSLATE_NOOP("App::Property", ...) without needing Qt


# (type, name, group, tooltip)
_PROPERTIES: tuple[tuple[str, str, str, str], ...] = (
    ("App::PropertyString", "MachineProfile", "Job",
     _tr("Id of the machine profile (Preferences → LaserBench)")),
    ("App::PropertyString", "MaterialPreset", "Job",
     _tr("Id of the material preset for this machine")),
    ("App::PropertyLength", "Thickness", "Job",
     _tr("Material thickness; can follow an expression such as Spreadsheet.thk")),
    ("App::PropertyLength", "Kerf", "Job",
     _tr("Width of the laser cut, used for kerf compensation; can follow an expression")),
    ("App::PropertyPlacement", "JobPlane", "Job",
     _tr("Plane the geometry is projected onto; its XY is the machine bed")),
    ("App::PropertyLinkList", "Operations", "Job",
     _tr("The job's operations")),
    ("App::PropertyPath", "OutputDir", "Export",
     _tr("Folder for exported files; empty means next to the document")),
    ("App::PropertyStringList", "ExportFormats", "Export",
     _tr("File formats to export: svg, json")),
    ("App::PropertyString", "IRCache", "Internal",
     _tr("Computed job IR (not saved)")),
    ("App::PropertyStringList", "ValidationSummary", "Job",
     _tr("Problems found in the last recompute")),
)


def default_resolver(machine_id: str, material_id: str
                     ) -> tuple[presets.MachineProfile, presets.MaterialPreset]:
    """Look up a profile and preset in the user's LaserBench data folder."""
    data_dir = presets_dir()
    presets.ensure_defaults(data_dir)
    machine = presets.find_machine(presets.load_machines(data_dir), machine_id)
    material = presets.find_material(presets.load_materials(data_dir), machine_id, material_id)
    return machine, material


def presets_dir() -> Path:
    """``<FreeCAD user data>/LaserBench``, where machines.json and materials.json live."""
    return Path(FreeCAD.getUserAppDataDir()) / "LaserBench"


_resolver: Resolver = default_resolver


def set_preset_resolver(resolver: Resolver | None) -> None:
    """Replace how jobs find their profile and preset; ``None`` restores the default."""
    global _resolver
    _resolver = default_resolver if resolver is None else resolver


def resolve_presets(machine_id: str, material_id: str
                    ) -> tuple[presets.MachineProfile, presets.MaterialPreset]:
    """The machine profile and material preset for these ids (raises KeyError/PresetError)."""
    return _resolver(machine_id, material_id)


class LaserJob:
    """Proxy for a ``Part::FeaturePython`` laser job."""

    Type = "LaserBench::LaserJob"

    def __init__(self, obj: FreeCAD.DocumentObject) -> None:
        obj.Proxy = self
        self.setup_properties(obj)

    def setup_properties(self, obj: FreeCAD.DocumentObject) -> None:
        """Add any missing properties. Also called on restore."""
        existing = set(obj.PropertiesList)
        for prop_type, name, group, tip in _PROPERTIES:
            if name in existing:
                continue
            # Prop_Transient (2): the IR cache is recomputed after load, never saved (D-008).
            obj.addProperty(prop_type, name, group, tip, 2 if name == "IRCache" else 0)
            if name == "ExportFormats":
                obj.ExportFormats = list(DEFAULT_FORMATS)
        obj.setEditorMode("IRCache", 2)
        obj.setEditorMode("ValidationSummary", 1)

    def onChanged(self, obj: FreeCAD.DocumentObject, prop: str) -> None:  # noqa: N802
        # Operations depend on these but can't link back to the job, so tell them here.
        # (A change made by an expression during recompute is caught in execute instead.)
        if prop not in ("Kerf", "JobPlane") or "Restoring" in obj.State:
            return
        for op in getattr(obj, "Operations", []):
            op.touch()

    def execute(self, obj: FreeCAD.DocumentObject) -> None:
        """Collect operation fragments and run core.pipeline.assemble_job (ARCHITECTURE §3).

        Stores IRCache, ValidationSummary and the preview Shape. User-correctable problems
        become issues; only hard failures raise (D-009).
        """
        try:
            machine, material = resolve_presets(obj.MachineProfile, obj.MaterialPreset)
        except (KeyError, ValueError, OSError) as exc:
            message = str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)
            obj.IRCache = ""
            obj.ValidationSummary = [f"error: {message}"]
            obj.Shape = Part.Shape()
            raise FreeCAD.Base.FreeCADError(f"{obj.Label}: {message}") from exc

        kerf = obj.Kerf.Value
        fragments: list[IROperation] = []
        issues: list[IRIssue] = []
        for op in enabled_operations(obj):
            if op_mod.fragment_context(op) != op_mod.job_context_key(obj):
                # Built before this job's Kerf/JobPlane settled, e.g. by an expression
                # evaluated in this recompute (FR-031). onChanged has touched it meanwhile.
                op.recompute()
                op.purgeTouched()
            fragment, op_issues = op_mod.read_fragment(op)
            fragments.append(fragment)
            issues.extend(op_issues)

        preset_settings = {t: material.settings_for(t) for t in ("cut", "score", "fill")}
        preset_settings["cut"]["kerf"] = kerf  # the kerf actually used, not the preset's
        job = assemble_job(
            name=obj.Label,
            machine=machine.to_ir(),
            material=IRMaterial(id=material.id, name=material.name,
                                thickness=obj.Thickness.Value, kerf=kerf),
            fragments=fragments,
            preset_settings=preset_settings,
            fragment_issues=issues,
            source_document=os.path.basename(obj.Document.FileName or ""),
        )
        obj.IRCache = job.to_json()
        obj.ValidationSummary = [f"{i.severity}: {i.code}: {i.message}" for i in job.issues]
        obj.Shape = _preview(fragments, obj.JobPlane)

    def onDocumentRestored(self, obj: FreeCAD.DocumentObject) -> None:  # noqa: N802
        self.setup_properties(obj)

    def dumps(self) -> dict[str, Any] | None:
        return None

    def loads(self, state: dict[str, Any] | None) -> None:
        return None


def enabled_operations(job_obj: FreeCAD.DocumentObject) -> list[FreeCAD.DocumentObject]:
    """The job's LaserOperations that are enabled, in list order (FR-045)."""
    return [op for op in job_obj.Operations
            if getattr(getattr(op, "Proxy", None), "Type", None) == op_mod.LaserOperation.Type
            and op.Enabled]


def _preview(fragments: list[IROperation], job_plane: FreeCAD.Placement) -> Part.Shape:
    if not any(f.paths or f.regions for f in fragments):
        return Part.Shape()
    # Baked into the geometry: Part::Feature replaces a shape's Placement with its own.
    return build_preview(fragments, FreeCAD.Placement()).transformGeometry(job_plane.toMatrix())


def make_job(doc: FreeCAD.Document, machine: str, material: str, name: str = "LaserJob"
             ) -> FreeCAD.DocumentObject:
    """Create a LaserJob for a machine profile id and material preset id (FR-030).

    Thickness and Kerf start from the material preset when it can be found; both stay
    editable and expression-bindable (FR-031).
    """
    obj = doc.addObject("Part::FeaturePython", name)
    LaserJob(obj)
    obj.MachineProfile = machine
    obj.MaterialPreset = material
    try:
        _, preset = resolve_presets(machine, material)
    except (KeyError, ValueError, OSError):
        pass  # execute reports the bad id; the job is still created so it can be fixed
    else:
        obj.Thickness = preset.thickness
        obj.Kerf = preset.kerf
    return obj


def add_operation(job_obj: FreeCAD.DocumentObject, op_obj: FreeCAD.DocumentObject) -> None:
    """Append an operation to the job (FR-032)."""
    job_obj.Operations = list(job_obj.Operations) + [op_obj]


def get_ir(job_obj: FreeCAD.DocumentObject) -> IRJob:
    """The job's last computed IR (recomputing first if the cache is empty)."""
    if not job_obj.IRCache:
        job_obj.recompute()
    if not job_obj.IRCache:
        summary = "; ".join(job_obj.ValidationSummary) or "recompute failed"
        raise ValueError(f"{job_obj.Label} has no IR: {summary}")
    return IRJob.from_json(job_obj.IRCache)


def jobs_in(doc: FreeCAD.Document) -> list[FreeCAD.DocumentObject]:
    """Every LaserJob in ``doc``, in document order."""
    return [o for o in doc.Objects
            if getattr(getattr(o, "Proxy", None), "Type", None) == LaserJob.Type]


def ordered_operations(job_obj: FreeCAD.DocumentObject) -> list[FreeCAD.DocumentObject]:
    """The job's operations sorted the way they run: by Order, then list position."""
    ops = list(job_obj.Operations)
    return sorted(ops, key=lambda o: (getattr(o, "Order", 0), ops.index(o)))


def move_operation(job_obj: FreeCAD.DocumentObject, op_obj: FreeCAD.DocumentObject,
                   delta: int) -> bool:
    """Move an operation ``delta`` places earlier (<0) or later (>0) in the run order.

    Renumbers Order to 0..n-1 and keeps the Operations list (the tree order) in step.
    Returns False when the operation is already at that end.
    """
    ops = ordered_operations(job_obj)
    i = ops.index(op_obj)
    j = max(0, min(len(ops) - 1, i + delta))
    if i == j:
        return False
    ops.insert(j, ops.pop(i))
    for n, op in enumerate(ops):
        if op.Order != n:
            op.Order = n
    job_obj.Operations = ops
    return True
