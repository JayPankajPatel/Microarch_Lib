"""Isolated test of pio_seq_prim.sv, driven directly (no FABulous fabric,
switch matrix, or bitstream loader in the loop) -- to determine whether a
UART-TX program that shows no activity (busy never asserts) when run through
the full fabric flow is a bug in this RTL itself, or somewhere in the fabric
integration (routing, ConfigBits delivery, bitstream generation) instead.
See Tracked_FPGA_experiments/FABulous_work/fabulous-v2/fabric_protocol_emulator_proj
for the fabric-level symptom this isolates.

# interface
# module pio_seq_prim #(
#     parameter integer NoConfigBits = 80
# ) (
#     input  wire       rst_n,
#     input  wire       start,
#     input  wire [7:0] tx_data,
#     output wire       tx,
#     output wire       busy,
#     input  dummy_carry_in,
#     output dummy_carry_out,
#     input  UserCLK,
#     input  [NoConfigBits-1:0] ConfigBits
# );
"""

import cocotb
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge
from ma_clkrst import reset_dut, start_clock

# ma_clkrst's drive()/clock_step() hardcode `dut.clk`; pio_seq_prim's clock
# port is `UserCLK`, so these are local equivalents following the same
# edge-timing discipline (see ma_clkrst.py's docstring for why this matters).


async def drive(dut, **values):
    await FallingEdge(dut.UserCLK)
    for name, val in values.items():
        getattr(dut, name).value = val


async def clock_step(dut):
    await RisingEdge(dut.UserCLK)
    await ReadOnly()

# Same PROG/DIV values as the fabric-level pio_seq2_uart_tx.v test design:
# PROG = {8'hE0, 8'h40, 8'h01, 8'h83, 8'h40, 8'h20, 8'h67, 8'h40, 8'h00}
# DIV  = 8'h02
PROG = 0xE0_40_01_83_40_20_67_40_00
DIV = 0x02
CONFIG_BITS = (DIV << 72) | PROG

TEST_BYTE = 0xA5
# start(0), data LSB-first, stop(1) -- same expected sequence documented
# against the fabric-level testbench.
_expected_bits = [0] + [(TEST_BYTE >> i) & 1 for i in range(8)] + [1]
# The observed capture below only records a symbol when tx *changes*
# (consecutive repeats collapse to one entry, since a plain sample-every-cycle
# list would otherwise depend on exactly how many cycles each bit holds for,
# which varies with DIV) -- so the expected sequence must be deduplicated the
# same way before comparing, or two genuine back-to-back repeats in
# _expected_bits (bits 3-4 of 0xa5 are both 0; the last data bit and the stop
# bit are both 1) would wrongly read as a mismatch.
EXPECTED_SYMBOLS = [v for i, v in enumerate(_expected_bits) if i == 0 or v != _expected_bits[i - 1]]


@cocotb.test()
async def uart_tx_program_runs_when_driven_directly(dut):
    dut.ConfigBits.value = CONFIG_BITS
    dut.dummy_carry_in.value = 0
    dut.start.value = 0
    dut.tx_data.value = TEST_BYTE

    start_clock(dut.UserCLK, period_ns=10)
    await reset_dut(dut.rst_n, dut.UserCLK, cycles=5)

    await drive(dut, start=1)
    await clock_step(dut)
    await drive(dut, start=0)

    symbols = []
    saw_busy = False
    n_cycles = 300
    cycles_run = 0
    for cycle in range(n_cycles):
        await clock_step(dut)
        cycles_run = cycle + 1
        busy = int(dut.busy.value)
        tx = int(dut.tx.value)
        saw_busy = saw_busy or bool(busy)
        if not symbols or symbols[-1] != tx:
            symbols.append(tx)
        if saw_busy and not busy:
            break

    cocotb.log.info(
        "observed %d/%d cycles, busy asserted=%s, tx transition sequence=%s",
        cycles_run,
        n_cycles,
        saw_busy,
        symbols,
    )

    assert saw_busy, (
        "busy never asserted after a start pulse -- matches the fabric-level "
        "symptom exactly, so this is a real bug in pio_seq_prim itself, not "
        "a fabric-integration issue"
    )
    assert symbols == EXPECTED_SYMBOLS, (
        f"tx transition sequence {symbols} != expected {EXPECTED_SYMBOLS} "
        f"for TEST_BYTE=0x{TEST_BYTE:02x}"
    )
