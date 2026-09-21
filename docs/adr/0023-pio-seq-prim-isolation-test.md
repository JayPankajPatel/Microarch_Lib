---
status: accepted
date: 2026-09-21
---

# 0023. `pio_seq_prim` is imported as an isolated block and restructured to the Gaisler two-process style to localize a fabric-level bug, not because its own logic was suspected first

## Context and Problem Statement

`pio_seq_prim` is a PIO-style programmable sequencer BEL (programmable
instruction sequencer driving a UART TX pin) developed in a sibling project,
`Tracked_FPGA_experiments/FABulous_work/fabulous-v2/fabric_protocol_emulator_proj`
(the Jane Street Protocol Emulator ASIC competition entry), where it is
wired into a real FABulous FPGA fabric, routed through a real switch matrix,
and driven by a real generated bitstream. After fixing an unrelated
combinational-loop bug in that fabric's edge-tile switch matrices and a
disconnected top-level wrapper bug, a UART-TX test program still showed no
activity at all through the full fabric flow: `busy` never asserted, `tx`
never toggled, across a 50µs/5000-cycle simulation window in both Verilator
and iverilog, well past when the program should have completed.

At that point there were two live hypotheses, with no evidence yet pointing
at either: a real bug in `pio_seq_prim`'s own RTL, or a fabric-integration
problem (routing, `ConfigBits` delivery, bitstream generation, timing of
`rst_n`/`start` relative to the fabric's own reset/config-load sequence).
Debugging further inside the full fabric sim would conflate both possible
fault domains at once. This repo (`Microarch_Lib`) already has exactly the
isolated-block/cocotb infrastructure needed to test the primitive alone,
with none of the fabric machinery in the loop.

## Decision Drivers

- Need to determine which of the two fault domains (primitive RTL vs.
  fabric integration) the bug is actually in, before spending more time
  debugging either one blind.
- This repo's own house convention (`CLAUDE.md`, ADR 0007) requires
  FSM-shaped RTL with several pieces of interacting registered state to use
  the Gaisler two-process style, not the single-`always`-block,
  multiple-separately-assigned-registers style `pio_seq_prim` originally
  used (copied as-is from the sibling project, which has no equivalent
  convention). ADR 0007's own history is directly relevant: restructuring
  `binary_stochastic_converter` to two-process style is what surfaced two
  real FSM bugs that the original nested-`if` style was hiding.

## Considered Options

1. Debug `pio_seq_prim` only inside the full FABulous fabric simulation
   (Verilator/iverilog against the generated bitstream), without isolating
   it.
2. Copy `pio_seq_prim` into this repo as a new block, write an isolated
   cocotb test against it directly (no fabric, no switch matrix, no
   bitstream loader), and restructure it to this repo's two-process
   convention while doing so.
3. Isolate the primitive with a quick ad hoc debug testbench (raw
   `iverilog`/`vvp`, hierarchical `dut.pc`/`dut.x` signal peeking) without
   adopting this repo's block layout or FSM style conventions.

## Decision Outcome

Chosen option: **2**, because it cleanly separates the two fault domains
(this repo's isolated test proves or disproves the primitive's own logic
independent of anything fabric-related) and because the primitive is
FSM-shaped enough (`pc`, `x`, `waiting`, `pin_out`, `running`, `shift_step`,
plus the free-running `div_cnt` divider and `shreg` shift register -- more
than "a couple" of interacting registered fields) that this repo's own
house convention requires the two-process form regardless of whether it
was the actual bug.

Option 1 was rejected: continuing to debug inside the full fabric sim
cannot distinguish "the primitive's logic is wrong" from "the primitive
never receives the inputs/config it expects," and every fabric-level
iteration costs a full `run_FABulous_fabric` + `compile_design` cycle
(HDL regen, synth, place-and-route, bitgen) instead of a sub-second cocotb
run.

Option 3 was rejected after being tried first and immediately reverted:
hierarchical signal-peeking (`dut.pc.value`, `dut.shreg.value`, etc.) in an
ad hoc testbench is not this repo's convention -- every existing test here
(`test_galois_lfsr.py`, etc.) verifies purely through the module's public
ports, and skipping the two-process restructuring would have meant
debugging the exact original nested-`if` structure ADR 0007 already
identified as bug-prone, in a repo that exists specifically to hold RTL to
a higher bar before tapeout.

### Consequences

- `pio_seq_prim.sv` now lives at `blocks/pio_seq/rtl/pio_seq_prim.sv`,
  restructured into the `r`/`rin` two-process form (single `always_comb`
  computing `rin` from `r`, defaulting `rin = r`; single `always_ff` doing
  only the reset assignment and `r <= rin`), with an `` `MA_ASSERT_ELABOR ``
  check on `NoConfigBits == 80` and an explicit, commented
  `verilator lint_off/on UNUSEDSIGNAL` waiver on `operand[4]` (reserved by
  the ISA's 5-bit operand field for a future opcode; no current opcode uses
  it).
- One lint-blocking bug was fixed as part of the port, unrelated to the
  restructuring itself: the original `pc <= {1'b0, operand[3:0]};` in the
  `JMP_XDEC` branch assigns a 5-bit value into 4-bit `pc`, tripping
  Verilator's `WIDTHTRUNC` under this repo's strict lint (silent/implicit
  under the sibling project's toolchain, since the truncated leading zero
  bit is always harmless). Fixed to `pc <= operand[3:0];`, functionally
  identical.
- **The restructuring did not find a bug.** The two-process rewrite
  produces bit-identical behavior to the original nested-`if` version
  against the same isolated test (confirmed by running the test against
  both forms before finalizing) -- unlike ADR 0007's `binary_stochastic_
  converter` case, this primitive's original structure, while against house
  style, was not actually hiding an implicit-hold or unreachable-branch bug.
- **The real fabric-level symptom (busy never asserting) is therefore
  confirmed NOT to be a `pio_seq_prim` RTL bug.** The isolated test proves
  the primitive correctly runs a UART-TX program (asserts `busy`, produces
  the exact expected start/data/stop bit sequence, deasserts `busy` on
  `HALT`) when driven directly with the same `PROG`/`DIV`/`tx_data` values
  used in the fabric-level test design. The fault must be somewhere in the
  fabric integration: `ConfigBits` delivery (bitstream layout/frame
  addressing), routing correctness beyond what the FASM's routing-table
  text shows, or timing/sequencing of `rst_n`/`start` relative to the
  fabric's own reset and bitstream-load sequence in the full simulation.
  That is the next real debugging target in the sibling project, not this
  primitive's own logic.
- A one-time test bug was found and fixed while getting the isolated test
  green: the test's `symbols` capture list deduplicates consecutive-equal
  `tx` values (since a plain sample-every-cycle list depends on exactly how
  many cycles each bit holds, which varies with `DIV`), but the initial
  `EXPECTED_SYMBOLS` comparison target was not deduplicated the same way --
  `0xA5`'s bit pattern has two genuine back-to-back repeats (data bits 3-4
  are both 0; the last data bit and the stop bit are both 1), which
  deduplicate away in the observed capture but not in the naive expected
  list, producing a spurious mismatch on the first run. Fixed by
  deduplicating `EXPECTED_SYMBOLS` with the identical rule before comparing.

### Confirmation

`pixi run verilator --lint-only -Wall -Icommon/rtl blocks/pio_seq/rtl/pio_seq_prim.sv`
produces only the pre-existing, ADR-0004-documented `GENUNNAMED` warning
(from `` `MA_ASSERT_ELABOR ``'s conditional-generate expansion, same as
`counter.sv`/`galois_lfsr.sv`/`binary_stochastic_converter.sv`) -- no other
warnings.

`pixi run make` in `blocks/pio_seq/verif/tb/test_pio_seq_prim/` (cocotb +
Verilator) drives `pio_seq_prim` directly with `ConfigBits` set to the same
`PROG`/`DIV` values as the fabric-level `pio_seq2_uart_tx.v` test design
(`PROG = 72'hE04001834020674000`, `DIV = 8'h02`), pulses `start` with
`tx_data = 8'hA5`, and asserts both that `busy` asserts after `start` and
that the observed `tx` transition sequence exactly matches the expected
start/data/stop bit sequence for `0xA5`. Result: `TESTS=1 PASS=1 FAIL=0
SKIP=0`, `busy` asserted and the program completed (returned to idle) in 60
cycles.

## Affected Files

- `blocks/pio_seq/rtl/pio_seq_prim.sv` (new; ported from the sibling
  project's `Tile/PIO_SEQ2/pio_seq_prim.v`, restructured to two-process
  style, one lint-blocking width-truncation fixed)
- `blocks/pio_seq/verif/tb/common.mk` (new)
- `blocks/pio_seq/verif/tb/test_pio_seq_prim/Makefile` (new)
- `blocks/pio_seq/verif/tb/test_pio_seq_prim/test_pio_seq_prim.py` (new)
- `Bender.yml` (added `blocks/pio_seq/rtl/*.sv` to the source list)

## More Information

- Sibling project this isolates a bug for:
  `Tracked_FPGA_experiments/FABulous_work/fabulous-v2/fabric_protocol_emulator_proj`
  (Jane Street Protocol Emulator ASIC competition entry). The fabric-level
  wiki writeup of the combinational-loop bug this session also fixed:
  `~/wiki/fpga_tapeout/fabulous-narrow-fabric-edge-tile-combinational-loop-gotcha.md`.
- [ADR 0007](0007-gaisler-two-process-fsm-style.md) -- the two-process
  convention and the bug class it targets; this ADR's "no bug found" result
  is a useful negative data point alongside 0007's "found two bugs" result
  for the same restructuring technique.
