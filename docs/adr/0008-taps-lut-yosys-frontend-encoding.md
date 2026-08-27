---
status: accepted
date: 2026-08-16
---

# 0008. `TAPS_LUT` is encoded as a constant function, not a `localparam` array, so it parses under Yosys's native frontend

## Context and Problem Statement

Standing up a working SymbiYosys formal flow for `galois_lfsr.sv`
(`blocks/stocastic/verif/formal/galois_lfsr.sby`) requires Yosys's native
Verilog/SystemVerilog frontend (`read_verilog -sv`) to parse the module --
there is no Verific/Slang frontend available in this repo's pixi-managed
toolchain, and Yosys's own docs describe frontend SV support as "only a
small subset."

`TAPS_LUT`, added by ADR 0002, is declared as
`localparam bit [63:0] TAPS_LUT[0:64] = '{0: 64'h0, 1: 64'h0, ...};` -- an
unpacked array with an indexed assignment-pattern initializer. This
construct is rejected outright by Yosys's frontend:
`ERROR: syntax error, unexpected '[', expecting ',' or ';' or '='` at the
declaration line, confirmed against both the pixi-pinned Yosys 0.67 build
and oss-cad-suite's bundled Yosys. Stubbing the array out (replacing it
with a single scalar `localparam`) confirmed every other construct in the
file -- the `WIDTH'(1)` parameter-default cast, the `for` loop inside
`always_ff`, `endmodule : galois_lfsr` -- parses cleanly; the array
declaration syntax is the only blocker.

## Decision Drivers

- The formal flow needs the real RTL to elaborate, not a stand-in; the fix
  has to preserve `TAPS_LUT`'s actual per-`WIDTH` values exactly, or it
  silently invalidates every primitivity result ADR 0002/0005/0006
  established.
- CLAUDE.md's Gaisler-style-FSM and general "prefer proven patterns"
  guidance for a tapeout-bound repo argues against hand-rolling a
  workaround (e.g. a flattened packed 2D array with bit-slicing arithmetic)
  when a more standard, more readable form is available.

## Considered Options

1. Flatten to a packed 2D array (`bit [64:0][63:0] TAPS_LUT`) with a
   concatenation-based initializer instead of an indexed assignment
   pattern.
2. Re-encode as `function automatic bit [63:0] taps(int n); case (n) ...
   endcase endfunction`, called as `taps(n)` wherever `TAPS_LUT[n]` was used.
3. Keep `TAPS_LUT` as-is and give up on running this file through Yosys's
   native frontend (e.g. restrict formal verification to a different,
   Verific-backed toolchain not currently in this repo).

## Decision Outcome

Chosen option: **2, constant function with a `case` statement**, because it
was confirmed to parse under Yosys's frontend, and it preserves the
existing table's readability (one line per width, inline comments intact)
far better than option 1's flattened-concatenation form would. Option 3
was rejected because it abandons the actual goal (a working formal flow
using the toolchain already established by ADR 0003) rather than solving
the parser incompatibility.

`function automatic` was specifically checked against the concern that
`automatic` implies a hardware call stack: it does not. `automatic` only
governs *simulation* local-variable storage (per-call instead of shared
across calls); with no recursion and a compile-time-constant call argument
(`n = WIDTH`, a `localparam`), synthesis inlines the function at its call
site and this collapses to pure constant folding -- functionally identical
to the `localparam` array it replaces, just expressed as a `case` instead
of an indexed literal.

A second, related parser limit was found while wiring this in: a bit-select
directly on a function call's return value (`taps(n)[n-1-i]`) also fails to
parse (`ERROR: syntax error, unexpected '['`). The call is instead
precomputed into a new `localparam bit [63:0] tap_mask = taps(n);`, and the
existing per-cycle logic bit-selects `tap_mask[n-1-i]` instead -- this also
avoids re-evaluating `taps(n)` on every iteration of the tap-application
loop, which the array form did too (`TAPS_LUT[n]` was similarly hoisted
implicitly by being a plain array read).

### Consequences

- `galois_lfsr.sv` now elaborates under `read_verilog -sv` (confirmed: 6
  cells for the `WIDTH=4` default -- 1 `$adff`, 4 `$mux`, 1 `$xor` -- with
  `CHECK` reporting 0 problems), unblocking
  `blocks/stocastic/verif/formal/galois_lfsr.sby`.
- The table's per-width structure and inline "which taps" comments are
  unchanged in spirit -- same 65 entries, same comments, just `N: taps =
  VAL;` instead of `N: VAL,`.
- No change to simulation or synthesis behavior for any existing
  non-formal flow (Verilator, or any future synthesis run) -- `function
  automatic` with a `case` and a constant argument is standard,
  well-supported SystemVerilog everywhere else already in use.

### Confirmation

- **Bit-exact equivalence**: extracted the pre-edit `TAPS_LUT` array and the
  post-edit `taps()` function into one Verilator testbench and compared all
  65 entries (`w` = 0 through 64) with `!==`: `ALL 65 ENTRIES MATCH`, zero
  mismatches.
- **Yosys elaboration**: `read_verilog -sv -Icommon/rtl
  blocks/stocastic/rtl/galois_lfsr.sv; prep -top galois_lfsr` completes with
  `CHECK pass ... Found and reported 0 problems` (previously a hard parse
  error at the `TAPS_LUT` declaration line).
- **Functional re-verification at `WIDTH=19`**, matching the standard ADR
  0002/0005 already established for this width: ran the edited RTL through
  Verilator with a corrected async-reset sequencing (`#12 rst_n = 1;`,
  independent of the clock edge) and counted unique `out` values until
  repeat -- **524287** cycles, exactly `2^19 - 1`, matching ADR 0005's
  previously-confirmed result for the same width and seed.
- Standard `pixi run verilator --lint-only -Wall -Icommon/rtl
  blocks/stocastic/rtl/galois_lfsr.sv` produces only the two pre-existing
  `GENUNNAMED` warnings from the unrelated `MA_ASSERT_INIT` generate blocks
  (confirmed identical before/after via `git stash`) -- no new warnings from
  this change.

## Affected Files

- `blocks/stocastic/rtl/galois_lfsr.sv` (`TAPS_LUT` localparam array
  replaced by `function automatic bit [63:0] taps(int n)`; new `tap_mask`
  localparam hoists the per-instance constant call result; tap-application
  loop reads `tap_mask[n-1-i]` instead of `TAPS_LUT[n][n-1-i]`)

## More Information

See [0002](0002-taps-lut-correctness-methodology.md) for how the table's
values were originally derived and verified, and
[0006](0006-galois-lfsr-tap-mirroring.md) for why the mirrored index
(`[n-1-i]`, not `[i]`) is needed -- neither is affected by this encoding
change. See [0009](0009-formal-checker-inline-not-bind.md) for the related
Yosys-frontend-compatibility decision this same formal-flow effort
surfaced, about how the `no_lockup` property itself is expressed.
