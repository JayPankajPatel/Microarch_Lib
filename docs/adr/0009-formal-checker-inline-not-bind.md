---
status: accepted
date: 2026-08-16
---

# 0009. The `galois_lfsr` `no_lockup` formal property is an inline `` `ifdef FORMAL `` assertion, not a `bind`-ed checker module

## Context and Problem Statement

`blocks/stocastic/verif/formal/galois_lfsr.sby` needed a way to express one
formal property against `galois_lfsr`: `out` never becomes all-zero once
reset deasserts (`no_lockup`), given `NoZeroSeed` guarantees a nonzero
`INIT_SEED`. The initial approach was a separate checker module in
`verif/formal/`, wired to the DUT via SystemVerilog's `bind` construct, to
keep the formal-only assertion completely out of `galois_lfsr.sv` itself.

That approach silently doesn't work under Yosys's native frontend. A
`bind galois_lfsr galois_lfsr_checker chk(.*);` statement, and an
`assert property (...)` inside the bound module, both **parse without
error** -- but after `prep -top galois_lfsr`, `stat` shows zero
`$check`/`$assert` cells in the elaborated design. The bound instance is
dropped during hierarchy elaboration, not rejected at parse time, which
means an `.sby` file built this way would report `PASS` unconditionally
with no property actually being checked -- confirmed directly: flipping the
bound property to its logical negation (`out == '0`, which should fail
every time) still reported `PASS`, because there was no assertion left in
the model to fail.

A second, separate issue was found in the same investigation:
`assert property (@(posedge clk) disable iff (!rst_n) out != '0);` --
ordinary SVA concurrent-assertion syntax with an embedded clocking event --
does not parse at all under this frontend
(`ERROR: syntax error, unexpected '@'`), independent of whether it's inside
a bound module or not.

## Decision Drivers

- A formal check that silently checks nothing is worse than no formal check
  at all -- it would report green while giving zero actual guarantee, which
  directly contradicts the tapeout-bound "elaboration-time correctness
  checks... are required, not optional" posture from CLAUDE.md.
- CLAUDE.md's precedent for `` `ifdef ``-gated tool-specific behavior already
  exists in this exact file, one macro up: `MA_ASSERT_INIT` dispatches on
  `` `ifdef SYNTHESIS ``/`` `elsif YOSYS `` (see ADR 0001). Reusing that same
  shape for a formal-only assertion is a smaller, more consistent change
  than introducing a new formal-checker convention.

## Considered Options

1. Keep pursuing `bind`, e.g. investigating Yosys flags or a different
   elaboration order to make the bound instance survive `prep`.
2. Inline the assertion directly in `galois_lfsr.sv`, guarded by
   `` `ifdef FORMAL ``, using the immediate-assertion form
   (`always @(posedge clk) if (rst_n) assert (...)`) confirmed to parse and
   elaborate to a real `$check` cell.
3. Write a non-`bind` formal-only wrapper module that instantiates
   `galois_lfsr` directly (rather than the DUT being the top module) and
   puts the assertion in the wrapper.

## Decision Outcome

Chosen option: **2, inline `` `ifdef FORMAL `` assertion**, because it's the
only option confirmed both to parse and to actually elaborate into the
model (verified via a real `FAIL` on a deliberately-wrong property, not
just absence of a parse error). Option 1 was not pursued further after
confirming the drop is a hierarchy-elaboration behavior, not a flag/ordering
issue that a quick retry would fix -- Yosys's `bind` support is understood
to target its (separate, not present in this repo's toolchain) `read_slang`
frontend rather than the native one. Option 3 was rejected as unnecessary
complexity: it solves the same problem as option 2 (get an assertion into
the elaborated hierarchy) with an extra file and extra indirection, for no
benefit once `bind` itself is off the table -- `galois_lfsr` is a leaf
module, not something that needs an unmodified top-level wrapper for other
reasons.

A related fix was needed alongside the syntax change: the property also
required an explicit `initial assume (!rst_n);` inside the same
`` `ifdef FORMAL `` block. Without it, the BMC base case is free to start
from an arbitrary, unconstrained `q` (including `q == '0`), which fails
`no_lockup` immediately with a counterexample that reflects an impossible
starting state, not a real design bug -- confirmed by adding the assumption
and watching the same failing base case turn into a genuine `pass`, then
re-confirming the negation still correctly fails with the assumption in
place.

### Consequences

- The `no_lockup` property now lives in `galois_lfsr.sv` itself rather than
  a separate `verif/formal/` file, inside `` `ifdef FORMAL ``, so it has zero
  effect on synthesis (`` `ifdef SYNTHESIS ``) or any tool that doesn't
  define `FORMAL` (plain simulation, lint).
  `blocks/stocastic/verif/formal/galois_lfsr_bind.sv` was deleted -- it
  never actually checked anything, so keeping it around as source would be
  misleading.
- Future formal properties on other blocks in this repo should follow the
  same inline `` `ifdef FORMAL `` pattern rather than `bind`, given the
  demonstrated frontend limitation, unless the toolchain later gains a
  frontend where `bind` is confirmed (not just parses without error) to
  elaborate correctly.
- `galois_lfsr.sby`'s `[script]` uses `read_verilog -sv -formal`
  (not plain `-sv`) so `` `FORMAL `` is defined, enabling this block; Yosys's
  `read_verilog` always defines `` `YOSYS `` regardless, so `MA_ASSERT_INIT`
  still correctly strips to its no-op dummy body per ADR 0001 during the
  formal run.

### Confirmation

- **Multiple widths, not just the `WIDTH=4` default**: `galois_lfsr.sby`
  defines three tasks (`w4`, `w19`, `w64`) using `chparam -set WIDTH ...
  -set INIT_SEED 1` for the non-default ones. `WIDTH=4` alone would only
  exercise one of the 63 distinct tap masks in the table (and one ADR 0002
  never needed to correct); `WIDTH=19` was chosen because it has
  independent Verilator cycle-length evidence (524287, see ADR 0008) to
  cross-check against, and `WIDTH=64` because it has the largest tap-count
  gap of any width (ADR 0005). All three pass at `depth 20` with no
  induction-depth issues.
- **Negative-case check across all three tasks, both before and after the
  reset-assumption fix**: temporarily flipped `no_lockup`'s condition to
  `out == '0` (the logical negation, which should fail on essentially every
  reachable cycle) and reran `sby`. Before the reset assumption existed,
  this flip's `FAIL` outcome was indistinguishable from a real bug (both
  were failures with counterexamples), which is why the assumption's
  necessity was caught in the first place: the *unflipped* property was
  also failing without it. After adding `initial assume (!rst_n);`, all
  three unflipped tasks pass (`successful proof by k-induction`) and all
  three flipped-negation tasks fail with a counterexample trace (`failed
  assertion galois_lfsr.no_lockup ... step 2`) -- the expected result in
  both directions, confirming the checker is load-bearing rather than
  vacuous, and that this holds across widths, not just the one tested.
- **`$check` cell presence**: `read_verilog -sv -formal -Icommon/rtl
  blocks/stocastic/rtl/galois_lfsr.sv; prep -top galois_lfsr; stat` shows
  `1 $check` cell in the final design (it showed zero when the same
  assertion lived in a `bind`-ed module instead).
- **`initial assume (!rst_n)` does not over-constrain past step 0**: the
  temporal-induction step of `mode prove` ignores initial-state assumptions
  entirely by construction (it proves "property holds at step k+1 given it
  held for the prior k steps," independent of how step 0 was reached), and
  that step passed on its own (`Temporal induction successful`) for all
  three widths. `rst_n` remains a free variable at every step after 0, so
  the proof still covers `rst_n` re-asserting mid-trace (`q` reloading
  `INIT_SEED`, still nonzero) -- the assumption only pins the trace's
  starting point, not its ongoing behavior.
- **Full proof result**: `sby -f galois_lfsr.sby` reports
  `DONE (PASS, rc=0)` / `successful proof by k-induction` for all three
  tasks on the real (non-negated) property.

## Affected Files

- `blocks/stocastic/rtl/galois_lfsr.sv` (new `` `ifdef FORMAL `` block:
  `initial assume (!rst_n);` and the `no_lockup` immediate assertion)
- `blocks/stocastic/verif/formal/galois_lfsr.sby` (new: proper
  `[tasks]`/`[options]`/`[engines]`/`[script]`/`[files]` SBY config,
  replacing a non-functional stub; `read_verilog -sv -formal`; three
  `chparam`-driven tasks -- `w4`, `w19`, `w64` -- so the proof covers more
  than one tap mask)
- `blocks/stocastic/verif/formal/galois_lfsr_bind.sv` (deleted -- the
  non-functional `bind`-based checker)

## More Information

See [0008](0008-taps-lut-yosys-frontend-encoding.md) for the other Yosys
native-frontend compatibility issue this same effort surfaced (`TAPS_LUT`'s
array encoding), found and fixed in the same session while standing up this
formal flow.
