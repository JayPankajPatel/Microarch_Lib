---
status: Accepted
date: 2026-08-30
---

# 0018. `stochastic_adder` integration requires its select LFSR decorrelated from both operand encoders, not just the encoders from each other

## Context and Problem Statement

Building `test_b_add_s_integration/top.sv` (two `binary_stochastic_converter`
encoders → `stochastic_adder` → `stochastic_to_binary`, mirroring
`test_b_mult_s_integration`) surfaced a second decorrelation requirement
beyond ADR 0015's encoder-vs-encoder one: `stochastic_adder`'s own internal
select LFSR (ADR 0014) also needs to be independent of *both* operand
streams, not just of the two encoders relative to each other.

`stochastic_adder`'s join has the same shape as `stochastic_multiplier`'s
(ADR 0012), so all three LFSRs in this composition — encoder A, encoder B,
and the adder's `SELECT_RNG` — advance in lockstep on the exact same
real-transfer cycles (the adder's `select_en` and each encoder's `en` are
gated by the same join condition). With the default parameters
unconsidered (`WIDTH=4`/`INIT_SEED=1` for encoder A, matching
`stochastic_adder`'s own default `SELECT_LFSR_WIDTH=4`/`SELECT_INIT_SEED=1`),
the select LFSR would be numerically identical to encoder A's — same taps
polynomial, same seed, same advance cadence — meaning the "independent"
select bit would just *be* encoder A's own bitstream, fully correlated
with one operand. This is the same failure class ADR 0015 addressed for
encoder-vs-encoder correlation, recurring one level up in the composition
(select-vs-operand instead of operand-vs-operand), caught this time by
design-time review before ever running a test, not by a failing simulation.

## Considered Options

1. Leave `stochastic_adder`'s defaults as-is; document the requirement in
   prose and trust callers to override correctly.
2. Require the composing wrapper to pick a `SELECT_LFSR_WIDTH` distinct
   from the operand encoders' `WIDTH`, enforced by an elaboration check at
   the integration-test level (not inside `stochastic_adder` itself, which
   has no way to know what WIDTH its callers' encoders use).
3. Change `stochastic_adder`'s own default `SELECT_LFSR_WIDTH` to some
   value unlikely to collide with common encoder widths (e.g. a large
   prime-like default).

## Decision Outcome

Chosen option: **2**. `test_b_add_s_integration/top.sv` sets
`SELECT_LFSR_WIDTH` to `5` by default (distinct from the encoders' `WIDTH=4`
default) and adds
`` `MA_ASSERT_ELABOR(SelectLFSRDecorrelatedFromOperands, SELECT_LFSR_WIDTH != WIDTH) `` —
the same "catch the laziest accidental collision, not a rigorous
independence proof" pattern already established by
`DistinctEncoderSeeds` (ADR 0015).

- **Option 1** repeats exactly the mistake ADR 0015 was written to avoid:
  a correctness precondition that isn't enforceable by the module's own
  interface, left as tribal knowledge. Given this trap was found by
  deliberate design review this time (not a failing simulation), leaving
  it undocumented/unchecked would waste that catch.
- **Option 3** doesn't actually solve the problem — `stochastic_adder`
  has no way to know what WIDTH any given caller's encoders use, so any
  fixed default is just as capable of colliding with some caller's choice
  as `4` is. The check belongs at the composition site, where both
  widths are actually known simultaneously.
- **Option 2 (chosen)** puts the check where the information required to
  make it meaningful actually lives — the integration wrapper, which is
  the only place both `WIDTH` and `SELECT_LFSR_WIDTH` are in scope
  together — and reuses the low-cost elaboration-check pattern rather than
  inventing new machinery.

### Consequences

- `SELECT_LFSR_WIDTH != WIDTH` is a *necessary* precondition for
  structurally different LFSRs (different `WIDTH` means a different
  `TAPS_LUT` entry, see `galois_lfsr.sv`), not a *sufficient* proof of
  statistical independence in the rigorous sense. Composing at fabric
  scale (shared LFSR banks per the open wiki question) still needs its own
  analysis, same caveat as ADR 0014/0015.
- Confirms ADR 0016 and ADR 0017's fixes are genuinely general, not
  multiplier-specific: no new deadlock-avoidance or boundary-pulse work
  was needed for this composition — both suites passed on the first run,
  using the exact same accept-gate and `boundary_in` mechanisms already in
  place.

### Confirmation

- `pixi run verilator --lint-only` with `-GSELECT_LFSR_WIDTH=4` (forcing
  the collision) trips the new elaboration check
  (`USERFATAL: SelectLFSRDecorrelatedFromOperands`), confirming it's
  load-bearing, not decorative.
- `test_b_add_s_integration`: 2/2 passing (`smoke_test_no_deadlock`,
  `sum_matches_golden_model_over_multiple_windows`), confirmed across 5
  random seeds, including the continuous `last_cycle_a == last_cycle_b`
  assertion holding throughout every run (same simultaneity guarantee as
  the multiplier composition, ADR 0017).
- Full regression: all 8 test suites in `blocks/stocastic/verif/tb/`
  (encoder, decoder, loopback, multiplier, adder, LFSR, and both
  integration tests) re-run and passing, 25 tests total.

## Affected Files

- `blocks/stocastic/verif/tb/test_b_add_s_integration/` (new)

## More Information

`docs/adr/0014-stochastic-adder-mux-scaling-and-select-independence.md`
establishes the select-LFSR-independence requirement this ADR extends to a
concrete multi-module composition. `docs/adr/0015` documents the
analogous encoder-vs-encoder check this one mirrors at a different level
of the composition.
