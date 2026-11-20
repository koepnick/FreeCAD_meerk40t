# LaserBench

A FreeCAD workbench that turns parametric FreeCAD geometry into laser jobs.

You model a part as usual (Sketcher, PartDesign, Spreadsheet-driven dimensions), then add
laser **operations** (cut, score, fill) that point at that geometry. When the model changes,
the job recomputes. LaserBench exports a colour-coded **SVG** plus a machine-neutral **JSON**
description of the job, and can open the SVG in your laser program (MeerK40t first).

LaserBench never talks to a laser. It writes files and, if you ask it to, launches a program
you have configured. You always check and start the job yourself in that program.

> **Status: early (0.x), not yet tested on real hardware.** The workbench, its commands and
> the export are covered by automated tests on FreeCAD 1.1, but no LaserBench file has yet
> been cut on a real machine or confirmed in a running copy of MeerK40t. Treat every output as
> something to preview and check before you fire the laser. See "Known limitations" below.

## Requirements

- FreeCAD 1.0 or later. Developed and tested against FreeCAD 1.1; 1.0 should work but is not
  tested in CI.
- No extra Python packages. LaserBench uses only what ships with FreeCAD.
- Windows, macOS (including Apple Silicon) and Linux.
- Optional: [MeerK40t](https://github.com/meerk40t/meerk40t) 0.9.8 or later, or any other
  program that can open an SVG.

## Installation

### Addon Manager (custom repository)

LaserBench is not in the official FreeCAD addon index yet, so add it as a custom repository:

1. Open **Edit → Preferences → Addon Manager**.
2. Under **Custom repositories**, add
   `https://github.com/koepnick/FreeCAD_meerk40t` with branch `main`.
3. Open **Tools → Addon manager**, find **LaserBench**, and click **Install**.
4. Restart FreeCAD.

Updates then appear in the Addon Manager like any other addon. The version shown there
comes from `package.xml`; what changed in each version is in [CHANGELOG.md](CHANGELOG.md).

### Manual install (git clone)

The repository root is the addon folder, so clone it straight into FreeCAD's `Mod` folder:

```
git clone https://github.com/koepnick/FreeCAD_meerk40t.git <Mod folder>/LaserBench
```

The `Mod` folder is inside FreeCAD's user data folder. You can find it by typing
`FreeCAD.getUserAppDataDir()` in FreeCAD's Python console. Typical locations for FreeCAD 1.1:

| System | Mod folder |
|---|---|
| Linux | `~/.local/share/FreeCAD/v1-1/Mod` |
| macOS | `~/Library/Application Support/FreeCAD/v1-1/Mod` |
| Windows | `%APPDATA%\FreeCAD\v1-1\Mod` |

FreeCAD 1.0 uses the same places without the `v1-1` part. Restart FreeCAD after cloning, and
use `git pull` in that folder to update.

If you keep the checkout elsewhere, `python tools/dev_install.py` links it into the newest
`Mod` folder it finds.

## Quick start

1. Model your part and **save the document**. Exports go next to the `.FCStd` file unless you
   set a different folder.
2. Switch to the **LaserBench** workbench.
3. **Create job**: pick a machine profile and a material preset.
4. Select sketches, faces, edges or solids and click **Add operation**. Choose:
   - **Cut**: closed outlines cut through, with kerf compensation.
   - **Score**: lines marked on the surface, no kerf.
   - **Fill**: filled areas engraved.
5. Use **Move operation up/down** to set the order and **Enable/disable operation** to skip
   one. The 3D view shows a colour-coded preview of the job.
6. Click **Check job**. It lists problems such as shapes outside the bed or open cut
   outlines; click one to find it in the model.
7. Click **Export job** to write `<job name>.svg` and `<job name>.json`, or
   **Send to laser program** to export and open the file in your laser program.

Change a dimension in your model and export again: the job follows the model.

Everything is scriptable too, for example from `freecadcmd`:

```
import laserbench.api as lb
lb.export_document("lid.FCStd")
```

## Supported machines

LaserBench is machine-neutral. A **machine profile** gives the bed size, the origin corner,
the default kerf and the command used to open jobs. Two profiles ship as defaults:

| Profile | Type | Work area | Origin |
|---|---|---|---|
| OMTech MF1624-60 (CO2, 60 W) | gantry | 600 × 400 mm | rear left |
| OMTech 50 W fiber, 210 mm lens | galvo | 150 × 150 mm | centre |

The material presets (3 mm birch ply, 3 mm cast acrylic, anodised aluminium marking) are
starting points only. Run a test on scrap before trusting any power or speed setting.

Profiles and presets live in `machines.json` and `materials.json` in the `LaserBench` folder
inside FreeCAD's user data folder. They are created on first use; edit them in a text editor
to add your own machine. A preferences page for this is planned.

## Handing jobs to MeerK40t

**Send to laser program** exports the job and then runs the `send_command` of the job's
machine profile. The default profiles have no command, so add one to `machines.json`, for
example:

```
"send_command": ["meerk40t", "{svg}"]
```

On macOS, if MeerK40t is installed as an app:

```
"send_command": ["open", "-a", "MeerK40t", "--args", "{svg}"]
```

The placeholders `{svg}`, `{json}` and `{job_name}` are replaced with the exported file
paths and the job name. The command runs directly, never through a shell.

**Safety.** Sending only opens the file. The laser does not move until you start the job in
MeerK40t. LaserBench refuses a MeerK40t command that contains `-a` or `--auto`, which would
start the laser on load. Always check the job in MeerK40t (size, position, operations, power
and speed) and use its simulate or preview before running it, and never leave a running
laser unattended.

If MeerK40t is already open, launching it again asks "Another instance is running!", and
answering No loads nothing. Close MeerK40t first or open the exported SVG from its File menu.

### How MeerK40t reads the file (not yet verified)

How MeerK40t turns the SVG into its own operations is decision **D-006**, which is still
*proposed*. It is based on reading the MeerK40t 0.9.8100 source code, not on loading a file in
a running MeerK40t:

- The SVG keeps one colour-coded layer per operation, so Inkscape and other programs can read
  it.
- It also carries one MeerK40t operation group per operation (cut, engrave or raster) with
  its power, speed and passes, so the settings should travel with the file instead of
  depending on MeerK40t's colour matching.
- Opening such a file replaces MeerK40t operations that are empty at that moment, the same
  as opening a file saved by MeerK40t.

Until this is confirmed on a real MeerK40t install, check that the Operations tree, the size
and the position look right before running anything. Reports of what you see are very
welcome on the issue tracker.

## Known limitations

- Not yet tested on real hardware, or with a running MeerK40t (see D-006 above).
- FreeCAD 1.0 is supported but only FreeCAD 1.1 is tested in CI.
- No preferences page yet: edit `machines.json` and `materials.json` by hand.
- Vector work only: no photo or raster image engraving, and no direct control of laser
  controllers.

## Contributing and support

Bug reports and ideas: <https://github.com/koepnick/FreeCAD_meerk40t/issues>.
Design notes and requirements are in the
[docs folder](https://github.com/koepnick/FreeCAD_meerk40t/tree/main/docs).

## Licence

LaserBench is licensed under the
[GNU Lesser General Public License v2.1 or later](https://github.com/koepnick/FreeCAD_meerk40t/blob/main/LICENSE)
(LGPL-2.1-or-later), the same licence as FreeCAD.
