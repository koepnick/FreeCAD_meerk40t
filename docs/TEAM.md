# Team Playbook — for the Coordinator (team lead)

This file tells the coordinator how to run the agent team. Teammates don't need it in full.
Their spawn prompts below contain what they need.

## 0. Setup (owner, once)

Agent teams in Claude Code are **experimental** and off by default. Enable them in
`.claude/settings.json` (already in this repo) or your shell:

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

Teammates load the project context (this repo's CLAUDE.md, MCP servers, skills) but **not** the
coordinator's conversation. Anything a teammate needs to know must be in the repo docs or in
its spawn prompt. That's why these documents exist.

Feature details change. Check https://code.claude.com/docs/en/agent-teams for current
behaviour and limitations (session resumption, shutdown) before a long run.

## 1. How to run the project

1. **Phase 0 solo.** The coordinator does C-01, C-02, and C-03 alone, without spawning
   anyone. Commit. A frozen contract plus stubs is the single biggest lever for parallel
   quality.
2. **Load TASKS.md into the shared task list** with dependencies as written.
3. **Spawn Phase 1 teammates** (§3), staggered: geometry-dev and core-dev first (critical
   path), then presets-dev and qa, then workbench-dev once G-04 is near done (or immediately
   for W-01).
4. **Gate each task** with the review checklist (§4) before marking it complete.
5. **Escalate OPEN decisions** to the owner in one batched message. Don't drip-feed them.
6. **Close Phase 1** with Q-02 (headline e2e) and Q-04 (trace audit) green. Then summarise for
   the owner: what works, the open decisions, and a demo script.

## 2. Coordinator rules
- One task, one owner, one set of files (ARCHITECTURE §7). If two tasks would touch the same
  file at once, sequence them.
- If isolated git worktrees per teammate are available, use them, and merge in dependency order.
- Contract change requests (IR, public API) come to the coordinator. Approve or deny, log in
  DECISIONS.md, then notify every affected teammate directly.
- Keep CLAUDE.md under ~150 lines. Move detail into docs/.
- Prefer 3–5 active teammates. More adds coordination cost without speeding up a codebase
  this size.

## 3. Spawn prompts

Use these verbatim, then add the specific task IDs being assigned.

### geometry-dev
> You are **geometry-dev** on LaserBench, a FreeCAD workbench. Read `CLAUDE.md`,
> `docs/ARCHITECTURE.md` (§3, §5), and `docs/IR_SCHEMA.md` first. You own `laserbench/fc/**`
> only. You turn FreeCAD source references into 2D wires in the job plane, apply kerf
> compensation with `makeOffset2D`, and convert Part edges to IR segments. Run tests with
> `freecadcmd tests/fc/run_all.py`. Ask qa for fixtures you need rather than writing them in
> `tests/fixtures/`. Record your projection-API findings in DECISIONS D-013 via the
> coordinator. Never import Qt or FreeCADGui. Done means tests are green, acceptance criteria
> in TASKS.md are met, and you've sent the coordinator a short note listing changed files and
> any risks.

### core-dev
> You are **core-dev** on LaserBench. Read `CLAUDE.md`, `docs/ARCHITECTURE.md`, and
> `docs/IR_SCHEMA.md`. You own `laserbench/core/**` (except `ir.py`, `presets.py`, and
> `handoff.py`) and `tests/core/**`. Your code is **pure Python standard library**: importing
> FreeCAD, Part, or Qt fails the layering test. Work on IR dataclasses from `core/ir.py`; do
> not change them. Request changes from the coordinator. Aim for ≥90% coverage, deterministic
> output, and 4-decimal float formatting. Test with `pytest tests/core -q`.

### workbench-dev
> You are **workbench-dev** on LaserBench. Read `CLAUDE.md`, `docs/ARCHITECTURE.md` (§4, §6),
> and `docs/REQUIREMENTS.md` §2.1–2.5 and §2.9. You own `laserbench/objects/**`,
> `laserbench/gui/**` (except `gui/prefs.py`), `api.py`, `InitGui.py`, `Init.py`,
> `package.xml`, and `resources/` icons/UI. Build FeaturePython objects whose `execute()` calls
> the fc and core pipeline. Never put geometry algorithms in objects or gui: call `fc/` and
> `core/`. Use `from PySide import QtCore, QtGui`. Proxies must restore without the workbench
> installed (NFR-006). Every GUI action needs a matching `api.py` function.

### presets-dev
> You are **presets-dev** on LaserBench. Read `CLAUDE.md` and `docs/IR_SCHEMA.md` §4. You own
> `core/presets.py`, `core/handoff.py`, `resources/defaults/*.json`, their tests, and
> `gui/prefs.py` (for P-04 only). Presets are opaque key/values except `kerf`,
> `hatch_interval`, and `hatch_angle`. The handoff runner uses argument lists only, never
> `shell=True`. Machine dimensions are owner-supplied (DECISIONS D-012): use clearly marked
> placeholders until then.

### qa
> You are **qa** on LaserBench. Read `CLAUDE.md`, `docs/REQUIREMENTS.md`, and `docs/TESTING.md`.
> You own `tests/fc/**`, `tests/fixtures/**`, `docs/user/**`, and `docs/TRACE.md`. Fixtures
> are Python scripts that **build** .FCStd files headlessly. Never commit binaries. You
> haven't seen how features were implemented, and that's the point: test against the
> requirement text, not the code. Report failing behaviour to the owning teammate with a
> minimal reproduction. Task Q-03 is a research spike: write findings, don't change code.

## 4. Review checklist (coordinator, before marking any task done)
- [ ] Cites requirement IDs. Acceptance criteria demonstrably met (a test name or screenshot).
- [ ] Only owned files changed. `git diff --stat` reviewed.
- [ ] `pytest tests/core -q` and `freecadcmd tests/fc/run_all.py` green, and `ruff check` clean.
- [ ] Layering test green. No new third-party imports.
- [ ] No change to IR/API without a DECISIONS entry.
- [ ] User-facing errors are actionable (no raw tracebacks).
- [ ] Deterministic output where applicable (run the export twice and diff).

## 5. Escalate to the owner when
- Any OPEN item in DECISIONS.md blocks a task.
- A requirement turns out to be infeasible or contradictory. Propose an alternative.
- A test needs real hardware or real MeerK40t behaviour that can't be simulated.
- Scope creep: someone wants to add controller I/O (OS-1). The answer is "later". Log it.
