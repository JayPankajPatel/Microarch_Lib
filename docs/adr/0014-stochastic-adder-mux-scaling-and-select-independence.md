---
status: Accepted
date: 2026-08-27
---

# 0014. `stochastic_adder` is a textbook MUX-based scaled sum with its own internal select LFSR

## Context and Problem Statement

This is the baseline stochastic adder — a reference implementation to
compare future optimized variants against (per project direction: get a
correct, simple baseline for each primitive first, then optimize). Unlike
`stochastic_multiplier` (ADR 0012), where the arithmetic is a trivial AND
and the only real design question was the join handshake, addition in
stochastic computing has a genuine correctness subtlety: a bitstream
represents a probability in `[0, 1]`, so an exact sum `A + B` isn't
representable when both operands are near 1. The textbook approach scales
the result: `out = MUX(select, A, B)`, computing `(A + B) / 2`, where
`select` must be an independent random bit, freshly drawn per output bit.

The correctness risk isn't the MUX itself — it's `select`. Reusing one of
the operand streams' own driving LFSR, or a select LFSR that's correlated
with either operand (same seed, same taps, same phase), makes the "random"
choice not actually independent of what it's choosing between. This
doesn't fail loudly: a per-bit test that only checks "is `stochastic_out`
either A or B" passes regardless, and even a plain bitwise-formula test
(`valid_out == valid_a && valid_b`, etc.) passes too, since that's a
protocol property, not a randomness property. Only a statistical check
over many samples reveals a biased or correlated select.

## Considered Options

1. Require the caller to supply the select bitstream as a third module
   input (like a third operand), keeping the module itself
   randomness-agnostic.
2. Generate the select bit internally from a dedicated `galois_lfsr`
   instance, parameterized so a caller composing multiple adders/tiles can
   choose distinct `SELECT_LFSR_WIDTH`/`SELECT_INIT_SEED` values per
   instance.
3. Same as 2, but derive the select bit implicitly from A and B's own
   bitstreams (e.g. XOR of the two operand bits) instead of a separate
   LFSR, avoiding any extra hardware.

## Decision Outcome

Chosen option: **2**. `stochastic_adder` instantiates its own
`galois_lfsr` (`SELECT_RNG`), parameterized by `SELECT_LFSR_WIDTH`
(default 4) and `SELECT_INIT_SEED` (default `SELECT_LFSR_WIDTH'(1)`),
advanced only on cycles a real transfer happens
(`select_en = valid_stochastic_out && ready_stochastic_out`) — matching
how the encoder/decoder already pace their own LFSR advances against real
transfers, not wall-clock cycles.

- **Option 1** pushes the correctness burden entirely onto the caller with
  no structural guardrail — every future consumer would need to remember
  to wire up an independent third stream, and nothing catches it if they
  don't. Also complicates the module's interface for what should be a
  two-operand primitive from the caller's perspective.
- **Option 3** is a real technique (some stochastic-computing literature
  uses XOR-based dependent select for specific correlation-management
  reasons), but it's not the textbook baseline this module is meant to be,
  and makes the adder's actual randomness properties depend on A and B's
  own statistics in a way that's harder to reason about generically. Worth
  revisiting as one of the optimized variants this baseline exists to be
  compared against, not as the baseline itself.
- **Option 2 (chosen)** keeps the two-operand interface simple, makes the
  independence requirement structurally visible (two exposed parameters a
  caller must actively consider when composing multiple SC tiles sharing a
  correlation-management strategy — see the open wiki question on
  "correlation-management area cost per additional SC tile on a shared
  LFSR bank"), and reuses the already-verified `galois_lfsr` rather than
  introducing a second RNG implementation.

### Consequences

- **This does not itself guarantee independence** — it only makes the
  parameters that need to be chosen deliberately (`SELECT_LFSR_WIDTH`,
  `SELECT_INIT_SEED`) visible and overridable. A caller who instantiates
  this adder downstream of two encoders that also default to
  `WIDTH=4`/`INIT_SEED=1` gets a select LFSR with a *different* taps
  polynomial (since `TAPS_LUT[width]` differs from whatever WIDTH the
  operand encoders use) but has not been given a rigorous independence
  proof — just a reasonable default that isn't trivially identical to a
  same-width operand LFSR. Composing this at the fabric level (shared LFSR
  banks, chained tiles) needs its own analysis; this module doesn't solve
  that, it just doesn't make it worse by defaulting to something visibly
  wrong (e.g. reusing WIDTH=`operand WIDTH`/`INIT_SEED=1` exactly).
- No registered state in `stochastic_adder` itself beyond the select LFSR
  — same "don't apply Gaisler two-process style where a pure combinational
  join suffices" judgment call as ADR 0012's multiplier.
- The statistical test (`scaled_sum_statistical_property`, A held at
  constant 1, B at constant 0, 2000 samples, asserting observed 1-frequency
  within 0.05 of 0.5) is the one test in this module's suite that actually
  exercises the property this ADR is about — the per-bit tests only check
  protocol/arithmetic correctness given whatever the select sequence is,
  not that the sequence is behaving like real randomness relative to A/B.

### Confirmation

- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean (only the
  pre-existing `GENUNNAMED` warning class from the shared macro system).
- `test_stochastic_adder`: 5/5 passing —
  `basic_both_ready_every_cycle`, `one_operand_stall_holds_no_fire`,
  `downstream_stall_holds_backpressure_and_select_lfsr`,
  `back_to_back_streaming_random_join`, `scaled_sum_statistical_property`.
- Mutation-tested twice:
  1. `stochastic_out` forced to `stochastic_in_a` unconditionally (stuck-at
     select) — 3/5 tests fail, including the statistical property.
  2. `select_en` forced to `1'b1` (select LFSR free-runs instead of pacing
     to real transfers) — 4/5 tests fail, since this desyncs the golden
     model's predicted select sequence from the DUT's actual one.
  Both confirm the test suite depends on the real select-independence
  mechanism rather than passing by coincidence.

## Affected Files

- `blocks/stocastic/rtl/stochastic_adder.sv`
- `blocks/stocastic/verif/tb/test_stochastic_adder/`

## More Information

`docs/adr/0012-stochastic-multiplier-join-semantics.md` establishes the
two-producer join pattern this module reuses. See
`~/wiki/fpga_stochastic_blocks/` (per this repo's project memory) for the
open fabric-level question this module's independence caveat feeds into:
correlation-management cost when multiple SC tiles share an LFSR bank.
