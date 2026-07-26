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

A pre-commit hook runs this automatically on every staged `blocks/*/rtl/*.sv` file. It's not active by default per clone — enable it once with:

```bash
git config core.hooksPath .githooks
```

## Architecture

### Block layout convention

Every block lives under `blocks/<name>/` with a fixed shape, established from the very first block even though most of it is still empty for that block:

```
blocks/<name>/
  rtl/                  -- synthesizable SystemVerilog
  verif/
    formal/             -- SymbiYosys .sby files + bind checkers
    sim/                -- testbenches
```

`common/` (sibling to `blocks/`, not nested inside it) holds cross-cutting infrastructure that every block depends on — currently just the elaboration-check macros.

### Elaboration-time parameter checks

`common/rtl/ma_assert.svh` is a tool-dispatch header: it `` `include ``s either `ma_assert_std.svh` (real macro bodies) or `ma_assert_dummy.svh` (same macro names, no-op bodies) depending on `` `ifdef SYNTHESIS ``/`` `ifdef YOSYS ``. Every block that needs a parameter-range check (or similar) should `` `include "ma_assert.svh" `` and call `` `MA_ASSERT_INIT(name, condition) `` rather than hand-rolling an `if`/`$error`. See `blocks/stocastic/rtl/galois_lfsr.sv` for the reference usage, and `docs/adr/0001-elaboration-check-mechanism.md` for why this specific form was chosen over the alternatives (SVA, the `checker` construct, OpenTitan's `` `ASSERT_INIT `` pattern).

### Design rationale lives in `docs/adr/`, not in commit messages or comments

Before assuming *why* a module is structured a certain way, check `docs/adr/README.md` first — it's an index of Architecture Decision Records (MADR-based: context, alternatives considered, what was chosen and why, and how it was verified). This is the authoritative source for design rationale in this repo; code comments intentionally stay terse. `docs/design-specs/` holds the planning documents that produced the ADRs, for deeper background if an ADR references one.

When making a new non-obvious design decision, add an ADR (`docs/adr/NNNN-<slug>.md`, next sequential number, same template) rather than leaving the reasoning only in conversation history.

**Before committing**, check the staged diff for exactly this: does it embody a decision someone would reasonably ask "why did you do it this way?" about (a chosen mechanism over rejected alternatives, a non-obvious tradeoff, a correctness methodology) — not just a bug fix or mechanical change? If so, write the ADR in the same commit (or the one right before it), not after. A decision made and committed without its ADR tends to never get one.
