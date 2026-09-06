---
status: Accepted
date: 2026-08-30
---

# 0017. `stochastic_to_binary` closes its window on an explicit `boundary_in` pulse, not a locally-counted length match

## Context and Problem Statement

After ADR 0016 fixed `binary_stochastic_converter`'s mutual-startup
deadlock, `test_loopback_stochastic`'s
`back_to_back_bursts_stay_aligned_under_tight_backpressure_coupling` test
started failing: a decoder window was observed spanning two different
encoder bursts (`sources {2, 3}`), even though both the encoder's burst
length and the decoder's window length are `2**WIDTH-1` (ADR 0013) — the
exact scenario GitHub issue #2 originally raised, resurfacing via a
different mechanism than the original length mismatch.

Root cause: matching lengths on both sides only guarantees alignment if
both sides also reset their counters at the same real-transfer index. The
old (buggy, per ADR 0016) encoder accept-gate coincidentally forced a
one-cycle stall at every burst boundary — waiting for the decoder's
`ready_stochastic_in` to reassert before starting — which is exactly what
kept the two sides' reset points phase-locked. Once that incidental stall
was correctly removed, the encoder could (correctly, per its own protocol)
start its next burst as soon as `valid_binary_in` allowed, independent of
whether the decoder had fully reopened yet — and any transient skew this
introduces at the first misalignment persists forever afterward (both
periods are equal, so neither side ever "catches up" or drifts further;
it's a fixed phase offset, not a growing one, but still a real, silent
value-boundary corruption).

More fundamentally: this exposed that "the decoder's local window length
happens to equal the encoder's burst length" was never a principled
synchronization mechanism — it doesn't generalize to compositions with no
single well-defined upstream "burst length" to match against at all, e.g.
`test_b_mult_s_integration`'s decoder, downstream of a join composing two
independently-seeded (and, in the general case, potentially
different-WIDTH) encoders through a multiplier.

## Considered Options

1. Reopen GitHub issue #2 with this new finding and defer an actual fix,
   keeping the existing length-matching mechanism.
2. Investigate whether `stochastic_to_binary`'s reopen-after-completion
   latency can be made same-cycle (matching the encoder's zero-bubble
   accept), restoring natural alignment without relying on an accidental
   stall.
3. Add an explicit boundary-pulse input to `stochastic_to_binary`: the
   producer asserts it on the transfer that is the last sample of its
   window, and the decoder closes its window on that signal instead of a
   locally-counted comparison. No credit/counter scheme — a single-pulse
   signal is sufficient here since this is a direct point-to-point (or
   join-synchronized) handshake, not a deep pipeline needing outstanding-
   transaction tracking.

## Decision Outcome

Chosen option: **3**. `stochastic_to_binary` gained a `boundary_in` input,
meaningful only on a cycle a real transfer happens
(`accept_this_cycle = valid_stochastic_in && ready_stochastic_in`). A new
registered `last_sample_seen` field replaces `cycle_count`'s old role of
"the window is done, waiting to announce/reopen" — set to `boundary_in`'s
value on the cycle a sample is accepted, instead of being inferred from
`cycle_count == MAX_CYCLES`. `cycle_count` itself is removed entirely; only
`ones_count` remains, since nothing else needs a running sample count once
completion is externally signaled. `binary_stochastic_converter`'s
existing `last_cycle` output (already fixed to correctly equal
`burst_complete`, per ADR 0013) is the producer-side signal wired into
this new input.

- **Option 1** doesn't fix anything — it leaves the same fragile
  length-matching mechanism in place for every future composition,
  including ones (like the multiplier composition) that never had a
  principled reason to expect it to hold in the first place.
- **Option 2** was considered but doesn't address the deeper issue: even a
  same-cycle reopen only restores alignment by making the *coincidence*
  tighter, not by making alignment structural. It also doesn't generalize
  to compositions without a single, well-defined upstream burst length
  (the multiplier case).
- **Option 3 (chosen)** makes the decoder's notion of "window" externally
  synchronized by construction rather than by coincidence — it closes
  exactly when told to, regardless of how many samples that turns out to
  be, and generalizes cleanly to the multiplier composition: since
  `stochastic_multiplier`'s join mutually gates each encoder's `en` on the
  *other* encoder's valid (ADR 0012), two same-WIDTH encoders' `last_cycle`
  outputs are provably simultaneous once both are busy — confirmed by a
  continuous assertion in `test_b_mult_s_integration`, not just asserted.
  A credit-counter scheme was explicitly not used here, since that's the
  right tool for deep pipelines with multiple outstanding transactions in
  flight, not a single-stage point-to-point (or join-synchronized)
  handshake like this one.

### Consequences

- `stochastic_to_binary`'s port list changed (`boundary_in` added, required
  by every caller) — every existing composition
  (`test_stochastic_to_binary`'s module-level tests, `loopback_top.sv`,
  `test_b_mult_s_integration/top.sv`) needed updating to drive or wire it.
- `test_stochastic_to_binary.py`'s four tests now drive `boundary_in`
  explicitly (high on the intended last sample of each simulated window,
  low otherwise) rather than relying on any implicit per-module window
  length — this is a more honest test setup, since "window length" is now
  purely a testbench choice, not something the RTL enforces internally.
- `loopback_top.sv` wires the encoder's `last_cycle` directly to the
  decoder's `boundary_in` (previously left unconnected with a
  `PINCONNECTEMPTY` lint waiver — now genuinely consumed).
- `test_b_mult_s_integration/top.sv` wires `u_encoder_a`'s `last_cycle` to
  the decoder's `boundary_in`; the testbench continuously asserts
  `last_cycle_a == last_cycle_b` rather than trusting the simultaneity
  claim silently.
- `cycle_count` removal means the decoder no longer independently bounds
  how many samples can accumulate before a boundary arrives — this is a
  documented shift of responsibility onto whatever defines the boundary
  pulse (the encoder's own burst-length correctness, per ADR 0013) rather
  than a safety net in the decoder itself. Not a regression: the old
  `cycle_count == MAX_CYCLES` check was never actually independent
  verification of the encoder's behavior either, since both sides had to
  already agree on `WIDTH` for it to mean anything.

### Confirmation

- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean on
  `stochastic_binary_converter.sv` (pre-existing warning classes only).
- `test_stochastic_to_binary`: 4/4 passing.
- Mutation-tested: forcing `rin.last_sample_seen = 1'b0` (ignoring
  `boundary_in` entirely) makes all 4/4 tests fail — confirms the new
  mechanism is load-bearing, not passing by coincidence.
- `test_loopback_stochastic`: 2/2 passing, confirmed across 5 random
  seeds — `back_to_back_bursts_stay_aligned_under_tight_backpressure_coupling`
  now holds by construction (boundary pulse), not by the encoder/decoder
  timing coincidence ADR 0016 removed.
- `test_b_mult_s_integration`: 2/2 passing (`smoke_test_no_deadlock`,
  `product_matches_golden_model_over_multiple_windows`), confirmed across
  5 random seeds, including the continuous `last_cycle_a == last_cycle_b`
  assertion holding throughout every run.
- Full regression: `test_binary_to_stochastic`, `test_stochastic_multiplier`,
  `test_stochastic_adder`, `test_galois_lfsr` all re-run and still passing
  (unaffected by this change, confirming no unrelated regressions).

## Affected Files

- `blocks/stocastic/rtl/stochastic_binary_converter.sv`
- `blocks/stocastic/verif/tb/test_stochastic_to_binary/test_stochastic_to_binary.py`
- `blocks/stocastic/verif/tb/test_loopback_stochastic/loopback_top.sv`
- `blocks/stocastic/verif/tb/test_b_mult_s_integration/` (new)

## More Information

`docs/adr/0016-encoder-accept-must-not-depend-on-downstream-ready.md`
documents the fix that reopened this issue. GitHub issue #2 is the
original report; this ADR supersedes its length-matching framing with an
explicit-synchronization mechanism.
