# Changelog

All notable changes to LaserBench are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers follow
[Semantic Versioning](https://semver.org/). While the version starts with `0.`, any release
may change behaviour or file formats; check this file before updating.

How to cut a release: see [docs/RELEASING.md](docs/RELEASING.md).

## [Unreleased]

## [0.1.0] - 2026-11-20

First versioned release. Covered by automated tests on FreeCAD 1.1, **not yet tested on a
real laser or in a running copy of MeerK40t**.

### Added
- LaserBench workbench, installable from the Addon Manager as a custom repository or by
  cloning into FreeCAD's `Mod` folder.
- Laser job and operation objects (cut, score, fill) that reference sketches, faces, edges
  or solids and recompute when the model changes.
- Projection of 3D geometry into the job plane (face, direction and section modes).
- Kerf compensation for cuts, duplicate-line removal, and cut ordering (inner shapes first,
  then nearest neighbour).
- Machine profiles and material presets, with two bundled machines and three starter
  materials.
- Colour-coded 3D preview of the job and the machine bed.
- Check job: validation for shapes outside the bed, open cut outlines and similar problems.
- Export to a colour-coded SVG with MeerK40t operation groups, and to a machine-neutral JSON
  job description.
- Send to laser program: export, then launch a configured command with the exported file.
- Scripting API (`laserbench.api`) for exporting from `freecadcmd`.

[Unreleased]: https://github.com/koepnick/FreeCAD_meerk40t/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/koepnick/FreeCAD_meerk40t/releases/tag/v0.1.0
