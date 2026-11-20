# Releasing — LaserBench

## Version numbers (D-015)

LaserBench uses [semantic versioning](https://semver.org/), `MAJOR.MINOR.PATCH`:

| Bump | When | Example |
|---|---|---|
| PATCH | bug fixes only, nothing new for the user to learn | 0.1.0 → 0.1.1 |
| MINOR | new features, or (while in 0.x) anything that changes behaviour or file formats | 0.1.1 → 0.2.0 |
| MAJOR | 1.0.0 once it has been used on real machines and the formats are stable; after that, breaking changes | 0.9.0 → 1.0.0 |

While the major version is 0, users should expect changes between minor versions. A change to
the IR `schema_version` (`docs/IR_SCHEMA.md` §6) always needs at least a minor bump.

No suffixes such as `-beta`: the Addon Manager compares versions as dotted numbers.

## Where the version lives

`package.xml` is the source of truth: it is what FreeCAD's Addon Manager reads and shows next
to the addon. The same string is repeated in `laserbench/__init__.py` (`__version__`) and
`pyproject.toml`, and `CHANGELOG.md` has a section for it. `tools/version.py` writes all of
them at once, and `tests/core/test_version.py` fails CI if they ever disagree.

## How the Addon Manager decides there is an update

This was checked against the Addon Manager source (`addonmanager_workers_startup.py`,
`UpdateChecker`), FreeCAD 1.1:

- **Installed with git** (the usual case when git is available, and always for a `git clone`
  into `Mod`): it runs `git fetch` and reports an update whenever the local copy is *behind*
  the remote branch. **Any new commit on `main` counts as an update**, whether or not the
  version changed. The version number is only a label.
- **Installed without git** (downloaded as a zip): it compares the `<version>` in the
  installed `package.xml` with the one on GitHub, and reports an update only if they differ.
  **If the version is not bumped, these users never see the change.**

So: everything merged to `main` reaches users, and the version must be bumped whenever
something merged to `main` should reach the zip users too. In practice, bump the version in
every pull request that changes what users get, or batch several merged changes into one
release PR.

## Cutting a release

1. Make sure `main` is green in CI.
2. On a branch, bump the version (today's date is filled in for you):

   ```bash
   python tools/version.py bump 0.2.0
   ```

   This updates `package.xml` (`<version>` and `<date>`), `laserbench/__init__.py`,
   `pyproject.toml`, and turns the `## [Unreleased]` heading in `CHANGELOG.md` into
   `## [0.2.0] - <date>` with a fresh empty `Unreleased` section above it.
3. Edit `CHANGELOG.md`: check the entries under the new heading read well for a user (Added /
   Changed / Fixed / Removed), and add the comparison link at the bottom.
4. Check, then open a pull request and merge it once CI passes:

   ```bash
   python tools/version.py check
   pytest tests/core -q && ruff check .
   ```

5. Tag the merge commit on `main` and push the tag:

   ```bash
   git checkout main && git pull
   git tag -a v0.2.0 -m "LaserBench 0.2.0"
   git push origin v0.2.0
   ```

   The `release` workflow runs `tools/version.py check --tag v0.2.0` and fails if the tag and
   `package.xml` disagree. If it fails, delete the tag (`git push --delete origin v0.2.0`,
   `git tag -d v0.2.0`), fix `main`, and tag again.
6. Create a GitHub release from the tag (Releases → Draft a new release → choose `v0.2.0`),
   titled `LaserBench 0.2.0`, with that version's `CHANGELOG.md` section as the notes.

## Day to day

Add a line under `## [Unreleased]` in `CHANGELOG.md` in any pull request that changes
something a user would notice. Internal refactors and test-only changes don't need one.
