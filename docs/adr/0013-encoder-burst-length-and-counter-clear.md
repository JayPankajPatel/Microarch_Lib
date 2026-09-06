---
status: Accepted
date: 2026-08-27
---

# 0013. `binary_stochastic_converter`'s burst counter gets an explicit synchronous clear, not an implicit wraparound reset

## Context and Problem Statement

GitHub issue #2 identified that `binary_stochastic_converter` (the encoder)
streamed `2**WIDTH` bits per burst while `stochastic_to_binary` (the
decoder) accumulated over `2**WIDTH-1` samples — one more than a clean
`galois_lfsr` period (per ADR 0005/0006, the LFSR's all-zero state is
unreachable, so its real period is `2**WIDTH-1`, not `2**WIDTH`).

Fixing the encoder's `target_cycle_count` from `2**WIDTH-1` to `2**WIDTH-2`
(so `out_counter` runs `0..2**WIDTH-2` inclusive, `2**WIDTH-1` values)
exposed a second, deeper latent bug: `out_counter` (driven by the shared
`counter` module) is never explicitly reset between bursts — only `rst_n`
clears it. It had always relied on its own register width overflowing back
to 0 at exactly the right moment. That coincidence held for the old,
buggy `target_cycle_count == 2**WIDTH-1`: the counter's port width is sized
via `$clog2(UPTO)`, and `UPTO == 2**WIDTH` (a power of 2) always needs
exactly `WIDTH` bits, so a burst's residual value (`target_cycle_count+1 ==
2**WIDTH`) wrapped to exactly 0 via plain bit truncation, every single
burst, for any `WIDTH` — no explicit reset was ever needed to *look*
correct.

`target_cycle_count == 2**WIDTH-2` breaks that coincidence: residual after
a burst is `2**WIDTH-1`, which is not a power of 2, so it does not wrap
back to 0 on its own. `out_counter` instead sits at `2**WIDTH-1` through
the idle gap and the next burst's accept cycle, and only wraps to 0 on that
next burst's *first* real advance — silently borrowing one cycle from what
should have been that burst's own count. Confirmed via a per-bit trace: the
second burst in `back_to_back_transfers` (3 consecutive bursts, `WIDTH=4`)
showed `out_counter` sitting at `15` (not `0`) through its accept cycle,
then wrapping mid-burst — corrupting both the golden model's LFSR-state
threading assumption and the completion timing for every burst after the
first.

## Considered Options

1. Pick a different `target_cycle_count`/counter-width combination that
   happens to make the residual wrap to 0 again (e.g. leave the counter at
   `2**WIDTH-1` states but size its register to some non-power-of-2
   modulus).
2. Replace the shared `counter` module with an inline counter local to
   `binary_stochastic_converter` that resets itself on burst completion.
3. Add an explicit synchronous `clr` input to the shared `counter` module,
   driven by the real burst-completion condition, taking priority over `en`.

## Decision Outcome

Chosen option: **3**. `counter.sv` gained a `clr` port (`clr` checked
before `en` in the `always_ff`, so a caller can restart a count window on
the same cycle it would otherwise have incremented).
`binary_stochastic_converter.sv` wires a new `burst_complete` signal
(`r.busy && (out_counter == target_cycle_count) && ready_stochastic_out` —
the exact condition that already gated the completion branch in
`always_comb`, now named and reused rather than inlined twice) into
`counter`'s `clr`.

- **Option 1** doesn't actually fix anything — it just re-hides the same
  class of bug behind a different numeric coincidence, which is the root
  problem being fixed here (see also the `MA_ASSERT_ELABOR`-macro-naming
  precedent in ADR 0011 for this repo's general stance on "worked by
  accident" being treated as a bug, not a feature). A future width or
  burst-length change would silently reintroduce the same failure mode.
- **Option 2** would work but throws away `counter.sv`'s reuse — it is
  currently only instantiated here (confirmed via
  `grep -rn "counter #(" blocks/`), so there was no compatibility
  constraint forcing this, but duplicating counting logic inline
  contradicts this repo's general preference for shared, tested primitives
  over ad hoc reimplementation, and the module was already being reused
  for exactly this purpose.
- **Option 3 (chosen)** fixes the root cause directly (explicit reset
  instead of relying on wraparound), keeps `counter.sv` genuinely reusable
  for future consumers that might not have a power-of-2-friendly `UPTO`,
  and required touching only the single existing call site.

### Consequences

- `counter.sv`'s interface changed (`clr` added) — since it has exactly one
  consumer today, this was a same-commit update, not a deprecation.
- `test_binary_to_stochastic/test_binary_stochastic.py`'s `golden_model`
  and protocol doc-comment were updated to predict `2**WIDTH-1` bits per
  burst instead of `2**WIDTH`, matching the fixed RTL.
- `stall_holds_bit_and_stretches_busy`'s hardcoded `stall_at=2` needed
  clamping to `min(2, len(expected_bits) - 2)` — bit index 2 was safely
  mid-burst when bursts were `2**WIDTH` bits (`WIDTH=2` burst length 4),
  but is now the *last* valid index in a `WIDTH=2` burst (length 3),
  which made the stall handler's post-stall "settling bit" check
  (`expected_bits[bits_consumed + 1]`) index out of range. Not a design
  flaw in the stall logic itself, just a fixed test constant that assumed
  a burst length at least one longer than the new minimum.
- `test_loopback_stochastic`'s empirical finding (encoder/decoder
  off-by-ones cancelling out under tight backpressure coupling, documented
  in that test's own docstring and posted to GitHub issue #2) still holds
  and is now true for a stronger reason: burst length and decoder window
  length are natively equal, so the cancellation is no longer load-bearing
  for correctness, just an incidental one-cycle-per-window throughput cost
  from the decoder's own completion-and-reopen latency.
- `last_cycle` (a public, currently-unconsumed output) was changed from an
  independent `r.busy && (out_counter == target_cycle_count)` expression to
  `assign last_cycle = burst_complete;`. The independent form diverges from
  `burst_complete` during a downstream stall at the burst boundary --
  `out_counter` holds at `target_cycle_count` for the whole stall (the
  counter isn't cleared, the burst hasn't actually retired), so the
  independent expression would assert for the entire stall instead of the
  one real retiring cycle. Nothing consumes this port today, so it wasn't a
  live bug, but it's exactly the shape of "true by coincidence" this ADR
  otherwise fixes, and it's the signal future chain-mode wiring
  (`docs/adr` architecture notes on tile chaining) would reach for first.

### Confirmation

- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean on `counter.sv`
  and `binary_stochastic_converter.sv` (only the pre-existing
  `GENUNNAMED`/`DECLFILENAME` warning classes already present across this
  block, confirmed unchanged by this fix).
- `test_binary_to_stochastic`: 4/4 passing, confirmed across multiple
  random seeds.
- `pixi run sweep-widths blocks/stocastic/verif/tb/test_binary_to_stochastic
  2 3 4 5 6 7 8 9 10 11 12 13 14 15 16`: 4/4 passing at every width
  (`WIDTH=2` required the `stall_at` clamp above; all others passed
  unmodified).
- `test_stochastic_to_binary`, `test_loopback_stochastic`,
  `test_stochastic_multiplier`, and `test_galois_lfsr` all re-run and still
  passing after this change (regression check for the shared `counter`
  and `binary_stochastic_converter` interface changes).
- `back_to_back_transfers` now directly asserts `RNG.out` matches the
  golden model's threaded LFSR state at the start of every burst (not just
  that emitted bits match), confirmed identical (`1`) across all 3 bursts
  in a `WIDTH=4` run -- the actual burst-to-burst phase-reproducibility
  property issue #2 was about, not just bit-for-bit framing.
- Mutation-tested the fix itself: with `counter`'s `clr` input forced to
  `1'b0` (reverting to the old implicit-wraparound behavior),
  `back_to_back_transfers` fails immediately (`RNG.out` reads `2` instead
  of the expected `1` at burst 2's start) -- confirming the test suite
  actually depends on this fix and isn't passing by coincidence.

## Affected Files

- `blocks/basic/counter.sv`
- `blocks/stocastic/rtl/binary_stochastic_converter.sv`
- `blocks/stocastic/verif/tb/test_binary_to_stochastic/test_binary_stochastic.py`

## More Information

GitHub issue #2 tracks the original encoder/decoder window-length mismatch
this fixes; see also `docs/adr/0005-taps-lut-sparse-vs-dense-ppa.md` and
`docs/adr/0006-galois-lfsr-tap-mirroring.md` for why `galois_lfsr`'s real
period is `2**WIDTH-1`, not `2**WIDTH`.
