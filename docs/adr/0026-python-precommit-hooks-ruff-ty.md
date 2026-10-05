---
status: accepted
date: 2026-10-04
---

# 0026. Python-only pre-commit hooks running ruff and ty from the pixi lockfile; RTL lint stays out of the hook

## Context and Problem Statement

The repo's Python verification code (`common/verif/`, `blocks/*/verif/tb/`,
`scripts/`) had no automated style, lint or type gate. Running the tools for
the first time on the 15 tracked Python files found:

- 2 unsorted-import findings (ruff `I001`), and 10 import fixes once the
  library's own modules were classed as first-party;
- 9 of 15 files not ruff-formatted;
- 1 real type error (`ty`, `invalid-method-override`):
  `blocks/basic/verif/tb/test_axis_fifo/test_axis_fifo.py`'s `TB.reset(self)`
  dropped the `cycles` parameter of `BaseTB.reset(self, cycles=2)`, so the
  subclass was not substitutable for its base.

The repo previously had a pre-commit hook, `.githooks/pre-commit` (ADRs 0004,
0022), which ran Verilator lint over the Bender-derived RTL file list. It was
removed in `2da8cf2` (2026-09-13) because a broken or incomplete project-wide
RTL manifest blocked unrelated commits; `CLAUDE.md` recorded that the repo
"intentionally has no pre-commit hook".

## Decision Drivers

- Catch Python lint, formatting and type errors at commit time.
- Do not bring back the failure that removed the old hook: a commit must
  never be blocked by the state of the RTL manifest.
- Tools must come from the pixi lockfile (ADR 0003), not from per-user or
  hook-managed installs, so every machine and CI run the same versions.
- Prefer Astral's Python tooling (ruff, ty), which is fast and already
  partly in use (`ty` was a dependency).

## Considered Options

1. **No hook**; run Python checks by hand or only in CI.
2. **`pre-commit` with upstream hook repos** (`astral-sh/ruff-pre-commit`,
   etc.), which download their own tool environments.
3. **`pre-commit` with `local` hooks** that run the pixi-pinned `ruff` and
   `ty` through `pixi run`, scoped to Python files only.

## Decision Outcome

Chosen option: **3, `local` pre-commit hooks running pixi's ruff and ty on
Python files only**.

- **1** leaves the fast feedback loop to memory; CI would catch problems a
  day later on the nightly.
- **2** gives each hook a second, separately versioned tool install outside
  `pixi.lock`, so a hook and `pixi run lint-py` could disagree.
- **3** keeps one source of tool versions and touches only staged `.py`
  files, so it cannot be blocked by the RTL manifest.

### Consequences

- `.pre-commit-config.yaml`: hooks `ruff-check` (`ruff check --fix
  --exit-non-zero-on-fix`), `ruff-format` and `ty`, all `language: system`,
  `types: [python]`. When a hook rewrites files the commit stops so the
  changes can be reviewed and re-staged.
- `ruff.toml` pins the configuration (ruff defaults plus `I` import
  sorting, py312, line length 88, first-party modules listed) so results do
  not depend on a user-level ruff config. It excludes `*.md`: ruff >= 0.16
  also formats Python blocks inside Markdown, and formatting must never
  rewrite ADRs or design docs.
- `pixi.toml`: `ruff` and `pre-commit` dependencies (exact builds locked in
  `pixi.lock`); tasks `setup-hooks` (`pre-commit install`, once per clone),
  `lint-py` (check only) and `fix-py` (auto-fix lint and formatting, then
  run `ty`).
- Hooks are opt-in per clone (`pixi run setup-hooks`), so the nightly
  workflow also runs `pixi run lint-py` as the enforcing gate.
- **RTL lint is still not a hook.** `pixi run lint-all` stays a manual and
  CI step, for the reason the old hook was removed.
- `ty` errors cannot be auto-fixed; they must be corrected by hand.

### Confirmation

Run 2026-10-04 on branch `feature/python-precommit`:

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` / `ty check` on all tracked Python, after fixes | all clean (15 files) |
| `pixi run pre-commit run --all-files` | ruff check, ruff format, ty: Passed |
| Staged throwaway file with an unused import and `int + str` | all three hooks Failed; ty reported `unsupported-operator` |
| `pixi run fix-py` on a throwaway messy file | 2 lint fixes + reformat applied automatically |
| `pixi install --locked` after adding the dependencies | consistent with `pixi.toml` |
| `pixi run run-regression` after the reformat and the `TB.reset` fix | 10 cocotb testbenches 33/33, `common/verif/tests` 17/17 |

## Affected Files

- `.pre-commit-config.yaml` (new)
- `ruff.toml` (new)
- `pixi.toml`, `pixi.lock` (`ruff`, `pre-commit`; tasks `setup-hooks`, `lint-py`, `fix-py`)
- `.github/workflows/nightly.yml` (Python lint step)
- `blocks/basic/verif/tb/test_axis_fifo/test_axis_fifo.py` (`TB.reset` signature)
- All tracked Python files (import order and formatting only)
- `CLAUDE.md`

## More Information

- Narrows, rather than reverses, the decision behind removing
  `.githooks/pre-commit` (see ADRs [0004](0004-precommit-lint-scope-svh-headers.md)
  and [0022](0022-adder-select-bias-default-and-lint-hook-repair.md) for that
  hook's history): the RTL lint hook stays gone; only Python gets a hook.
- Toolchain management: [0003](0003-pixi-toolchain.md).
