"""Cocotb tests for dual_port_ram.

Simple dual-port RAM: the write port is on wclk, the read port is on rclk,
and the read is registered (1-cycle latency, rdata holds while ren is low).
The two clocks have unrelated periods so the domains drift against each
other. Inputs are driven on a FallingEdge and registered outputs are read
after RisingEdge + ReadOnly, as in common/verif/ma_clkrst.py.
"""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

DATA_WIDTH = int(os.environ.get("DATA_WIDTH", "8"))
DEPTH = int(os.environ.get("DEPTH", "16"))
WCLK_NS = 10
RCLK_NS = 14


def start_clocks(dut):
    Clock(dut.wclk, WCLK_NS, unit="ns").start()
    Clock(dut.rclk, RCLK_NS, unit="ns").start()
    dut.wen.value = 0
    dut.ren.value = 0
    dut.waddr.value = 0
    dut.raddr.value = 0
    dut.wdata.value = 0


async def write_word(dut, addr, data):
    """Write one word: wen is high for exactly one wclk rising edge."""
    await FallingEdge(dut.wclk)
    dut.waddr.value = addr
    dut.wdata.value = data
    dut.wen.value = 1
    await RisingEdge(dut.wclk)
    await FallingEdge(dut.wclk)
    dut.wen.value = 0


async def read_word(dut, addr):
    """Present addr with ren high, return rdata after the next rclk edge."""
    await FallingEdge(dut.rclk)
    dut.raddr.value = addr
    dut.ren.value = 1
    await RisingEdge(dut.rclk)
    await ReadOnly()
    return int(dut.rdata.value)


def random_words(seed):
    rng = random.Random(seed)
    return [rng.randrange(1 << DATA_WIDTH) for _ in range(DEPTH)]


@cocotb.test()
async def read_back_every_address(dut):
    """Every address returns what was last written to it."""
    start_clocks(dut)
    model = random_words(seed=1)

    order = list(range(DEPTH))
    random.Random(2).shuffle(order)
    for addr in order:
        await write_word(dut, addr, model[addr])

    random.Random(3).shuffle(order)
    for addr in order:
        actual = await read_word(dut, addr)
        assert actual == model[addr], (
            f"addr {addr}: read {actual:#x}, expected {model[addr]:#x}"
        )


@cocotb.test()
async def overwrite_returns_latest_value(dut):
    """A second write to the same address replaces the first."""
    start_clocks(dut)
    first, second = 0x5A & ((1 << DATA_WIDTH) - 1), 0xA5 & ((1 << DATA_WIDTH) - 1)
    assert first != second

    await write_word(dut, 3, first)
    await write_word(dut, 3, second)
    actual = await read_word(dut, 3)
    assert actual == second, f"read {actual:#x}, expected {second:#x}"


@cocotb.test()
async def no_write_when_wen_low(dut):
    """With wen low, wclk edges with a new waddr/wdata must not write."""
    start_clocks(dut)
    keep, junk = 0x11 & ((1 << DATA_WIDTH) - 1), 0x22 & ((1 << DATA_WIDTH) - 1)
    assert keep != junk

    await write_word(dut, 5, keep)

    await FallingEdge(dut.wclk)
    dut.waddr.value = 5
    dut.wdata.value = junk
    dut.wen.value = 0
    for _ in range(3):
        await RisingEdge(dut.wclk)
        await FallingEdge(dut.wclk)

    actual = await read_word(dut, 5)
    assert actual == keep, f"read {actual:#x}, expected {keep:#x}"


@cocotb.test()
async def read_is_registered_and_holds(dut):
    """rdata changes one rclk edge after raddr, and holds while ren is low."""
    start_clocks(dut)
    a, b = 1, 2  # nonzero, distinct
    await write_word(dut, 1, a)
    await write_word(dut, 2, b)

    assert await read_word(dut, 1) == a

    # Registered: a new address alone must not change rdata before the edge.
    await FallingEdge(dut.rclk)
    dut.raddr.value = 2
    dut.ren.value = 1
    await Timer(1, unit="ns")
    assert int(dut.rdata.value) == a, "rdata changed before the rclk edge"
    await RisingEdge(dut.rclk)
    await ReadOnly()
    assert int(dut.rdata.value) == b

    # Hold: with ren low, rdata keeps the last loaded value, whatever raddr is.
    await FallingEdge(dut.rclk)
    dut.ren.value = 0
    dut.raddr.value = 1
    for _ in range(3):
        await RisingEdge(dut.rclk)
        await ReadOnly()
        assert int(dut.rdata.value) == b, "rdata changed while ren was low"
        await FallingEdge(dut.rclk)

    # Re-enable: the held address now loads.
    dut.ren.value = 1
    await RisingEdge(dut.rclk)
    await ReadOnly()
    assert int(dut.rdata.value) == a


@cocotb.test()
async def concurrent_write_and_read(dut):
    """Reads of committed addresses stay correct while writes continue."""
    start_clocks(dut)
    model = random_words(seed=4)
    committed = []

    async def writer():
        for addr in range(DEPTH):
            await write_word(dut, addr, model[addr])
            # Half a wclk later, so a reader can never sample the same edge
            # as the write (a same-address same-time access is undefined).
            await FallingEdge(dut.wclk)
            committed.append(addr)

    write_task = cocotb.start_soon(writer())
    for i in range(DEPTH):
        while len(committed) <= i:
            await RisingEdge(dut.rclk)
        addr = committed[i]
        actual = await read_word(dut, addr)
        assert actual == model[addr], (
            f"addr {addr}: read {actual:#x}, expected {model[addr]:#x}"
        )
    await write_task
