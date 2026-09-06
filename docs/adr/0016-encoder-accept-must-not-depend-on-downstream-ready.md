---
status: Accepted
date: 2026-08-30
---

# 0016. `binary_stochastic_converter`'s accept condition depends only on its own state and `valid_binary_in`, never on `ready_stochastic_out`

## Context and Problem Statement

Wiring two `binary_stochastic_converter` instances into a shared
`stochastic_multiplier` (for an encoder → encoder → multiply → decode
integration test) deadlocked from reset: neither encoder ever accepted its
first `binary_in`, confirmed via a per-cycle trace showing
`ready_binary_in=1` (idle) on both encoders forever, with `valid_stochastic_out`
never asserting on either side.

Root cause: the encoder's accept condition was
`!r.busy && valid_binary_in && ready_stochastic_out` — a burst could only
begin once the encoder already observed its downstream's `ready_stochastic_out`
as high. `stochastic_multiplier`'s join equations (ADR 0012) are:

```systemverilog
ready_stochastic_in_a = ready_stochastic_out && valid_stochastic_in_b;
ready_stochastic_in_b = ready_stochastic_out && valid_stochastic_in_a;
```

Encoder A's `ready_stochastic_out` (the multiplier's `ready_stochastic_in_a`)
depends on encoder B already being valid; encoder B's depends symmetrically
on A. At reset neither is valid, so neither's accept condition can ever
become true — a mutual-startup deadlock, invisible until this specific
composition: every prior consumer (a plain decoder, or a testbench stub)
has readiness independent of the encoder's own valid, so the same gate
never mattered before.

This is the same shape of AMBA Rule 1 violation ("VALID must never wait for
READY") this session's earlier `stochastic_to_binary` fix addressed at the
*end* of a window (see ADR 0013's confirmation notes and the original
decoder completion-branch fix) — here it recurs at the *start* of a burst.
Gating a burst's very first `valid_stochastic_out` assertion on an
already-observed `ready_stochastic_out` is exactly "valid implicitly waits
for ready," just relocated to the accept transition instead of the
completion transition.

## Considered Options

1. Add a skid buffer per operand between each encoder and the multiplier,
   giving each encoder an always-ready consumer to accept against.
2. Redesign `stochastic_multiplier` with a startup-aware state machine that
   can independently latch a first bit from either operand before both are
   flowing.
3. Decouple the encoder's accept condition from `ready_stochastic_out`
   entirely: start a burst on `!r.busy && valid_binary_in` alone.

## Decision Outcome

Chosen option: **3**. The accept branch's condition dropped
`&& ready_stochastic_out`; `ready_stochastic_out` still gates `en`
(advancing the LFSR/counter) and the completion condition (`burst_complete`),
exactly as before — it now only ever governs whether an *already-presented*
bit gets consumed, never whether a new burst is allowed to begin.

- **Option 1** would work here but treats a symptom, not the root cause:
  the encoder's accept-gate would still implicitly wait for ready at every
  future composition site with similar coupling (e.g. `stochastic_adder`,
  or the wiki's chain-optimization idea composing multiple tiles) unless a
  buffer is added at every one of them. The underlying violation would
  persist, just made inert by construction at each site it's remembered to
  guard.
- **Option 2** is the heaviest option and modifies an already-verified,
  ADR-documented block (0012) to work around a bug that isn't actually in
  it — the multiplier's join equations are correct AMBA-style join logic;
  the violation is upstream, in the encoder.
- **Option 3 (chosen)** fixes the actual violation at its source, is
  consistent with the precedent already set for the decoder's completion
  branch, and is the smallest change: one condition, no new state, no new
  ports.

### Consequences

- Bit 0 of a burst is still computed purely combinationally
  (`stochastic_out = random_number < r.binary_in_d`), so presenting it
  immediately on accept — before `ready_stochastic_out` is necessarily
  known — doesn't require any new logic; it's already correct and held
  steady by the existing `en`-gated advance if the consumer isn't ready
  yet, identical to how any other bit mid-burst is already held during a
  stall.
- Existing `test_binary_to_stochastic` suite (4/4, all four tests) passes
  unmodified, since every one of those tests already drives
  `ready_stochastic_out=1` before or at the same cycle as `valid_binary_in`
  — this fix only changes behavior for the case those tests never
  exercised (accept while ready is still low), so it changes nothing
  observable there.
- This fix **reopened GitHub issue #2's window-length concern** for
  `test_loopback_stochastic`'s continuously-driven-producer scenario: the
  old (buggy) accept-gate coincidentally forced a one-cycle stall on every
  burst boundary (waiting for the decoder's `ready_stochastic_in` to
  reassert), which is exactly what kept the encoder/decoder length
  agreement's phase alignment stable in that topology. Removing that
  incidental stall (correctly) exposed a genuine phase-alignment gap
  between the encoder's burst boundary and the decoder's window boundary
  even with matching lengths, addressed separately in
  `docs/adr/0017-decoder-window-close-via-boundary-pulse.md`.

### Confirmation

- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean (pre-existing
  warning classes only).
- `test_binary_to_stochastic`: 4/4 passing, confirmed across multiple
  random seeds, unmodified from before this fix.
- `test_b_mult_s_integration.smoke_test_no_deadlock`: confirms two encoders
  driven from cold reset produce a `binary_out` result within 200 cycles
  (previously hung forever, confirmed via a 30-cycle trace showing zero
  progress before this fix).

## Affected Files

- `blocks/stocastic/rtl/binary_stochastic_converter.sv`
- `blocks/stocastic/verif/tb/test_b_mult_s_integration/` (new)

## More Information

`docs/adr/0012-stochastic-multiplier-join-semantics.md` establishes the
join pattern whose readiness equations exposed this bug.
`docs/adr/0013-encoder-burst-length-and-counter-clear.md`'s confirmation
notes document the precedent case (the decoder's own completion-branch
Rule 1 violation) this fix generalizes.
