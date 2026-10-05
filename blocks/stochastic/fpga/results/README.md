# SC vs. binary 4-bit multiply — Zybo Z7-10 area/power comparison

Vivado 2024.1, target `xc7z010clg400-1` (Zybo Z7-10), 125 MHz clock constraint
(`constraints/zybo_z7.xdc`). Both designs: identical wrapper style (free-running
operand counters, `clk`-only interface, no external reset pin — see each
`rtl/*_top.sv`'s header comment), so the only real difference is the multiply
architecture itself.

Reproduce: `vivado -mode batch -source scripts/build_and_report.tcl -tclargs
<sc_multiply_top|binary_multiply_top> results/<name>` (needs
`LD_LIBRARY_PATH` pointed at Vivado's bundled `libtinfo.so.5` — see note at
the bottom).

## Results (post-route)

| Metric | `sc_multiply_top` (SC, WIDTH=4) | `binary_multiply_top` (binary, 4x4) |
|---|---|---|
| Slice LUTs | 21 | 10 |
| Slice Registers | 40 | 12 |
| DSP48 slices | 0 | 0 (both stayed in LUT fabric) |
| Total on-chip power | 0.094 W | 0.109 W |
| — Dynamic power | 0.001 W | 0.016 W |
| — Static power | 0.093 W (identical, device baseline) | 0.093 W |
| WNS @ 125 MHz | 3.989 ns (≈249 MHz max) | 5.509 ns (≈401 MHz max) |

## Headline finding: SC is *larger*, not smaller, at this precision

Contrary to the naive "SC multiply = one AND gate, must be cheaper" framing:
**the SC design used ~2.1x the LUTs and ~3.3x the flip-flops of the plain
binary multiplier.** This is not a bug or an unfair comparison — it's the
correct, expected outcome at this scale. SC's actual arithmetic core (AND-gate
multiply) is trivial, but running it requires the full SNG infrastructure:
two LFSR-based encoders (each with their own LFSR + counter + control FSM) and
a decoder (accumulator + control FSM), while a plain 4x4 binary multiply is
cheap enough on its own (10 LUTs) that Vivado didn't even reach for a DSP48
block — the encode/decode overhead dominates the comparison at 4-bit
precision, not the multiply itself.

This matches the standard characterization in stochastic-computing
literature: SC's area/power advantage over binary arithmetic typically only
emerges at **larger operand widths or more complex multi-operand functions**
(e.g. a MAC/dot-product across several inputs sharing one SNG's amortized
cost), not a single small standalone multiply. This is a real, useful
negative result for the paper — it argues for measuring at wider precision
and/or a full MAC chain (matching the wiki roadmap's actual headline metric,
INT4 MACs/mm², not a bare multiplier) to find where SC's area crossover point
actually is, rather than assuming 4-bit is representative.

## Dynamic power: the one place SC did win, with a caveat

SC's *dynamic* power came in 16x lower than binary (0.001 W vs. 0.016 W) —
consistent with SC's core logic being mostly regular, low-fanout shift/count
toggling rather than a binary multiplier's higher-activity carry/partial-
product structure. This is a real, plausible, and reportable difference, but:

**Caveat — both power numbers are Vivado's vector-less estimate (`Confidence
Level: Medium` in both `*_power.rpt` files), not measured from real switching
activity.** Vector-less estimation assumes generic default toggle rates per
node, not this design's actual behavior — and SC's genuinely much slower
effective throughput (one multiply result every `2**WIDTH-1` = 15 cycles,
vs. one every cycle for the combinational binary multiplier) is exactly the
kind of behavior a vectorless estimate can get wrong in either direction. A
trustworthy power comparison needs a post-implementation timing simulation
with a real testbench driving the design, producing a SAIF file for
`report_power` to consume. Not done here — flagged as follow-up scope, not
silently assumed correct.

## The latency/throughput asymmetry this table doesn't show

`sc_multiply_top` produces one (approximate) result every `2**WIDTH-1 = 15`
clock cycles; `binary_multiply_top` produces one (exact) result every cycle.
Any statement drawn from this table ("SC uses more area," "SC's dynamic power
is lower") must be read together with that ~15x throughput gap — it is the
standard SC area-for-latency tradeoff, not something either design hides.
None of the numbers above normalize for it (e.g. "area per multiply-per-
second"); doing that normalization is straightforward from this data but was
not pre-computed here to avoid asserting a specific framing before deciding
how the paper wants to present it.

## Known accuracy caveat (separate from this area/power comparison)

`sc_multiply_top`'s encoder seeds (`INIT_SEED=1` and `INIT_SEED=5`) were
chosen to be the best available phase separation at WIDTH=4 (see
`rtl/sc_multiply_top.sv`'s header comment), but per Microarch_Lib GitHub
issue #3, no fixed seed pair gives an accurate product estimate at WIDTH=4 —
the LFSR period (15 states) is too short relative to any useful sample count.
This doesn't affect the area/power numbers above (the same gates get
synthesized regardless of which seed constant is loaded), but means this
specific design's *numeric* output should not be trusted, only its resource
usage.

## Toolchain note

Vivado 2024.1 on this machine needs `libtinfo.so.5`, which isn't installed
system-wide (only `libtinfo.so.6` is). Vivado bundles a compatible one:

```
export LD_LIBRARY_PATH="/home/jay/Programs/AMD/Vivado/2024.1/lib/lnx64.o/Rhel/9:$LD_LIBRARY_PATH"
```
