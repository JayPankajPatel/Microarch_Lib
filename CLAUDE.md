# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`Microarch_Lib` is a SystemVerilog hardware IP library headed toward both ASIC tapeout and a custom FPGA fabric (a stochastic-computing MAC unit). Because it's tapeout-bound, prefer proven/verified patterns over newer-but-less-supported language features, and treat elaboration-time correctness checks and lint gates as required, not optional.

## Toolchain setup

Tools (Verilator, Yosys, SymbiYosys, z3) are managed via `pixi`, not assumed to be pre-installed:

```bash
pixi install        # verilator, yosys, libz3 (bundles the real `z3` CLI, not just the library), click
pixi run setup-sby   # one-time: builds SymbiYosys (`sby`) from source into the pixi env -- it isn't on conda-forge
```

Supported platforms are `linux-64` and `osx-64` only — Yosys's conda-forge feedstock has no builds for `osx-arm64` or `linux-aarch64` (see `docs/adr/0003-pixi-toolchain.md`).

## Linting

```bash
pixi run verilator --lint-only -Wall -Icommon/rtl blocks/<name>/rtl/<file>.sv
```

Run RTL lint explicitly when it is useful; RTL lint is intentionally not a
pre-commit hook, so a broken or incomplete project-wide source manifest cannot
block unrelated commits.

Python verification code has pre-commit hooks (ruff check/format and ty, run
from the pixi lockfile; ADR 0026). Install once per clone with
`pixi run setup-hooks`. `pixi run lint-py` checks, `pixi run fix-py` auto-fixes
lint and formatting (ty errors must be fixed by hand).

## Architecture

### Block layout convention

Every block lives under `blocks/<name>/` with a fixed shape, established from the very first block even though most of it is still empty for that block:

```
blocks/<name>/
  rtl/                  -- synthesizable SystemVerilog
  docs/
    waveforms/           -- wavedrom JSON timing-diagram sources, plus their rendered .svg (both committed -- .svg regenerated via `pixi run render-waveform <path/to/diagram.json>` after editing the .json)
  verif/
    formal/             -- one test_<name>/ dir per proof: a .sby (read_slang -D FORMAL, ADR 0024) plus, for blocks using reusable checkers, a <name>_bind.sv that binds common/verif/sva/ checkers and the reset-at-step-0 assume via `MA_ASSUME_RESET_AT_START` (ADR 0025)
    tb/                 -- cocotb testbenches, one directory per test (test_<name>/)
```

`common/` (sibling to `blocks/`, not nested inside it) holds cross-cutting infrastructure: `common/rtl/` has the elaboration-check macros (`ma_assert*.svh`), the AXI-Stream struct typedef macros (`ma_axis_typedef.svh`, ADR 0023) and the concurrent SVA wrappers (`ma_sva.svh`, ADR 0025); `common/verif/sva/` has reusable protocol checkers (e.g. `ma_axis_checker.sv`); `common/verif/*.py` has shared cocotb helpers.

### Formal properties live outside the RTL

Design RTL contains no verification code. Reusable/protocol checkers live in `common/verif/sva/` and attach to a block via `bind` from `blocks/<name>/verif/formal/test_<name>/<name>_bind.sv`; those files are only in the Bender `formal` target, never in the synthesis file list. Each `.sby` keeps `select -assert-min 1 t:$check` plus a per-instance `select -assert-count N t:$check */u_<port>_chk.* %i` guard, because a missing bind file is otherwise silent. Yosys's slang frontend lowers only boolean property bodies plus `$past` -- no `|->`, `|=>`, `##N`, sequences or `$stable` -- so write each rule as "if X last cycle then Y now" with `$past(rst_n && X)` (the `rst_n` mirrors `disable iff`). Designer assertions about a block's own internals (e.g. `galois_lfsr`'s `no_lockup`) may stay inline under `` `ifdef FORMAL ``. See `docs/adr/0025-assertions-outside-rtl-sva-header-and-bind.md`.

### Elaboration-time parameter checks

`common/rtl/ma_assert.svh` is a tool-dispatch header: it `` `include ``s either `ma_assert_std.svh` (real macro bodies) or `ma_assert_dummy.svh` (same macro names, no-op bodies) depending on `` `ifdef SYNTHESIS ``/`` `ifdef YOSYS ``. Every block that needs a parameter-range check (or similar) should `` `include "ma_assert.svh" `` and call `` `MA_ASSERT_ELABOR(name, condition) `` rather than hand-rolling an `if`/`$error`. See `blocks/stochastic/rtl/galois_lfsr.sv` for the reference usage, and `docs/adr/0001-elaboration-check-mechanism.md` for why this specific form was chosen over the alternatives (SVA, the `checker` construct, OpenTitan's `` `ASSERT_INIT `` pattern).

### FSM-shaped RTL uses the Gaisler two-process style

Any module with more than a couple of pieces of interacting registered state (i.e. it's naturally an FSM, not just a counter or a single-register datapath) must be written in the Gaisler two-process style, not as a single `always_ff` with several separately-declared registers conditionally assigned across nested branches: collect all registered state into one `r`/`rin` packed struct pair, compute `rin` entirely in one `always_comb` block that starts with `rin = r;` (hold everything) before conditionally overriding only the fields that change, and use a single `always_ff` block that does nothing but the reset assignment and `r <= rin;`. See `blocks/stochastic/rtl/binary_stochastic_converter.sv` for the reference usage, and `docs/adr/0007-gaisler-two-process-fsm-style.md` for the two concrete bugs (an output that silently held for only one cycle instead of the whole burst, and an unreachable termination condition) this convention exists to prevent. Don't apply this structure to modules that don't need it — `counter.sv` and `galois_lfsr.sv` are intentionally left as plain single-register `always_ff` blocks, since the struct/two-process split would add ceremony without a corresponding clarity gain there.

### Design rationale lives in `docs/adr/`, not in commit messages or comments

Before assuming *why* a module is structured a certain way, check `docs/adr/README.md` first — it's an index of Architecture Decision Records (MADR-based: context, alternatives considered, what was chosen and why, and how it was verified). This is the authoritative source for design rationale in this repo; code comments intentionally stay terse. `docs/design-specs/` holds the planning documents that produced the ADRs, for deeper background if an ADR references one.

When making a new non-obvious design decision, add an ADR (`docs/adr/NNNN-<slug>.md`, next sequential number, same template) rather than leaving the reasoning only in conversation history.

**Before committing**, check the staged diff for exactly this: does it embody a decision someone would reasonably ask "why did you do it this way?" about (a chosen mechanism over rejected alternatives, a non-obvious tradeoff, a correctness methodology) — not just a bug fix or mechanical change? If so, write the ADR in the same commit (or the one right before it), not after. A decision made and committed without its ADR tends to never get one.

## Before opening a PR or merging to `main`

When the user asks to open a PR or merge, remind them of this checklist first, and don't treat it as done until each item is confirmed:

1. **README "AI-Assisted Development" section**: every `<...>` placeholder is replaced with accurate details, and the `TODO(before PR/merge)` comment is removed.
2. `pixi run lint-all`, `pixi run run-regression`, and `pixi run run-formal` all pass.
3. Any ADR still marked `proposed` either has its Confirmation filled in with real evidence or intentionally stays proposed.
