---
status: accepted
date: 2026-08-15
---

# 0006. `galois_lfsr.sv`'s distributed-tap recurrence reads `TAPS_LUT` mirrored (`TAPS_LUT[WIDTH][WIDTH-1-i]`, not `[i]`)

## Context and Problem Statement

`galois_lfsr.sv` is meant to implement a real Galois-configuration LFSR:
feedback sourced from one end of the register (`q[WIDTH-1]`) and XORed
directly into *multiple* next-state bits as data shifts through, matching
the standard schematic (flip-flops in series, XOR gates between adjacent
stages gated by tap coefficients, last stage's output feeding the first
stage's input unconditionally). Two earlier structural attempts at this
file did not actually achieve that: the version at HEAD used a modular
rotate (`q[(i+1) % WIDTH]`) conditionally XORed with `q[0]`, and an
intermediate rewrite computed `feedback` as a single external
reduction-XOR over all tapped bits then shifted that one bit in at
`q[0]` -- structurally a Fibonacci (external-XOR) LFSR despite the
module's name, confirmed by reading pylfsr's own `next()` implementation
(`.pixi/envs/default/lib/python3.12/site-packages/pylfsr/pylfsr.py`) and
finding its `fibonacci` branch, not its `galois` branch, was the one that
matched this RTL's actual recurrence bit-for-bit.

The current recurrence finally has the right shape:

```systemverilog
localparam n = WIDTH;
logic [n-1:0] q;
logic feedback;
assign feedback = q[n-1];
always_ff @(posedge clk or negedge rst_n) begin
  if (!rst_n) q <= INIT_SEED;
  else begin
    q[0] <= feedback;
    for (int i = 1; i < n; i = i + 1)
      q[i] <= q[i-1] ^ (feedback & TAPS_LUT[n][n-1-i]);
  end
end
```

But it introduced a new, silent failure mode: reading `TAPS_LUT` at the
*unmirrored* index (`TAPS_LUT[n][i]`, i.e. reusing the mask exactly as
ADR 0002/0005 verified it) produces a **non-maximal** LFSR. This doesn't
show up as a compile error, lint warning, or simulation crash -- the
same silent-failure class ADR 0002 already called out for a wrong tap
entry -- it just produces a shorter output cycle than `2^WIDTH-1`. Direct
Python simulation of both forms at `WIDTH=4` (`TAPS_LUT[4]=0x4`, i.e. bit
2 set) showed the concrete difference:

```
unmirrored (TAPS_LUT[n][i]):        [2, 4, 8, 5, 10, 1]       period = 6
mirrored   (TAPS_LUT[n][n-1-i]):    [2, 4, 8, 3, 6, 12, 11, 5, 10, 7, 14, 15, 13, 9, 1]   period = 15
```

`2^4-1 = 15`, so only the mirrored form is maximal-length.

## Decision Drivers

- Must cover the full supported `WIDTH` range (2-64), not just be
  spot-checked at one width -- same driver ADR 0002 used, for the same
  reason (a wrong tap is invisible without deliberately checking cycle
  length).
- Reuse the existing, already-verified-primitive `TAPS_LUT` (ADR
  0002/0005) rather than re-deriving 63 new masks from scratch, if
  possible to justify rigorously rather than just assuming it carries
  over.

## Considered Options

1. Leave `TAPS_LUT[n][i]` unmirrored (the state immediately after the
   Fibonacci-to-Galois rewrite).
2. Read the mask mirrored, `TAPS_LUT[n][n-1-i]`, reusing the existing
   table unchanged.
3. Regenerate `TAPS_LUT` from scratch under the new recurrence's own
   indexing (a fresh primitive-mask search per width, as ADR 0002 did
   originally).

## Decision Outcome

Chosen option: **2, mirror the read index, reuse `TAPS_LUT` unchanged**,
because option 1 is empirically non-maximal (shown above, and confirmed
to fail broadly, not just at `WIDTH=4` -- see Confirmation), and option 3
is unnecessary once option 2 is shown correct: it would repeat ADR
0002/0005's expensive search-and-verify process for no benefit.

Why mirroring is the correct fix, not just an empirically-found
workaround: `TAPS_LUT`'s bit index has a fixed, unchanged meaning --- bit
`b` always means polynomial term `x^(b+1)` (this is exactly what
`fpoly_for()` in the testbench encodes: `taps = [i+1 for i in range(width)
if bit i set]`, and that construction did not need to change). What
changed is *where* the Galois circuit needs each term's tap physically
placed: working through pylfsr's own galois algorithm structurally
(`feedbackbit = state[0]`; `state = roll(state, -1)`; `state[k-1] ^=
feedbackbit` for each `k` in `fpoly[1:]`), a term of degree `k` lands at
register stage `WIDTH-k` -- i.e. **high-degree taps sit close to the
feedback re-entry point, low-degree taps sit at the far end**, the
reverse of `TAPS_LUT`'s ascending-degree-with-ascending-bit-index
convention. Reading the mask at `[n-1-i]` instead of `[i]` corrects for
exactly that ascending-vs-descending mismatch; it is a permutation
(bit-reversal) similarity transform on the per-width transition matrix,
which preserves the matrix's characteristic polynomial and therefore its
multiplicative order -- so a table already shown primitive under one
reading is expected to remain primitive under the mirrored reading. This
is why option 2 was expected to work before broad verification, not just
after.

### Consequences

- Every next-state bit now genuinely depends on `feedback` through a
  distributed XOR network (the real Galois shape), not just `q[0]` --
  matches the schematic this module was always meant to implement.
- `TAPS_LUT` itself required no changes; only the read-index expression
  in `galois_lfsr.sv` and the corresponding index convention in the
  cocotb reference model changed.
- The testbench's `state_to_int()`/`initstate` construction needed a
  matching fix, independent of but related to this one: pylfsr's `galois`
  branch sources feedback from `state[0]` and shifts new bits into
  `state[-1]`, the opposite end from this RTL's `q[WIDTH-1]`-sourced,
  `q[0]`-entry convention, so `state[j]` must map to `q[WIDTH-1-j]`, not
  `q[j]`. `fpoly_for()`'s tap-list construction did *not* need a matching
  reversal -- the two reversals (mask-read mirroring in the RTL, and
  state-index mirroring in the reference model) independently cancel out
  algebraically for the tap-list computation specifically, verified
  empirically (see Confirmation) rather than assumed.
- ADR 0002 and ADR 0005's primitivity claims, made against the earlier
  (non-Galois) recurrence, do not automatically transfer -- they are
  re-established here for the current recurrence rather than silently
  inherited.
- The fanout/timing claim from ADR 0002 (feedback bit fans out in
  parallel to every tap, so logic depth is one XOR gate regardless of tap
  count) carries over unchanged: the current recurrence still broadcasts
  `feedback` combinationally to every stage's conditional XOR in the same
  parallel shape, only the source register and per-stage wiring changed.
  No new PPA run was needed; ADR 0005's numbers (tap count and logic
  depth per width, unaffected by this change) still apply.

### Confirmation

**Primitivity, algebraic, full range.** The GF(2) transition matrix for
the corrected (mirrored) recurrence was built for all widths 2-64 and run
through the same multiplicative-order check ADR 0002 used
(`M^(2^W-1)==I`, `M^((2^W-1)/p)!=I` for every prime factor `p` of
`2^W-1`): **all 63 widths came back primitive**, no failures.

**Brute-force cross-check, real RTL, small widths.** The actual
corrected Verilog (not just the Python transition-matrix model) was run
through Verilator via the existing cocotb testbench's
`reaches_maximal_length_cycle` test for the historically spot-checked
widths, counting unique `out` values per clock until the sequence
returned to its start state:

| WIDTH | unique states before repeat | expected (`2^W-1`) |
|---|---|---|
| 2 | 3 | 3 |
| 3 | 7 | 7 |
| 4 | 15 | 15 |
| 12 | 4095 | 4095 |
| 13 | 8191 | 8191 |
| 14 | 16383 | 16383 |
| 16 | 65535 | 65535 |
| 19 | 524287 | 524287 |

All eight exactly matched the expected maximal period.

**Reference-model comparison, full range, constrained-random seeds.**
Separately, `matches_pylfsr_galois_reference` (the pylfsr-vs-DUT,
200-cycle, full-state-vector comparison, not just cycle-length) was run
via `pixi run make` for all 63 widths (2-64) x 3 random nonzero seeds
each (189 combinations total), using `EXTRA_ARGS="-GWIDTH=$w
-GINIT_SEED=${w}'d${s}"` (a sized-literal seed override -- an unsized
decimal `-GINIT_SEED=$s` was tried first and produced spurious
`WIDTHTRUNC`-promoted-to-error build failures unrelated to RTL
correctness, since Verilator's `-G` overrides don't infer the target
parameter's width from an unsized literal; the sized-literal form fixed
this cleanly). **189/189 passed.** Both `fpoly_for()`'s unreversed tap-list
construction and `state_to_int()`'s reversed state-index mapping were
validated together by this run, across every declared width and multiple
seeds per width, not just the single default seed used elsewhere.

This sweep also incidentally settles a separate open question about
`common/verif/ma_clkrst.py`'s `reset_dut()`: its trailing `await
RisingEdge(clk)` (after `rst_n` is deasserted) is a real functional clock
edge, raising a question of whether the DUT silently advances one step
ahead of the Python reference model before the comparison loop even
starts. If it did, the very first cycle-0 comparison would fail
deterministically every time (exactly the failure mode seen earlier in
this work when the state-index mapping was wrong) -- since all 189 runs
passed bit-exact from cycle 0 through cycle 199, this is empirical
evidence there is no such skew, without needing a dedicated test for it.

**Lint.** `pixi run verilator --lint-only -Wall -Icommon/rtl
blocks/stocastic/rtl/galois_lfsr.sv` produces only the pre-existing,
already-documented (ADR 0004) `GENUNNAMED` warnings from ``
`MA_ASSERT_INIT ``'s conditional-generate expansion -- no new warnings
from this change.

## Affected Files

- `blocks/stocastic/rtl/galois_lfsr.sv` (feedback/next-state recurrence
  rewritten to real Galois topology; `TAPS_LUT` values unchanged, only
  the read-index expression)
- `blocks/stocastic/verif/tb/test_galois_lfsr/test_galois_lfsr.py`
  (`state_to_int`/`initstate` construction reversed to match; added
  `reaches_maximal_length_cycle` as a complementary check --
  maximal-length alone can't prove the *intended* polynomial is wired
  up, since any primitive polynomial reaches full length, so it
  supplements rather than replaces the reference-model comparison)

## More Information

- ADR 0002 (`0002-taps-lut-correctness-methodology.md`) and ADR 0005
  (`0005-taps-lut-sparse-vs-dense-ppa.md`) verified `TAPS_LUT`'s
  primitivity against the pre-Galois recurrence; both now carry a pointer
  to this ADR noting the read index is mirrored under the current
  recurrence, though the per-width polynomial and primitivity result are
  unchanged.
