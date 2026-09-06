---
status: accepted
date: 2026-08-27
---

# 0012. `stochastic_multiplier` joins two independent valid/ready producers with `valid` never gated on `ready`

## Context and Problem Statement

`stochastic_multiplier` ANDs two independent single-bit stochastic streams
(operand A, operand B) that are not necessarily synchronized -- either
producer may stall independently. The AND itself is trivial; the actual
design question is what logic decides, each cycle, whether a bit is
considered "consumed" from each side and whether the combined output is
"valid," given two upstream valid/ready handshakes and one downstream
valid/ready handshake.

Getting this wrong either desyncs the two streams (a bit silently dropped
from one operand with no matching bit dropped from the other, corrupting
every AND downstream of that point) or violates AMBA-style valid/ready
composability, which this repo already treats as a real hazard --
`stochastic_to_binary`'s ready/valid decoupling bug (see its ADR
0007 and its test file's `valid_binary_out_should_hold_through_post_completion_stall`
test) is exactly the class of bug this module's join logic needed to avoid
by construction, not just by testing after the fact.

## Considered Options

1. **`valid_out = valid_a && valid_b`, `ready_a = ready_out && valid_b`,
   `ready_b = ready_out && valid_a`** (each producer's ready gated on the
   *other* producer's valid, output valid gated on neither producer's
   readiness).
2. `valid_out = valid_a && valid_b && ready_out` (fold downstream readiness
   into the output's own valid signal).
3. Gate each producer's ready on its *own* valid as well, e.g.
   `ready_a = ready_out && valid_b && valid_a`.
4. A registered/skid-buffered stage per operand, decoupling the join from
   combinational readiness.

## Decision Outcome

Chosen option: **1**, because it's the only one of the four that is both
correct and adds no unnecessary state or dependency.

- Option 2 was rejected because it makes `VALID` depend on `READY`, which
  is the specific AMBA rule this repo has already been bitten by getting
  wrong once (see Context). Concretely, chaining two blocks built this way
  creates a combinational dependency where each side's `VALID` waits on the
  other's `READY` and vice versa -- a structural deadlock risk, not just a
  style violation. Under option 1, `valid_stochastic_out` reflects
  `valid_a && valid_b` unconditionally; a downstream consumer that isn't
  ready simply doesn't assert its own `ready`, and no data is lost because
  nothing was ever latched -- this module has no registered state for a
  dropped cycle to corrupt.
- Option 3 was rejected as dead logic: `ready` without the matching
  `valid` on that same side already produces no transfer (nothing reads
  `ready_a` except in conjunction with `valid_a` on the producer side), so
  ANDing in the operand's own valid is an extra term that changes nothing
  observable while adding a spurious dependency. This was caught directly
  while writing the testbench -- an early version of
  `one_operand_stall_holds_no_fire` asserted `ready_stochastic_in_b == 0`
  while B was not valid, which is *not* required by the design and doesn't
  hold for option 1's correct implementation; the fix was to correct the
  test's expectation, not the RTL. Recorded here so the next reader doesn't
  reach for the same wrong intuition.
- Option 4 was rejected because zero registered state is needed for a pure
  AND join -- adding a skid buffer here would be state introduced for its
  own sake, which CLAUDE.md's anti-overengineering guidance and this
  module's actual requirements both argue against. The tradeoff being
  accepted instead: `ready_stochastic_in_a`/`ready_stochastic_in_b` are
  combinational functions of `ready_stochastic_out`, so chaining N of these
  joins produces an N-deep combinational path on the ready signal. That's a
  known, deliberate consequence (see below), not an oversight -- if a
  future composition needs to break that path for timing closure, a skid
  buffer should be added there deliberately, not preemptively here.

### Consequences

- `stochastic_multiplier` has no registered state and no `clk`/`rst_n`
  dependency in its logic; both ports are kept anyway to match every other
  block's module-port convention in this repo, and are silenced locally
  with a scoped `/* verilator lint_off UNUSEDSIGNAL */` / `lint_on` pair
  around just those two ports (same pattern as `binary_stochastic_converter.sv`'s
  `ASCRANGE` and `counter.sv`'s `WIDTHEXPAND` scoped waivers) rather than
  dropping the ports, since dropping them would make this module's
  instantiation inconsistent with its siblings.
- Chaining multiple valid/ready stages through this join produces a
  combinational `ready` path as long as the chain -- acceptable for a
  single multiplier, but a real constraint to revisit if `stochastic_multiplier`
  instances are ever composed back-to-back in a longer pipeline.

### Confirmation

`blocks/stocastic/verif/tb/test_stochastic_multiplier/test_stochastic_multiplier.py`,
4/4 passing (`pixi run -e default make` from that directory):

- `basic_both_ready_every_cycle` -- both producers and the consumer ready
  every cycle; output matches AND of the driven bits every cycle.
- `one_operand_stall_holds_no_fire` -- B's valid drops while A stays valid
  and the consumer stays ready; confirms `ready_stochastic_in_a` stays low
  (no bit silently consumed from A) and `valid_stochastic_out` stays low.
- `downstream_stall_holds_backpressure_on_both_operands` -- consumer not
  ready while both operands are valid; confirms both operand readys stay
  low (real option-1-vs-option-2 discriminator) while
  `valid_stochastic_out` correctly stays *high* the whole time, confirming
  `VALID` is not gated on `READY`.
- `back_to_back_streaming_random_join` -- 500 cycles with A's valid, B's
  valid, and the consumer's ready independently randomized; independently
  accumulates each side's *actually-consumed* stream (`valid && ready` on
  that side, not just `valid`) and asserts all three streams (A consumed,
  B consumed, output produced) stay equal length and the output equals the
  pairwise AND -- the sample-for-sample no-desync property, not just a
  per-cycle restatement of the RTL's own equations.

## Affected Files

- `blocks/stocastic/rtl/stochastic_multipler.sv`
- `blocks/stocastic/verif/tb/test_stochastic_multiplier/test_stochastic_multiplier.py`
- `blocks/stocastic/verif/tb/test_stochastic_multiplier/Makefile`

## More Information

See [0007](0007-gaisler-two-process-fsm-style.md) for the two concrete
handshake bugs (in a different module) that motivate this repo's general
wariness of getting valid/ready composability wrong.
