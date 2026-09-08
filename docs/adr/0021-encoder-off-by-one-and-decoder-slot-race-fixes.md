---
status: Accepted
date: 2026-09-07
---

# 0021. Fix encoder off-by-one, decoder output-slot race, and encoder width-unsafe sizing, found by independent audit

## Context and Problem Statement

An independent audit of the whole `blocks/stocastic` library (requested after
this session's earlier remediation of `stochastic_decorrelator.sv` — see the
decorrelator's own reworked test suite and design — for the same kind of
scrutiny across the rest of the library) found two defects in modules that
had been treated as verified throughout this entire project, including by
every prior ADR (0013, 0015, 0016, 0017, 0019) and every accuracy claim made
along the way:

1. **Encoder systematic off-by-one** (`binary_stochastic_converter.sv`,
   `binary_stochastic_converter_sync.sv`): `galois_lfsr` never visits its
   all-zero state (its period is `2^WIDTH-1` states: `1..2^WIDTH-1`, not
   `0..2^WIDTH-1` — ADR 0005/0006). The encoder compared
   `random_number < binary_in_d`. Over one full burst, the count of LFSR
   states strictly less than a positive value `x` is `x-1`, not `x` — every
   positive input was under-encoded by exactly one 1-bit, and `x=0` and
   `x=1` both produced an all-zero stream (indistinguishable at the
   encoder's output). No existing test caught this: the per-bit cocotb
   tests compared against a Python `golden_model` that had independently
   copied the same `<` rule, so both sides agreed with each other while
   both being wrong relative to the intended `x/(2^WIDTH-1)` probability
   mapping.

2. **Decoder output-slot race** (`stochastic_binary_converter.sv`,
   `stochastic_binary_converter_sync.sv`, module `stochastic_to_binary`):
   the completion branch decided whether to immediately reopen the
   accumulator (clearing `last_sample_seen`/`ones_count`) using
   `ready_binary_out` sampled on the SAME cycle the window's last sample
   was accepted — one cycle BEFORE `valid_binary_out` ever became
   externally visible. If the consumer's `ready_binary_out` differed
   between that cycle and the cycle valid actually appeared (a fully legal
   sequence — ready is allowed to change any cycle), the module could
   silently drop a result that was never actually transferred under a real
   `valid && ready` handshake on the same cycle. The existing backpressure
   test covered "ready low throughout"; it never covered "ready flutters
   high then low before valid is visible."

   **A first fix attempt (gating the drain on `slot_available =
   !r.valid_binary_out || ready_binary_out`) resolved this specific race
   but a re-audit found a second, distinct defect it introduced no
   protection against:** the drain branch and the input-accept branch were
   chained as mutually-exclusive `else if`s. When a completed-but-
   unconsumed result sits in the slot while the NEXT window is already
   accumulating (`last_sample_seen=0`, so `ready_stochastic_in` is high),
   a cycle where the consumer finally raises `ready_binary_out` to drain
   the old result *and* a new input sample is accepted (both legal,
   independent handshakes) would only run the drain branch — silently
   discarding the input sample the module had already told the producer it
   accepted. A directed re-audit testbench
   (`/tmp/decoder_concurrent_handshake_tb.sv`) reproduced this on both
   reset variants.

3. **Encoder width-unsafe sizing** (`binary_stochastic_converter.sv`,
   `binary_stochastic_converter_sync.sv`): the module's elaboration check
   advertises `WIDTH inside {[2:64]}`, but `target_cycle_count` and
   `out_counter` were both sized via `$clog2((1 << n))`, and `1` is an
   *unsized* integer literal — 32 bits by default. Shifting a 32-bit value
   left by 32 or more bit positions shifts every bit out, so `1 << n`
   silently evaluates to `0` for `n >= 32` (well-defined LRM behavior, not
   an overflow trap or tool quirk). `$clog2(0)` is `0` by the LRM, so
   `$clog2((1<<n))-1` becomes `-1`, collapsing the declared width to an
   ascending `[-1:0]` range. Confirmed directly via Yosys elaboration:
   `out_counter` stays correctly sized through `WIDTH=31`, then collapses
   to a 2-bit ascending-range signal from `WIDTH=32` through `64`.

   **A first fix attempt (sizing `out_counter`/`target_cycle_count` as
   `[n-1:0]` directly) fixed only the encoder's own local wire — a
   re-audit found the encoder instantiates the shared `counter`/
   `counter_sync` module (`blocks/basic/`), whose own `UPTO` parameter was
   still declared `parameter int UPTO`, a 32-bit *signed* type.**
   `.UPTO(target_cycle_count + 1)` truncates/reinterprets into that 32-bit
   signed parameter regardless of how correctly `target_cycle_count`
   itself is now computed: at `WIDTH=32` the intended value (`2^32-1`)
   becomes *negative* as a 32-bit signed number, tripping `counter`'s own
   `` `MA_ASSERT_ELABOR(ValidCounterSize, UPTO > 0)`` fatal; at
   `WIDTH=33..64` the value doesn't fit in 32 bits at all and gets
   silently truncated, so `counter.out`'s actual port width (derived from
   the truncated `UPTO`) doesn't match the encoder's now-correctly-sized
   `out_counter` wire, and Yosys resizes the connection at the port
   boundary rather than erroring — the burst-length counter can never
   reach the real `target_cycle_count` for these widths. Checking only
   `out_counter`'s own declared width (as the first fix attempt's
   confirmation did) gives a false pass; the instantiated counter's own
   parameter and port must be checked too.

Each defect is structural/protocol-adjacent, of exactly the kind this
codebase's own discipline (bit-exact golden models, exhaustive population
tests, adversarial handshake sequences, elaboration-time width checks) is
supposed to catch — they went undetected because the specific tests that
would catch them (an exact input-to-density sweep independent of any
RTL-derived reference; the specific "ready flutters before valid" sequence;
a direct elaboration check of `out_counter`'s actual width at `WIDTH>=32`)
had never been written or run.

## Considered Options

**Encoder:**
1. Change the comparator to `random_number <= r.binary_in_d`.
2. Change the LFSR to also visit the all-zero state (a period of `2^WIDTH`
   instead of `2^WIDTH-1`).

**Decoder:**
1. Gate the slot-drain/reopen decision on `r.valid_binary_out &&
   ready_binary_out` (both read the same cycle, `r.valid_binary_out`
   already externally visible since the start of that cycle) instead of a
   same-cycle-as-latch snapshot of `ready_binary_out` alone.
2. Keep the existing structure but add a second read of `ready_binary_out`
   one cycle later to "confirm" the early decision.

**Encoder width-unsafe sizing:**
1. Force a wide-enough literal, e.g. `65'd1 << n` (needs at least 65 bits
   to represent `2^64` at all), everywhere this pattern appears.
2. Eliminate the `1 << n` computation entirely: `(1 << n) - 2` is
   mathematically identical to `'1 - 1` (SystemVerilog's self-sized
   all-ones fill, minus one) evaluated in an `n`-bit context, and
   `$clog2((1 << n))` was always exactly equal to `n` itself
   (`ceil(log2(2^n)) == n` for `n >= 1`), so the declarations can just be
   sized `[n-1:0]` directly.

## Decision Outcome

**Encoder: option 1.** Changing the comparator to `<=` gives exactly `x`
ones out of the `(2^WIDTH-1)`-bit burst for every `x` in
`{0, ..., 2^WIDTH-1}` — `x=0` still yields all zeros, `x=2^WIDTH-1` (max)
yields all ones, and the LFSR's own period/tap structure (already verified
by formal proof and the width-decorrelation characterization) is
untouched. Option 2 would change the LFSR's fundamental period and
lockup-avoidance property (ADR 0005/0006/0009's `no_lockup` formal
property specifically depends on the all-zero state being unreachable) for
no benefit — a one-character change to the encoder's own comparator is a
strictly smaller, more targeted fix.

**Decoder: option 1, plus a second structural fix the re-audit surfaced.**
`slot_available` removes the original race by construction — the drain
decision can never observe a not-yet-visible `valid_binary_out`. But
gating the drain and the input-accept on the same `if`/`else if` chain
treated them as mutually exclusive when they touch entirely disjoint state
(`valid_binary_out` vs. `ones_count`/`last_sample_seen`) and can legally
both need to happen on the same edge. The final structure keeps the
window-complete-and-latch branch as the first, highest-priority check
(`ready_stochastic_in` is low whenever `last_sample_seen` is high, so that
branch and an input accept are already naturally mutually exclusive — no
conflict there), then runs the drain check and the accept check as two
*independent* `if`s (not `else if`) inside the remaining `else`:

```systemverilog
if (r.last_sample_seen && slot_available) begin
  ... latch result, reopen accumulator ...
end else begin
  if (r.valid_binary_out && ready_binary_out) begin
    rin.valid_binary_out = 1'b0;
  end
  if (accept_this_cycle) begin
    rin.ones_count = r.ones_count + (stochastic_in == 1'b1);
    rin.last_sample_seen = boundary_in;
  end
end
```

Option 2 (a confirmation read one cycle later) was never applicable to
this second defect — it addresses a stale-snapshot problem, not a
mutual-exclusion problem, and would not have prevented the drain branch
from blocking the accept branch's execution.

**Encoder width-unsafe sizing, decoder counter dependency: widen the
shared `counter`'s own parameter.** `parameter int UPTO` in
`blocks/basic/counter.sv` and `counter_sync.sv` becomes
`parameter longint unsigned UPTO` (64 bits, unsigned) — sufficient to hold
the largest value this module ever needs to pass it
(`target_cycle_count + 1 = 2^64-1` at `WIDTH=64`) without truncation or
sign reinterpretation. Both `counter` and `counter_sync` have no other
instantiators in this repo (confirmed by grep), so this widening carries
no blast radius beyond the two encoder variants.

**Encoder width-unsafe sizing: option 2.** Removes the entire class of
"was the literal made wide enough" bugs rather than just widening this one
instance — no explicit power-of-two computation remains to overflow at any
`WIDTH` this module's own elaboration check allows, and matches this
codebase's existing philosophy of using self-sizing constructs
(`WIDTH'(1)`, seen elsewhere in this same file's own `INIT_SEED` default)
over hand-picked literal widths. Option 1 would work but leaves a
magic-number width (`65`) to remember and re-derive correctly at every call
site touching this pattern.

### Consequences

- Every prior accuracy claim in this project that used the encoder to
  produce numeric results (ADR 0019's WIDTH≥7 threshold characterization,
  the WIDTH=8 fabric bitstream verification in
  `~/wiki/fpga_stochastic_blocks/decision_logs/
  stochastic-v0-evidence-and-v1-candidate-2026-09-06.md`) was computed
  under the old, slightly-biased encoder. The qualitative conclusions
  (WIDTH<7 fails regardless of seed; WIDTH≥8 gives usable accuracy) are
  very unlikely to change from a systematic one-count bias this small, but
  the exact MAE percentages reported there are now stale by a small,
  consistent amount and would shift slightly if regenerated. Not
  regenerated as part of this fix — flagged here so it isn't mistaken for
  still being exactly reproducible.
- Three new regression tests close the specific gaps that let each bug
  through undetected: `exhaustive_input_to_density_contract`
  (`test_binary_to_stochastic`) sweeps every possible `binary_in` value and
  asserts the burst's exact ones-count independent of any RTL-derived
  golden model; `transient_ready_before_valid_must_not_drop_result` and
  `simultaneous_output_drain_and_input_accept_must_not_drop_input`
  (`test_stochastic_to_binary`) each reproduce one of the two distinct
  adversarial handshake sequences found across the two audit passes.
- `stochastic_binary_converter_sync.sv`/`binary_stochastic_converter_sync.sv`
  (the FABulous-target sync-reset variants, ADR 0020) share all fixes,
  since they're structurally identical except for reset style — confirmed
  directly by re-running both encoder and decoder cocotb suites against
  the `_sync` toplevels via `COCOTB_TOPLEVEL` override, not just asserted
  by similarity.
- `counter.sv`/`counter_sync.sv`'s own widened `UPTO` parameter has no
  dedicated cocotb regression at large widths for the same reason the
  encoder's width-safety fix doesn't (a WIDTH>=32 burst is `2^32-1`+
  cycles, computationally infeasible to simulate) — confirmed instead via
  direct Yosys elaboration/synthesis at WIDTH=4, 31, 32, 33, and 64,
  checking the *instantiated counter's* actual parameter value and port
  width, not just the encoder's own local wire (the first fix attempt's
  narrower check that produced a false pass).
- Two integration tests (`test_b_add_s_integration`,
  `test_b_mult_s_integration`) and the loopback test
  (`test_loopback_stochastic`) had their own tape/window bookkeeping built
  on the same `if`/`elif` mutual-exclusion assumption the decoder's second
  defect had — once the decoder correctly started accepting input on the
  same cycle it drains output, these tests' own accounting silently
  undercounted the next window's bits by exactly the concurrently-accepted
  sample, producing failures that looked like RTL regressions but were
  test-bookkeeping gaps of the identical shape. Fixed the same way: two
  independent `if`s instead of `if`/`elif`, in the same statement order
  (window/slot bookkeeping first, so it uses the pre-this-cycle state
  before the second `if` updates it) so a same-cycle event is attributed
  to the correct window on both sides.

### Confirmation

- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean (only the
  pre-existing, repo-wide `GENUNNAMED` warning class) on all six modified
  RTL files.
- Yosys `synth`+`check` clean (0 problems) for `stochastic_to_binary` and
  `binary_stochastic_converter` at default parameters, and (0 problems) for
  `binary_stochastic_converter` at `WIDTH=32`, `33`, and `64` specifically
  — the exact widths the original `ValidCounterSize` fatal and port-width
  mismatch hit before the `counter`/`counter_sync` parameter widening.
- Direct Yosys elaboration of `binary_stochastic_converter` with
  `chparam -set WIDTH <n>` at `n = 4, 31, 32, 33, 64`: both `out_counter`'s
  dumped width AND the instantiated `counter` cell's own `UPTO` parameter
  value track `n` correctly at every value, with no negative/truncated
  parameter and no port-width mismatch requiring a resize.
- Full repo regression (`scripts/run_regression.sh`): 31/31 cocotb tests
  passing across all nine testbenches, including the three new tests above.
  Several tests failed at intermediate points during this fix and were
  each traced to a *test*-side bug, not a reason to loosen the RTL fix:
  `valid_binary_out_should_hold_through_post_completion_stall` used a
  fixed post-write settling-edge count instead of this file's own
  established polling helper; `test_loopback_stochastic`,
  `test_b_add_s_integration`, and `test_b_mult_s_integration` each had the
  identical `if`/`elif` mutual-exclusion bug the decoder itself had, in
  their own window/tape bookkeeping.
- The new `simultaneous_output_drain_and_input_accept_must_not_drop_input`
  test itself needed one iteration to get right: its first version left
  `valid_stochastic_in`/`boundary_in` asserted with a stale value across a
  polling wait, letting a spurious extra accept complete a bogus 1-sample
  window before the intended adversarial cycle and invalidating the
  test's own precondition — confirmed by direct signal tracing, fixed by
  dropping `valid_stochastic_in` during the wait rather than assuming the
  RTL was still wrong. Re-run across multiple random seeds after the fix.
- Both reset variants of the encoder and decoder confirmed independently:
  full cocotb suites re-run against `binary_stochastic_converter_sync` and
  `stochastic_to_binary_sync` via `COCOTB_TOPLEVEL` override, all passing.

## Affected Files

- `blocks/basic/counter.sv`
- `blocks/basic/counter_sync.sv`
- `blocks/stocastic/rtl/binary_stochastic_converter.sv`
- `blocks/stocastic/rtl/binary_stochastic_converter_sync.sv`
- `blocks/stocastic/rtl/stochastic_binary_converter.sv`
- `blocks/stocastic/rtl/stochastic_binary_converter_sync.sv`
- `blocks/stocastic/verif/tb/test_binary_to_stochastic/test_binary_stochastic.py`
- `blocks/stocastic/verif/tb/test_stochastic_to_binary/test_stochastic_to_binary.py`
- `blocks/stocastic/verif/tb/test_loopback_stochastic/test_loopback_stochastic.py`
- `blocks/stocastic/verif/tb/test_b_add_s_integration/test_b_add_s_integration.py`
- `blocks/stocastic/verif/tb/test_b_mult_s_integration/test_b_mult_s_integration.py`

## More Information

Full audit findings (including several not addressed by this ADR — the
adder's slightly-biased select probability, the Zybo Z7 FPGA wrapper's
reset gap, `binary_multiply_top`'s truncated observable product, the
pre-commit lint hook's missing-dependency gap, most testbenches' still-
fragile active-edge scheduling, and stale documentation) are recorded in
`/tmp/stochastic_blocks_reaudit.md` (not committed — a point-in-time review
artifact) and should be triaged separately. A follow-up re-audit
(`/tmp/stochastic_fixes_reaudit_2026-09-07.md`, also not committed) is what
found the decoder's residual same-edge accept-vs-drain conflict and the
`counter`/`counter_sync` parameter-width gap this ADR's final version
covers — a useful confirmation that "the tests pass" and "the fix is
complete" are not the same claim, and that a fix touching a shared
dependency (`counter.sv`) needs the dependency's own interface checked, not
just the caller's local wires. This ADR covers only the three findings
fixed here.
