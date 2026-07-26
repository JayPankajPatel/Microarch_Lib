---
status: accepted
date: 2026-07-25
---

# 0005. `TAPS_LUT` uses the sparse (low Hamming-weight) replacement masks, confirmed by real LibreLane+sky130 PPA numbers

## Context and Problem Statement

ADR 0002 corrected 28 non-primitive `TAPS_LUT` entries in `galois_lfsr.sv`,
but the first replacement search found *a* valid primitive mask per width
without optimizing for tap count -- some widths needed 25-29 taps where
every other (already-correct) entry uses 2-4. ADR 0002 reasoned
qualitatively that this costs area/power (each tap is an XOR gate) but not
timing, and recommended a sparser follow-up search, which was then run
(commit `low Hamming Taps added`) and added behind an
`` `ifdef LFSR_SPARSE_TAPS `` alongside the original denser table.

This issue (github.com/JayPankajPatel/Microarch_Lib/issues/1) was to
replace that qualitative "more taps costs area/power" reasoning with real
numbers from an actual sky130 synthesis + place-and-route flow, and decide
whether to keep both tables or collapse to one.

## Decision Drivers

- ADR 0002's own Consequences section says timing shouldn't be affected
  (the feedback bit `q[0]` fans out in parallel to every tap position), so
  the interesting question is purely area/power, not speed.
- CLAUDE.md explicitly disallows leaving feature-flag scaffolding in place
  once its purpose (in this case, the pending comparison) is resolved --
  the `` `ifdef `` fork needed to collapse to one table once numbers were in.

## Considered Options

1. Keep both tables behind `` `ifdef LFSR_SPARSE_TAPS `` indefinitely, decide
   per-instantiation.
2. Run the numbers, then adopt the sparse table unconditionally and delete
   the dense one.
3. Trust ADR 0002's qualitative reasoning without measuring, and adopt
   sparse anyway.

## Decision Outcome

Chosen option: **2**. Real numbers were obtained (see Confirmation) and
they confirm the qualitative prediction cleanly enough that keeping two
tables around no longer serves a purpose -- option 1 is exactly the kind
of stale scaffolding CLAUDE.md says to collapse, and option 3 would have
left the claim unverified, which was the entire point of this issue.

### Consequences

- `TAPS_LUT` in `galois_lfsr.sv` now contains only the sparse masks; the
  denser corrected-but-unoptimized table from ADR 0002 no longer exists in
  the RTL (still recoverable from git history at the commit tagged "low
  Hamming Taps added" if ever needed again).
- Area wins scale with instantiation count and `WIDTH`; the full benefit
  will vary by width (see More Information for which widths actually
  differ between the two tables -- most don't).
- Power difference is within the noise of a vectorless STA power estimate
  at default switching activity, not simulation-driven dynamic power --
  see Confirmation. This does not contradict ADR 0002; it's consistent
  with the fanout structure described there (one XOR gate of logic depth
  regardless of tap count) meaning fewer taps mostly removes gates from a
  parallel structure rather than off a switching critical path.

### Confirmation

**Primitivity of the adopted (sparse) table was independently re-verified
in this session, not just inherited from the commit that added it.**
Deleting ADR 0002's dense table removes its RTL-verified fallback for 4 of
the 7 widths ADR 0002 confirmed by Verilator (13, 14, 16, 19 all changed
between the two tables), so the sparse replacements needed their own
confirmation before being trusted as the sole table:

- Programmatically diffed the two tables (before either was deleted) to
  get the real set of widths that differ: **13, 14, 16, 19, 24, 26, 27,
  30, 32, 34, 38, 42, 45, 46, 48, 50, 51, 53, 54, 56, 60, 61, 62, 63, 64**
  (all other widths 2-64 are byte-identical between the two tables).
- Ran the same GF(2) transition-matrix primitivity check ADR 0002 used
  (`M^(2^W-1) == I` and `M^((2^W-1)/p) != I` for every prime factor `p`)
  against all 25 differing widths' sparse masks: all 25 came back
  primitive.
- Cross-checked that against brute-force cycle enumeration for the four
  smaller widths (13, 14, 16, 19): all four reached exactly `2^W-1`
  states, matching the matrix check.
- Additionally ran the actual updated RTL (`galois_lfsr.sv` post-edit,
  parameterized per width) through Verilator for those same four widths,
  counting unique `out` values per clock until the sequence returned to
  its start state: 13 -> 8191, 14 -> 16383, 16 -> 65535, 19 -> 524287,
  each exactly `2^W-1` -- the same real-hardware-run confirmation
  standard ADR 0002 applied to the table it verified.
- Widths 24-64 were not brute-forced (intractable) but are covered by the
  matrix check, same as ADR 0002 did for its own out-of-range-for-
  brute-force widths.

PPA was measured via LibreLane v3.0.3 + sky130A (PDK version
`8afc8346a57fe1ab7934ba5a6056ea8b43078e71`, `sky130_fd_sc_hd`), synthesis
through post-route STA (`OpenROAD.STAPostPNR`, i.e. real placement,
routing, and RC-extracted STA/power -- not synthesis-only estimates). GDS
streamout/DRC/LVS signoff steps were skipped as out of scope for a PPA
comparison. Both runs used `FP_SIZING: relative` with identical
`FP_CORE_UTIL`/`PL_TARGET_DENSITY` so the floorplan reflects each
variant's actual cell count rather than a fixed die size masking the
difference.

Design under test: a `WIDTH=64` instantiation of `galois_lfsr` (wrapped in
`blocks/stocastic/pnr/lfsr64_wrapper.sv`), the width with the largest gap
between the two tables (dense mask `64'h268A2A32F60F159C`, ~30 set bits,
vs. sparse mask `64'h4040000000000020`, 3 set bits). Confirmed via yosys
synth `stat` before running PnR: 29 `$_XOR_` cells for the dense variant,
3 for the sparse variant, matching the expected tap counts exactly.

Post-route results (`blocks/stocastic/pnr/{dense,sparse}/runs/`,
`final/metrics.json`):

| Metric | Dense (29 taps) | Sparse (3 taps) | Delta |
|---|---|---|---|
| `design__core__area` (µm²) | 5172.46 | 4264.09 | -17.6% |
| `design__die__area` (µm²) | 8029.92 | 6723.18 | -16.3% |
| `design__instance__count__stdcell` | 332 | 277 | -16.6% |
| combinational cell area (µm²) | 471.70 | 48.80 | -89.7% |
| combinational cell count | 29 | 3 | -89.7% |
| `power__total` (W) | 6.4056e-4 | 6.4004e-4 | -0.08% |

`design__instance__count` (712 -> 535, -24.9%) is not listed above because
it's dominated by fill cells (380 -> 258) and tap cells (70 -> 52), both a
function of the floorplan's die area rather than independent evidence of
the design's actual content -- it moves with the area result rather than
verifying it separately. `design__instance__count__stdcell` isolates the
design's own logic/sequential cells and is reported instead.

The area and cell-count reduction confirms ADR 0002's prediction directly.
The power delta (<0.1%) is inside the noise of OpenSTA's vectorless
default-activity power model and should not be read as a measured dynamic
power saving -- with only 26 fewer XOR gates on an already tiny design,
this is an expected result, not a failed measurement.

## Affected Files

- `blocks/stocastic/rtl/galois_lfsr.sv` (`TAPS_LUT` localparam: dense
  table and `` `ifdef `` fork removed, sparse table is now the only one)
- `blocks/stocastic/pnr/lfsr64_wrapper.sv` (new: fixed-`WIDTH=64` synthesis
  harness used for this comparison; not library RTL, kept out of `rtl/`
  so the pre-commit lint hook glob doesn't pick it up)
- `blocks/stocastic/pnr/dense/config.json`, `blocks/stocastic/pnr/sparse/config.json`
  (new: the two LibreLane configs used for this comparison)
- `.gitignore` (new entry: `blocks/*/pnr/*/runs/` -- LibreLane run
  artifacts are regenerable and were ~85MB per run)
- `docs/adr/0002-taps-lut-correctness-methodology.md` (Consequences section
  now points here for the measured, rather than qualitative, area/power
  claim)

## More Information

The two tables are byte-identical for most widths (2-12, 15, 17, 18,
20-23, 25, 28, 29, 31, 33, 35-37, 39-41, 43, 44, 47, 49, 52, 55, 57-59) --
only the widths ADR 0002 flagged as needing a denser fallback actually
differ, and this measurement was taken at the single width (64) with the
largest gap. Widths with a smaller tap-count gap will show a
proportionally smaller area effect; this was not re-measured per width, as
the fanout/timing argument in ADR 0002 and the structural relationship
between tap count and XOR gate count apply uniformly.
