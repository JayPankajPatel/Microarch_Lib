---
status: Accepted
date: 2026-09-06
---

# 0020. Parallel `_sync` RTL variants for targets whose flip-flop has no async reset

## Context and Problem Statement

Mapping the stochastic-computing chain onto the FABulous-based FPGA fabric
(`Tracked_FPGA_experiments`) hit a hard block: `synth_fabulous`'s
`DFFLEGALIZE` pass rejected the design with `dffs with async set or reset
are not supported`. Reading the fabric's actual FF BEL source
(`Tile/LUT4AB/LUT4c_frame_config_dffesr.v`) confirmed this isn't a synthesis
option to enable — the BEL's `SR` reset input is sampled inside the clocked
`always @(posedge UserCLK)` block, not in the sensitivity list. This fabric
tile genuinely has no async-reset FF primitive; every register this repo's
RTL maps onto it must use a purely synchronous reset.

Every sequential module in this library (`counter`, `galois_lfsr`,
`binary_stochastic_converter`, `stochastic_to_binary`) is written with
`always_ff @(posedge clk or negedge rst_n)` — async reset — matching this
repo's ASIC-tapeout-first orientation (see top-level `CLAUDE.md`). That
style is correct and required for the ASIC target; it is simply unsupported
by this specific FPGA fabric's FF BEL.

## Considered Options

1. Convert every module's reset style in place to synchronous, dropping
   async reset entirely from the library.
2. Add a build-time macro/`ifdef` that switches one module's sensitivity
   list between async and sync forms depending on target.
3. Add parallel `_sync`-suffixed files: exact duplicates of each async
   module except for the reset style, kept alongside the originals.

## Decision Outcome

Chosen option: **3**.

- **Option 1** would regress the verified ASIC-target default for every
  existing/future tapeout use, to serve one FPGA fabric's limitation. This
  repo is explicitly ASIC-tapeout-first (`CLAUDE.md`); async reset is the
  correct choice there and shouldn't be removed for a target that is
  presently experimental.
- **Option 2** avoids duplicating files but pushes a `` `ifdef ``-selected
  sensitivity list into every sequential module permanently, mixing two
  reset disciplines behind a flag in files that are otherwise this repo's
  most scrutinized (formally verified, hardened to GDSII). The existing
  `ma_assert.svh` tool-dispatch macro already sets precedent for *parameter
  checks* being conditionally compiled; reset topology is a structural
  property of the register itself, not a check, and is easy to get subtly
  wrong under a shared macro (e.g. accidentally leaving `or negedge rst_n`
  in the sensitivity list while also gating on it synchronously elsewhere).
- **Option 3 (chosen)**: each `_sync` file is a mechanical, minimal-diff
  copy of its async original — same logic, same parameters, same port
  list, only the `always_ff` sensitivity list changes (drop
  `or negedge rst_n`) and any internal submodule instantiations are
  re-pointed at the corresponding `_sync` submodule. This keeps the
  async-reset originals untouched (still the default for every existing
  test, ADR, and hardening run) while giving the fabric target a
  drop-in-verified alternative. The duplication cost is small and bounded
  (five files) and each pair is easy to diff against its original to
  confirm nothing beyond reset style changed.

### Which modules got a `_sync` variant

- `blocks/basic/counter_sync.sv`
- `blocks/stocastic/rtl/galois_lfsr_sync.sv`
- `blocks/stocastic/rtl/binary_stochastic_converter_sync.sv` (instantiates
  `counter_sync`/`galois_lfsr_sync`)
- `blocks/stocastic/rtl/stochastic_binary_converter_sync.sv`, module
  `stochastic_to_binary_sync`
- `blocks/stocastic/rtl/stochastic_adder_sync.sv` (instantiates
  `galois_lfsr_sync` for its select RNG)

`stochastic_multipler.sv` deliberately got **no** `_sync` variant: per ADR
0012 it's pure combinational (AND-gate join), has no `always_ff` of its
own, so the exact same file is reset-style-agnostic and works unmodified
under either target.

### Confirmation

Lint alone doesn't prove behavioral equivalence, so each `_sync` module was
run through its **existing, already-verified cocotb test suite** (same
golden models and mutation-tested assertions used for the async original),
with `COCOTB_TOPLEVEL` pointed at the `_sync` module name instead of
writing new tests:

- `pixi run verilator --lint-only -Wall -Icommon/rtl` on all five new files
  (grouped by dependency): clean except for pre-existing warning classes
  already present for the async originals (`GENUNNAMED` from
  `MA_ASSERT_ELABOR`'s generate block; `DECLFILENAME` for the decoder's
  filename/module-name mismatch, which the async original also has) — zero
  new warnings.
- `test_binary_to_stochastic` against `binary_stochastic_converter_sync`:
  4/4 passing.
- `test_stochastic_to_binary` against `stochastic_to_binary_sync`: 4/4
  passing.
- `test_stochastic_adder` against `stochastic_adder_sync`: 5/5 passing,
  including the statistical `scaled_sum_statistical_property` test —
  confirms `galois_lfsr_sync`'s decorrelation behavior over a real N=2^16+
  run matches the async LFSR's.
- `test_galois_lfsr` against `galois_lfsr_sync` directly: 2/2 passing,
  including `reaches_maximal_length_cycle` (all 15 nonzero WIDTH=4 states
  visited before repeating) and the `pylfsr` golden-model match.
- No dedicated standalone test exists for `counter`/`counter_sync`; it is
  exercised indirectly through the encoder test above, which passed.

15/15 reused test cases pass identically against the `_sync` variants with
zero test-file changes — only `COCOTB_TOPLEVEL` was overridden.

### Consequences

- The async-reset originals remain the unqualified default for ASIC/tapeout
  work and every existing GDSII hardening run; nothing about them changed.
- The `_sync` files are now available to compose a sync-reset fabric
  integration top (e.g. a `sc_multiply_chain_top_sync`) for the FABulous
  mapping attempt, unblocking the `DFFLEGALIZE` failure.
- Two parallel copies of core library logic now exist and must be kept in
  sync by hand if the async originals' *combinational* logic ever changes
  (the reset-style diff is the only intentional divergence). This is an
  accepted maintenance cost for a small, stable set of modules; if the
  fabric-mapping effort grows to need many more modules mirrored this way,
  revisit option 2.

## Affected Files

- `blocks/basic/counter_sync.sv` (new)
- `blocks/stocastic/rtl/galois_lfsr_sync.sv` (new)
- `blocks/stocastic/rtl/binary_stochastic_converter_sync.sv` (new)
- `blocks/stocastic/rtl/stochastic_binary_converter_sync.sv` (new)
- `blocks/stocastic/rtl/stochastic_adder_sync.sv` (new)

## More Information

Prompted by `~/wiki/fpga_stochastic_blocks/reusable_lessons/fabric-ff-primitive-sync-reset-only.md`,
which documents the fabric BEL finding in full (exact `LUT4c_frame_config_dffesr.v`
excerpt, options considered, commands to check any other fabric's FF BEL the
same way). That doc and the fabric-mapping decision log
(`~/wiki/fpga_stochastic_blocks/decision_logs/stochastic-v0-evidence-and-v1-candidate-2026-09-06.md`)
are the authoritative record of *why* fabric mapping needed this; this ADR
is the authoritative record of *how* the library responded.
