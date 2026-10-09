---
status: Proposed
date: 2026-10-09
---

# 0027. Async FIFO storage depth must be a power of two, enforced in `dual_port_ram`

## Context and Problem Statement

The async FIFO (after Cummings, SNUG 2002 FIFO1) passes its read and write
pointers across clock domains in Gray code, so that a synchronizer sampling
the pointer mid-change sees either the old or the new value and never a
third one. That guarantee needs **exactly one bit to change on every
pointer increment, including the wrap from the last value back to zero.**
If several bits change together, each wire reaches the synchronizer flop at
a slightly different time, so a sample taken during the change can catch some
old bits and some new ones: a pointer value that was never on the counter.

`dual_n_bit_gray_counter` keeps a binary pointer of `DATA_WIDTH + 1` bits,
converts it with `binary_to_gray`, and takes the memory address from the low
`DATA_WIDTH` bits. The extra top bit distinguishes full from empty. The
pointer therefore counts through `2 * DEPTH` values before it wraps. Whether
the wrap is a single-bit change depends on `DEPTH`.

The question: does the FIFO's storage have to be a power-of-two depth, and
where is that enforced?

## Decision Drivers

- A clock-domain-crossing pointer that changes by more than one bit at any
  step can be mis-sampled; that is a silent hardware failure, not something
  simulation with ideal clocks will show.
- The library is tapeout-bound (see `CLAUDE.md`); invalid configurations
  should fail at elaboration, not at silicon.
- The pointer counter already derives the address width from `DATA_WIDTH`,
  so its depth is `2**DATA_WIDTH` by construction.

## Considered Options

1. **Require power-of-two depth**, enforced by an `MA_ASSERT_ELABOR` in the
   memory (and the FIFO).
2. **Allow any depth** and wrap the binary pointer at `2 * DEPTH` with a
   compare-and-reset.
3. **Allow any even pointer range** using a trimmed (offset) Gray sequence
   whose end-to-start transition is also a single bit.
4. **Allow any depth, round the storage up** to the next power of two
   internally.

## Decision Outcome

Chosen option: **1, require power-of-two depth**, because it is the only
option where the Gray conversion of a plain wrapping binary counter has the
single-bit-change property at the wrap with no extra logic.

Enumerating `gray(i) ^ gray((i + 1) mod 2*DEPTH)` over the full pointer range
(see Confirmation) shows one bit changes at every step, wrap included, only
when `2 * DEPTH` is a power of two. For every other depth tried, the wrap
step changes three bits. Example, `DEPTH = 6`: the pointer runs 0..11,
`gray(11) = 1110` and `gray(0) = 0000`, so three bits flip at once.

Why: standard (reflected) Gray code is symmetric about the midpoint of each
complete `2^k` block. With `M = 2^k - 1`, the mirror partner of index `i` is
`i ^ M`, and since shifts distribute over XOR,
`gray(i ^ M) = gray(i) ^ (M ^ (M >> 1)) = gray(i) ^ 2^(k-1)`: a code and its
mirror differ only in the top bit. Folding the sequence in half lays every
code on its partner. At `i = 0` the partner is the last code, so the wrap is
one bit. A truncated range ends before the mirror image of the start, so the
fold does not apply.

Converse: the wrap changes as many bits as `gray(n-1)` has ones
(`gray(0) = 0`). If `gray(n-1) = 2^j`, inverting the code
(`m = g ^ (g >> 1) ^ (g >> 2) ^ ...`) gives `n - 1 = 2^(j+1) - 1`, so `n` is
a power of two. Being even (and `n = 2 * DEPTH` always is) does not help: a
closed one-bit-per-step loop needs an even length, but that is necessary,
not sufficient.

- **Option 2** keeps a non-power-of-two wrap but the wrap is exactly the step
  that breaks the Gray property; the pointer seen by the other domain can
  take a value that was never on the pointer. Rejected on correctness.
- **Option 3** is a known technique (a window cut from the middle of a longer
  Gray sequence), but it needs offset logic on both pointers and a different
  full/empty comparison, and was not evaluated here. Rejected for now on
  complexity; revisit if a non-power-of-two depth is ever required.
- **Option 4** hides the rounding. A requested depth of 10 would silently
  become 16 and use more memory than the caller asked for; the explicit check
  makes the caller choose.

### Consequences

- Depths available are 2, 4, 8, 16, ... Depth 1 is also rejected (separate
  `ValidDepth` check): `$clog2(1)` is 0 and gives a `[-1:0]` address port.
- A FIFO that needs, say, 10 entries must use 16 and waste the rest. For a
  block RAM target the waste is usually free, since blocks come in fixed
  sizes.
- The check lives in `dual_port_ram`, which is the FIFO's storage. The RAM on
  its own does not need a power-of-two depth, so reusing it elsewhere inherits
  a constraint that comes from the FIFO. If that becomes a problem, move the
  check into the FIFO and relax the RAM.
- This reasoning covers **depth only**. It says nothing about `DATA_WIDTH`;
  the memory's current power-of-two *width* check (`Powerof2DataWidth`) is not
  justified by this ADR and needs its own reason or should be removed.
- The Gray property holds for the pointer range, not only the address. That
  is why the pointer has `DATA_WIDTH + 1` bits and why `2 * DEPTH` is the
  quantity that has to be a power of two (equivalent to `DEPTH` being one).

### Confirmation

Pointer-wrap enumeration (Python, run 2026-10-09). `n = 2 * DEPTH`; for each
`i`, count the bits in `gray(i) ^ gray((i + 1) % n)`, with `gray(x) = x ^ (x >> 1)`:

```
depth= 2 pointer range 0.. 3 max bits changed per step=1 (wrap 3->0: 1)
depth= 3 pointer range 0.. 5 max bits changed per step=3 (wrap 5->0: 3)
depth= 4 pointer range 0.. 7 max bits changed per step=1 (wrap 7->0: 1)
depth= 5 pointer range 0.. 9 max bits changed per step=3 (wrap 9->0: 3)
depth= 6 pointer range 0..11 max bits changed per step=3 (wrap 11->0: 3)
depth= 8 pointer range 0..15 max bits changed per step=1 (wrap 15->0: 1)
depth=10 pointer range 0..19 max bits changed per step=3 (wrap 19->0: 3)
depth=12 pointer range 0..23 max bits changed per step=3 (wrap 23->0: 3)
depth=16 pointer range 0..31 max bits changed per step=1 (wrap 31->0: 1)
```

Elaboration checks in `dual_port_ram` (Verilator 5.052 `--lint-only`,
`-GDEPTH=<d> -GDATA_WIDTH=8`): depths 0 and 1 trigger `ValidDepth`; depth 0
also triggers `Powerof2Addr`; depth 6 triggers `Powerof2Addr`; depths 2 and 8
pass.

Not yet done: the FIFO itself, a cocotb test of the RAM, and a formal proof
of the pointer crossing. This ADR stays `Proposed` until the FIFO is built
and the Gray-step property is proven on its actual pointers.

## Affected Files

- `blocks/basic/rtl/dual_port_ram.sv`
- `blocks/basic/rtl/dual_n_bit_gray_counter.sv`
- `blocks/basic/rtl/axis_async_fifo.sv` (in progress)

## More Information

- C. E. Cummings, "Simulation and Synthesis Techniques for Asynchronous FIFO
  Design", SNUG 2002, FIFO1 (the counter cites Figure 4, p. 8).
- [0001](0001-elaboration-check-mechanism.md): `MA_ASSERT_ELABOR` mechanism.
- Open: `MA_ASSERT_ELABOR` uses `$fatal` while ADR 0001 specifies `$error`
  (issue #17); parameter-default convention (issue #18).
