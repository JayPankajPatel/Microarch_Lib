---
status: accepted
date: 2026-08-16
---

# 0007. FSM-shaped RTL uses the Gaisler two-process style (`r`/`rin` struct, single `always_comb` + single `always_ff`)

## Context and Problem Statement

`binary_stochastic_converter.sv` implements a small handshake-driven FSM
(idle / streaming-a-burst) using one `always_ff` block with `busy`,
`en`, `ready_binary_in`, `valid_stochastic_out`, and `binary_in_d` as
separate `logic` registers, each conditionally assigned across nested
`if`/`else` branches. Two real bugs were found in that style while
implementing the module against `binary_stochastic_timing_diagram.svg`
(the reference waveform for this converter):

1. `valid_stochastic_out <= '0` was written unconditionally in the
   `busy` branch, dropping the signal one cycle into every burst instead
   of holding it high for the whole burst as the waveform requires.
2. The burst-termination check (`out_counter == target_cycle_count`)
   was nested inside the `if (!busy)` branch, but `out_counter` only
   ever reaches that value while `busy == 1` -- the condition was
   unreachable and `busy` would never clear.

Both bugs share a root cause: in a multi-branch `always_ff`, a signal
not assigned on a given path silently holds its previous value, and
whether a given branch assigns a given signal is a separate concern
from whether the branch structure itself is correct. Nothing forces
every branch to make an explicit choice for every piece of state, so a
missing assignment (bug 1) and a misplaced branch (bug 2) both compile
cleanly and only show up as wrong runtime behavior. This module's
author found the single-block style with several individually-declared
registers confusing to reason about for exactly this reason.

## Decision Drivers

- This repo is tapeout-bound (per top-level `CLAUDE.md`): prefer
  proven, widely-used RTL conventions over ad hoc structure, especially
  for FSM-shaped logic where implicit-hold bugs are easy to write and
  easy to miss in review.
- The fix should make the *next* similar bug harder to write, not just
  correct this one instance.

## Considered Options

1. Keep the single-`always_ff`, multiple-separate-registers style, and
   simply fix the two bugs in place.
2. Adopt the Gaisler two-process style (from Aeroflex Gaisler's
   GRLIB/LEON3 coding convention): all registered state collected into
   one `r`/`rin` struct pair; a single `always_comb` block computes
   `rin` from `r` and the module's inputs, defaulting `rin = r` (hold
   everything) before conditionally overriding only the fields that
   change; a single `always_ff` block does nothing but `r <= rin`
   (plus the reset assignment).
3. Use a `case`-based explicit-state-enum FSM (separate `state`/
   `next_state` signals, `unique case` on an enum) instead of the
   current implicit boolean-flag (`busy`) encoding.

## Decision Outcome

Chosen option: **2, Gaisler two-process style**, because it directly
targets the root cause: `rin = r` as the first line of the
combinational block means every field of `rin` already has a defined
value before any branch runs, so a missing assignment in some branch
is a non-issue (bug 1's class) rather than a silent implicit hold, and
collecting all next-state decisions into one combinational block makes
misplaced branch nesting (bug 2's class) easier to spot on read since
the whole next-state computation is in one place instead of spread
across a single sequential block that mixes "what changes" with "when
it's clocked in".

Option 1 was rejected because it fixes only this instance, not the
pattern -- the same class of bug remains equally easy to introduce in
the next FSM-shaped block in this repo.

Option 3 was rejected as unnecessary for this module: the FSM has only
two states (idle / busy), a single boolean already encodes that
exactly, and introducing an enum and explicit `state`/`next_state`
signals on top of the two-process restructuring would add ceremony
without a corresponding clarity gain at this size. The two-process
convention itself does not preclude an explicit-state enum for larger
FSMs later; this decision is about the register/combinational split,
not about how state is encoded within it.

### Consequences

- All registered state for a module (`binary_in_d`, `ready_binary_in`,
  `valid_stochastic_out`, `en`, `busy`) lives in one `state_t r` struct
  instead of five separate `logic` declarations; module outputs that
  are just a struct field are wired out with a trailing `assign`.
- Every future edit to this module's FSM logic happens in the
  `always_comb` block against `rin`; the `always_ff` block should
  essentially never need to change (reset values aside).
- This is now the intended house style for FSM-shaped blocks in this
  repo going forward, not just a one-off fix -- apply it when writing
  new blocks with more than a couple of pieces of interacting
  registered state, not to purely combinational or single-register
  modules like `counter.sv` or `galois_lfsr.sv` where it would add
  structure without benefit.

### Confirmation

`pixi run verilator --lint-only -Wall -Icommon/rtl -Iblocks/stocastic/rtl
-Iblocks/basic blocks/stocastic/rtl/binary_stochastic_converter.sv`
produces only the pre-existing, ADR-0004-documented `GENUNNAMED`
warnings (from `` `MA_ASSERT_INIT ``'s conditional-generate expansion,
also present on `counter.sv` and `galois_lfsr.sv`) -- no new warnings
from the restructuring.

`pixi run make` in
`blocks/stocastic/verif/tb/test_binary_to_stochastic/` (cocotb +
Verilator, `WIDTH=4`) exercises exactly the two bugs this ADR
describes and passes against the corrected RTL:

- `single_transfer_matches_waveform_protocol`: accepts one `binary_in`,
  checks `valid_stochastic_out` stays asserted for all 16 bits of the
  burst (would fail under bug 1), each bit matches
  `random_number < binary_in`, and the burst terminates and hands
  `ready_binary_in` back after exactly 16 bits (would hang forever
  under bug 2).
- `stall_holds_bit_and_stretches_busy`: asserts backpressure
  (`ready_stochastic_out == 0`) mid-burst and checks the current bit
  holds steady and the burst length stretches accordingly.
- `back_to_back_transfers`: runs three consecutive bursts to confirm
  the FSM returns cleanly to idle and re-accepts.

All three tests pass: `TESTS=3 PASS=3 FAIL=0 SKIP=0`.
`test_galois_lfsr`'s existing two tests (unaffected by this change,
since `galois_lfsr.sv` itself wasn't touched) still pass unchanged,
confirming the shared source list didn't regress.

## Affected Files

- `blocks/stocastic/rtl/binary_stochastic_converter.sv` (restructured
  to the `r`/`rin` two-process form; two FSM bugs fixed as part of the
  restructuring)
- `blocks/stocastic/verif/tb/test_binary_to_stochastic/test_binary_stochastic.py`
  (replaced the placeholder smoke test with real assertions against
  the waveform-derived protocol)

## More Information

- Reference waveform this module implements:
  `binary_stochastic_timing_diagram.svg` (not checked into the repo;
  supplied externally as the spec for this module's handshake and
  streaming timing).
- Aeroflex Gaisler's GRLIB/LEON3 coding style, the source of this
  convention's name and structure.
