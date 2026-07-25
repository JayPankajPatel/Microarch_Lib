---
status: accepted
date: 2026-07-25
---

# 0002. `TAPS_LUT` correctness is established by algebraic primitivity checking, not by trusting the source table

## Context and Problem Statement

`galois_lfsr.sv`'s `TAPS_LUT` is a 65-entry table (indices 0-64, one entry
per supported `WIDTH`) of 64-bit tap-mask constants used to build a
parameterized Galois LFSR. A wrong entry doesn't cause a compile error, a
lint warning, or even a functional simulation failure in the ordinary
sense — it just produces an LFSR whose output cycle is shorter than the
maximal `2^WIDTH - 1`, which is silently wrong unless someone specifically
checks the cycle length. This is exactly the kind of bug that matters more
heading toward tapeout than in an FPGA iteration loop, where it would be
caught eventually.

## Decision Drivers

- The check needs to cover the full supported range, `WIDTH` 2 through 64 —
  spot-checking a handful of widths and assuming the rest are fine is not
  good enough once one spot-check already turned up a wrong entry.
- Brute-force simulating every possible state is only tractable for small
  widths; `2^64` states cannot be enumerated.

## Considered Options

1. Trust the original table as received, no verification.
2. Brute-force simulate the LFSR for each width and count unique states
   until a repeat, comparing against the expected `2^WIDTH - 1`.
3. Algebraic primitivity check: represent one LFSR step as a `WIDTH x WIDTH`
   matrix `M` over GF(2), and test whether `M`'s multiplicative order is
   exactly `2^WIDTH - 1` (i.e. `M` is primitive) via matrix exponentiation
   by repeated squaring, checking `M^(2^WIDTH-1) == I` and
   `M^((2^WIDTH-1)/p) != I` for every prime factor `p` of `2^WIDTH-1`.

## Decision Outcome

Chosen option: **3, algebraic primitivity checking**, because it is the
only one of the three that is both rigorous and tractable across the full
`WIDTH` range. Before trusting it, it was cross-validated against every
width already confirmed by brute-force simulation (widths 4, 5, 6, 7, 8, 10
confirmed correct; widths 3, 12, 16 confirmed wrong) — the algebraic check
reproduced every one of those results exactly, which is what justified
trusting it for the untested widths.

Running it across all 65 entries found **28 of 63 checked widths (2 through
64) had non-primitive masks** — far worse than the initial 3-of-9 sample
suggested. Valid replacement masks were found for all 28 via search (small
widths: deterministic scan in increasing order; large widths: randomized
search), each replacement independently re-verified with the same
primitivity check before being written into the table.

**Sparsity note:** the replacement search initially found *a* valid
primitive mask per width without optimizing for tap count. This matters
because every set bit in a tap mask is a real XOR gate in the feedback
network — every other (already-correct) entry in the table uses 2-4 taps,
while some randomly-found replacements needed 25-29. This has no timing
impact in this design specifically (see Consequences), but has a real,
avoidable area/power/FPGA-utilization cost. Future replacement searches
should bias toward low Hamming-weight candidates (trying 2-tap, then
3-tap, etc. before falling back to denser masks) rather than accepting the
first primitive candidate found.

### Consequences

- More taps means more area and more dynamic power (each tap is one XOR
  gate), scaling with however many instances of this LFSR end up
  instantiated in a larger design.
- More taps does **not** meaningfully affect critical-path timing in this
  specific implementation: the feedback bit (`q[0]`) is broadcast in
  parallel to every tap position (`q[i+1] ^ (q[0] & mask[i])`), so the
  logic depth from `q[0]` to any bit's next-state input is exactly one XOR
  gate regardless of tap count. The only secondary cost of more taps is
  increased fanout on `q[0]`, handled by ordinary synthesis buffering.
- On the target FPGA, LUT/slice utilization is the more direct proxy for
  "tap count cost" than gate count is; stochastic-computing designs are
  already utilization-hungry, so this compounds if the LFSR is replicated
  across many parallel SC streams.

### Confirmation

The algebraic check's correctness was established by exact agreement with
every previously brute-force-simulated width before being trusted further
(see Decision Outcome). After applying all 28 corrections to the table, 7
of the corrected widths (2, 3, 12, 13, 14, 16, 19) were additionally
confirmed by building and running the actual RTL (not just the Python
model) through Verilator, each reaching exactly `2^WIDTH - 1` unique states
before repeating — including a full 524,287-state run at `WIDTH=19`.

## Affected Files

- `blocks/stocastic/rtl/galois_lfsr.sv` (`TAPS_LUT` localparam, 28 of 65
  entries corrected)

## More Information

None.
