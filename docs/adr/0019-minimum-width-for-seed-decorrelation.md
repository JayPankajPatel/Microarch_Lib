---
status: Accepted
date: 2026-09-06
---

# 0019. A minimum `WIDTH` of 7 is required for seed-based LFSR decorrelation to work at all

## Context and Problem Statement

GitHub issue #3 reported that `test_b_mult_s_integration`/`test_b_add_s_integration`'s
default encoder seeds (`INIT_SEED_A=1`, `INIT_SEED_B=2`, at `WIDTH=4`) are a
near-worst-case choice: adjacent integer seeds turned out to be only 1 step
apart on the LFSR's own state cycle (`phase_lag(seed=1, seed=2) = 1`), nearly
fully correlated rather than independent. The issue's own next-steps asked
for "a verified-well-separated pair," implicitly assuming a better seed
choice at the same `WIDTH=4` would fix it.

A follow-up characterization (`Tracked_FPGA_experiments`' `Stochastic_Blocks/tb/decorrelation_seed_sweep.py`,
separate repo, tracked there) tested that assumption directly: for each
`WIDTH` from 2 to 16, it found the *best possible* seed pair (phase lag
closest to half the LFSR's period) and measured AND-multiply accuracy at
N=2^16 across four representative `(p1,p2)` pairs. Result: **no seed pair,
however well phase-separated, gives accurate output at `WIDTH` 2 through
6** — average absolute error ranged 0.018-0.153, all far above the
sampling-noise floor. At `WIDTH=7` (period 127) and above, phase-separated
seeds reliably work (error 0.0000-0.0051), improving further with width.

This means issue #3's original framing was incomplete: the problem isn't
"the wrong seed was chosen," it's that **`WIDTH=4` cannot achieve accurate
stochastic multiplication via seed selection at any seed pair** — the LFSR
period (15 states) is too short relative to any useful sample count,
regardless of phase separation. A "verified-well-separated pair" at
`WIDTH=4` doesn't exist, because none is good enough.

## Considered Options

1. Pick the best available `WIDTH=4` seed pair anyway (per the sweep:
   `seed_b=11`, phase lag 7) and update the test defaults to it, treating it
   as "the fix."
2. Change `test_b_mult_s_integration`/`test_b_add_s_integration`'s default
   `WIDTH` to 7 or higher, so the existing tests demonstrate genuinely
   accurate numeric output.
3. Leave `WIDTH=4` and the existing seeds as-is; document the structural
   limit plainly in both modules' header comments and this ADR, so nobody
   mistakes those tests' passing status for a numeric-accuracy guarantee.

## Decision Outcome

Chosen option: **3**, with option 1's finding (best available `WIDTH=4`
seed) recorded here for reference but not adopted as if it were a fix.

- **Option 1** would be actively misleading — updating the default seed
  implies the problem is solved, when the characterization shows it
  fundamentally isn't at this width. Committing to a "less bad" seed
  without saying so risks the same failure mode issue #3 itself was about:
  a change that looks correct (a "better," distinct, even
  phase-separated seed) while still being numerically wrong.
- **Option 2** would fix accuracy but silently changes what these tests are
  scoped to test — `test_b_mult_s_integration`/`test_b_add_s_integration`
  were deliberately built as "4-bit multiply"/"4-bit add" compositions
  (matching the existing RTL's `WIDTH=4` convention used throughout this
  repo's other tests). Changing the default width there is a scope
  decision belonging to whoever needs a numerically-trustworthy example,
  not a mechanical fix to this issue.
- **Option 3 (chosen)** is the honest baseline: these tests were always
  scoped as *structural/protocol* verification (`binary_out` honestly
  reflects whatever the multiplier/adder actually output — confirmed
  correct regardless of `WIDTH`), never as a numeric-accuracy
  demonstration. Making that explicit in both modules' comments (rather
  than leaving the `WIDTH=4` accuracy gap implicit) closes the actual gap
  issue #3 identified: someone reading these files no longer has a false
  impression that "distinct seeds" solved the correlation problem.

### Consequences

- `test_b_mult_s_integration/top.sv` and `test_b_add_s_integration/top.sv`
  gained explicit header-comment warnings: do not trust their `WIDTH=4`
  numeric output; use `WIDTH>=7` with a properly phase-separated seed pair
  if numeric accuracy is required.
- No RTL or test logic changed — this ADR is a documentation/scoping
  clarification, not a functional fix, because there is no functional fix
  available at `WIDTH=4` via seed selection.
- A future numerically-trustworthy example (e.g. a `WIDTH=8` variant of
  either integration test, using a verified half-period seed pair) is
  reasonable follow-up scope, not required to close this issue.
- The `DistinctEncoderSeeds`/`SelectLFSRDecorrelatedFromOperands`
  elaboration checks (ADR 0015/0018) are left as-is: they correctly catch
  the specific mistakes they were designed for (identical seed; identical
  polynomial width) and were never claimed to be a full independence
  proof. Extending them to reject `WIDTH<7` was considered and rejected —
  that would block legitimate protocol-only test uses of small widths
  (e.g. this repo's existing `WIDTH=2..16` sweeps, which test handshake
  correctness, not numeric accuracy) for no benefit, since the actual
  numeric-accuracy caveat is now documented at the call sites that matter.

### Confirmation

- Full width/seed characterization: `Tracked_FPGA_experiments`'
  `Stochastic_Blocks/results/decorrelation_seed_sweep.csv` (60 rows,
  `WIDTH` 2-16, best-available seed per width, 4 `(p1,p2)` pairs each).
- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean on both updated
  `top.sv` files (comment-only changes; same pre-existing warning counts as
  before this ADR, confirmed unchanged).
- `test_b_mult_s_integration` and `test_b_add_s_integration`: still 2/2
  passing each (unaffected — these tests verify structural correctness,
  which this ADR doesn't change).

## Affected Files

- `blocks/stocastic/verif/tb/test_b_mult_s_integration/top.sv`
- `blocks/stocastic/verif/tb/test_b_add_s_integration/top.sv`

## More Information

GitHub issue #3 is the original report; this ADR closes it with the
structural-threshold finding rather than a seed-value change. Full
characterization methodology and data live in the separate
`Tracked_FPGA_experiments` repo
(`Stochastic_Blocks/tb/decorrelation_seed_sweep.py`) and are promoted to
`~/wiki/fpga_stochastic_blocks/decision_logs/stochastic-v0-evidence-and-v1-candidate-2026-09-06.md`.
