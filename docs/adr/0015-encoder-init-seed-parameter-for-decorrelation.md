---
status: Accepted
date: 2026-08-30
---

# 0015. `binary_stochastic_converter` exposes `INIT_SEED`, required to be distinct across instances sharing a consumer

## Context and Problem Statement

Wiring two `binary_stochastic_converter` encoders into `stochastic_multiplier`
(for an encoder → encoder → multiply → decode integration test) surfaces a
well-known stochastic-computing correctness trap: multiplying two
stochastic bitstreams via AND only computes the true product `p_a * p_b`
if the two streams are statistically independent. `binary_stochastic_converter`
had no way to control its internal `galois_lfsr`'s seed — it always used
the default (`WIDTH'(1)`) — so two same-`WIDTH` instances would drive
their LFSRs in lockstep, fully correlated, forever. Confirmed via a direct
statistical simulation (not just asserted): with a shared/correlated
random source compared against two thresholds, `AND` computes
`min(p_a, p_b)`, not `p_a * p_b` (e.g. `p_a=0.3, p_b=0.7`: independent
sources measured `0.21` matching `p_a*p_b`; a shared source measured
`0.30` matching `min(p_a,p_b)` — both within noise of their respective
predictions over 200,000 samples). This failure mode looks entirely
protocol-correct — valid handshakes, plausible-looking bits — while being
numerically wrong, which is what makes it dangerous to leave unaddressed
rather than a cosmetic gap.

## Considered Options

1. Leave `binary_stochastic_converter` as-is; require callers composing
   multiple instances to work around correlation externally (e.g. an
   external LFSR bank with per-instance taps).
2. Expose `INIT_SEED` as a new parameter on `binary_stochastic_converter`,
   pass-through to its internal `galois_lfsr` instance (which already
   supports it).
3. Give `binary_stochastic_converter` its own independent RNG selection
   logic (e.g. a built-in per-instance hash of some ID), removing the need
   for a caller to pick seeds at all.

## Decision Outcome

Chosen option: **2**. Added `parameter bit [WIDTH-1:0] INIT_SEED = WIDTH'(1)`
to `binary_stochastic_converter`, wired straight to its `galois_lfsr`
instance's own `INIT_SEED` parameter (which already existed and already
defaults identically — this only exposes the pass-through, no new
randomness logic).

- **Option 1** pushes a genuine correctness requirement onto every future
  caller with no structural reminder — exactly the shape of gap this
  session's `stochastic_adder` (ADR 0014) explicitly chose to avoid for
  its own select-bit independence requirement, by exposing the relevant
  seed parameter directly on the module that needs it.
- **Option 3** removes the caller's ability to reason about or control
  independence at all, and doesn't obviously improve on just picking
  distinct seeds — it would also need its own correctness argument (why a
  hash-derived seed is any less likely to collide than a chosen one),
  which is more design surface for no clear benefit at this stage.
- **Option 2 (chosen)** is the minimal change: `galois_lfsr` already
  supports arbitrary non-zero seeds; this only makes that capability
  reachable from the encoder's own port list, the same way
  `stochastic_adder`'s `SELECT_LFSR_WIDTH`/`SELECT_INIT_SEED` already
  exposes its own decorrelation knob.

### Consequences

- **This does not itself guarantee independence** — same caveat as ADR
  0014's select-LFSR decision: it only makes the parameter a caller must
  actively choose visible and overridable. `test_b_mult_s_integration/top.sv`
  enforces the specific, narrow "not literally identical" case via
  `` `MA_ASSERT_ELABOR(DistinctEncoderSeeds, INIT_SEED_A != INIT_SEED_B) `` —
  this catches the most common accidental mistake (forgetting to override
  the default) but is not a rigorous statistical-independence proof.
  Composing encoders at fabric scale (shared LFSR banks, per the open wiki
  question on correlation-management cost) still needs its own analysis.
- Default value is unchanged (`WIDTH'(1)`), so every existing single-encoder
  call site and test is unaffected — confirmed via full regression.

### Confirmation

- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean on
  `binary_stochastic_converter.sv` (pre-existing warning classes only).
- `test_binary_to_stochastic`: 4/4 passing, unmodified (default `INIT_SEED`
  behavior unaffected).
- `test_loopback_stochastic`: 2/2 passing (single-encoder composition,
  default seed, unaffected).
- Correlation failure mode independently verified via a standalone Python
  statistical simulation (200,000 samples) before relying on it as the
  motivating rationale, not just asserted from general SC-literature
  knowledge.

## Affected Files

- `blocks/stocastic/rtl/binary_stochastic_converter.sv`
- `blocks/stocastic/verif/tb/test_b_mult_s_integration/` (new)

## More Information

`docs/adr/0014-stochastic-adder-mux-scaling-and-select-independence.md`
establishes the same "expose the seed parameter, document the caveat"
pattern for `stochastic_adder`'s select-bit independence requirement.
