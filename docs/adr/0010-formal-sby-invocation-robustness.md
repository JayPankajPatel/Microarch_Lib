---
status: accepted
date: 2026-08-16
---

# 0010. `.sby` files use repo-root-relative `[files]` paths and a dedicated `pixi run formal` task that redirects all run output to `/build/`

## Context and Problem Statement

SymbiYosys resolves relative paths in a `.sby` file's `[files]` section
against the **process's current working directory at invocation time**, not
against the `.sby` file's own location. The first working version of
`galois_lfsr.sby` used paths hand-counted relative to
`blocks/stocastic/verif/formal/` (e.g. `../../rtl/galois_lfsr.sv`,
`../../../../common/rtl/ma_assert.svh`), which only resolves correctly if
`sby` happens to be invoked from exactly that directory.

This broke in practice: while experimenting with the file, `sby -f *.sby`
was run from a nested subdirectory
(`verif/formal/test_galois_lfsr/galois_lfsr_w4/`, itself containing a
leftover `config.sby` copy from an earlier SBY run), and the hand-counted
`../../` paths resolved to nonexistent locations, producing a
`FileNotFoundError` instead of a useful error. Nothing about the `.sby`
file itself was wrong -- the invocation directory was just different than
assumed.

A second, related problem surfaced once the block layout moved to one
directory per module under `verif/formal/` (`verif/formal/<module>/`, with
the module's `.sby` file inside it -- chosen over a flat `verif/formal/`
directory so multiple modules' formal setups don't collide as more blocks
grow formal properties): SBY's default workdir naming
(`<sby-basename>_<taskname>`, created as a *sibling* of the `.sby` file)
means every `sby` run leaves generated directories inside the same
tracked-source directory as the `.sby` file itself. A `.gitignore` pattern
trying to exclude these by directory depth or name
(`blocks/*/verif/formal/*/`) is unreliable here specifically because module
directory names in this repo routinely contain underscores
(`galois_lfsr`, `binary_stochastic_converter`), making a generated workdir
name (`galois_lfsr_w4`) structurally indistinguishable from a legitimate
module directory name by a simple glob.

## Decision Drivers

- This repo already depends on `bender` (`Bender.yml`/`Bender.lock`
  tracked) specifically to avoid this class of hand-maintained,
  invocation-order-sensitive path bookkeeping -- `pixi.toml`'s existing
  `lint`/`lint-all` tasks already use `bender script flist-plus` plus a
  `cd "$PIXI_PROJECT_ROOT"` pattern for exactly this reason, and this
  should follow the same established convention rather than inventing a
  new one.
- The fix needs to survive being invoked from *any* directory, not just
  fix the one specific broken case, since formal verification during
  active development is run from wherever the user happens to be working.

## Considered Options

1. Hand-count the correct number of `../` segments for the *current*
   known invocation directory (`verif/formal/`) and document "always cd
   here first."
2. Make `[files]` paths repo-root-relative (matching
   `bender script flist-plus --relative-path` output, confirmed to always
   anchor to `Bender.yml`'s directory regardless of invocation cwd) and add
   a `pixi run formal <path-to-sby>` task that forces `sby`'s actual
   working directory to `$PIXI_PROJECT_ROOT` before running, mirroring the
   existing `lint`/`lint-all` tasks.
3. Use absolute paths generated once via `bender script flist-plus` (no
   `--relative-path`) and hardcode them into the checked-in `.sby` file.

For the workdir-location problem specifically:

4. Pattern-match generated workdirs in `.gitignore` by directory depth
   under `verif/formal/`.
5. Use `sby`'s `--prefix <dirname>` flag (workdir becomes
   `<dirname>_<taskname>`) to redirect every task's output to one common,
   top-level location outside `blocks/` entirely, gitignored once.

## Decision Outcome

Chosen option: **2**. Option 1 was already tried and is exactly what broke
-- it only relocates the fragility, it doesn't remove it, and "remember to
cd to this exact directory" is not a real fix for a file other people (and
future sessions) will invoke from wherever they happen to be. Option 3 was
rejected because `bender`'s absolute-path output is anchored to the
clone's filesystem location on the machine it was run on
(`/home/jay/Repos/Microarch_Lib/...` here) -- hardcoding that into a
checked-in file would break on every other clone/machine.

`bender script flist-plus --relative-path`, run from both the repo root and
a nested subdirectory, was confirmed to produce the identical
repo-root-relative output in both cases (`+incdir+common/rtl`,
`blocks/stocastic/rtl/galois_lfsr.sv`, etc.) -- it doesn't need special
invocation-directory handling itself, because it resolves against
`Bender.yml`'s location, not the caller's cwd. `galois_lfsr.sby`'s
`[files]` section adopts that same repo-root anchor
(`blocks/stocastic/rtl/galois_lfsr.sv`, `common/rtl/ma_assert.svh`, etc.,
no `../` climbing at all), and the new `pixi run formal` task guarantees
`sby` is always actually invoked from that anchor point, regardless of
where the user's shell currently is -- by resolving the given `.sby` path
against `$INIT_CWD` (pixi's variable for the directory `pixi run` was
launched from) into a `$PIXI_PROJECT_ROOT`-relative path, then `cd`-ing
there before running `sby`.

For the workdir location, chosen: **5, `--prefix`**, over 4
(`.gitignore` pattern-matching), for the reason given above -- module
directory names containing underscores make directory-name/depth-based
`.gitignore` patterns genuinely ambiguous, not just verbose, since a
pattern broad enough to catch every generated workdir shape also catches
legitimate module directories (e.g. `galois_lfsr/` itself, which contains
an underscore) and would hide any new tracked file later added inside one
from `git add -A` without any error or warning. `--prefix` sidesteps the
ambiguity entirely by never creating the workdir inside `blocks/` in the
first place: `pixi run formal` passes
`--prefix "build/formal/$(basename <sby-file> .sby)"`, so every task's
workdir lands under a single top-level `/build/` directory (one `.gitignore`
line covers it, unconditionally, regardless of how deeply nested any
module's `verif/formal/` directory becomes in the future).

A related simplification to the same `[files]` section: SBY's `[files]`
entries can name a directory, not just individual files -- confirmed by
reading `copy_src()` in `sby_core.py`, which calls `copytree()` when the
source path is a directory. `common/rtl`'s three headers
(`ma_assert.svh`, `ma_assert_dummy.svh`, `ma_assert_std.svh`) were
originally listed one per line; that's replaced with a single
`common/rtl common/rtl` entry (copy the whole directory), plus `-Icommon/rtl`
added to the `read_verilog` line in `[script]` since the headers now land in
a subdirectory of the sandbox rather than flat alongside `galois_lfsr.sv`.
This isn't "bender inline" (SBY's `[files]`/`[script]` sections are static
declarative config with no subprocess/command-substitution support at all,
confirmed by reading the parser -- `os.path.expandvars` is the only
dynamic behavior it has), but it removes the same class of hand-maintenance
risk bender is used elsewhere in this repo to avoid: any header added to
`common/rtl` in the future is picked up automatically, with nothing in the
`.sby` file to remember to update.

### Consequences

- Running formal verification is now always
  `pixi run formal <path-to-the.sby-file>`, from any directory, rather
  than `sby -f galois_lfsr.sby` from one specific expected directory.
- The `.sby` file's `[files]` section is no longer directly runnable via a
  bare `sby -f galois_lfsr.sby` unless invoked from the repo root
  specifically -- this is an intentional, documented tradeoff (one correct
  anchor point via a task, instead of an implicit "run from here" convention
  that isn't enforced by anything).
- `verif/formal/<module>/` directories (here, `verif/formal/test_galois_lfsr/`,
  the module-per-directory naming already in use for this block) now only
  ever contain the tracked `.sby` file itself -- every run's generated
  output goes to `/build/formal/`, never as a sibling of the `.sby` file, so
  there's nothing generated to accidentally commit or need to `.gitignore`
  per-module.
- Any future `.sby` file in this repo should follow the same pattern
  (repo-root-relative `[files]`, run via `pixi run formal`) rather than
  reintroducing hand-counted relative paths or bare `sby -f` invocations.

### Confirmation

- Ran `pixi run formal blocks/stocastic/verif/formal/test_galois_lfsr/galois_lfsr.sby`
  from the repo root: all three tasks (`w4`, `w19`, `w64`) report
  `DONE (PASS, rc=0)`, with generated output under
  `build/formal/galois_lfsr_{w4,w19,w64}/`.
- Reproduced the exact failure scenario -- ran the same task with a
  relative `.sby` path from inside a directory nested even deeper than the
  one that originally broke: all three tasks again report
  `DONE (PASS, rc=0)`, confirming the fix is actually
  invocation-directory-independent and not just re-fixed for one specific
  case.
- Confirmed via `git status --short` after a full run that no generated
  file or directory appears anywhere under `blocks/` -- only the tracked
  `.sby` file itself shows as modified.

## Affected Files

- `blocks/stocastic/verif/formal/test_galois_lfsr/galois_lfsr.sby`
  (`[files]` section changed from `verif/formal/`-relative `../` paths to
  repo-root-relative paths; moved into the per-module
  `verif/formal/test_galois_lfsr/` directory)
- `pixi.toml` (new `formal` task, alongside the existing `lint`/`lint-all`
  tasks that already establish the `$PIXI_PROJECT_ROOT`/`$INIT_CWD`
  pattern this follows; passes `--prefix build/formal/<basename>` to `sby`)
- `.gitignore` (`/build/` replaces the earlier, narrower
  `blocks/*/verif/formal/*/` pattern)

## More Information

See [0009](0009-formal-checker-inline-not-bind.md) for the separate
decision about how the `no_lockup` property itself is expressed (inline
`` `ifdef FORMAL ``, not `bind`), found and fixed in the same overall effort
to stand up this formal flow.
