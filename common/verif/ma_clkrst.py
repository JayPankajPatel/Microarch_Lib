"""Shared cocotb clock and reset helpers for Microarch_Lib testbenches.

All blocks in this repo use a free-running clock and an active-low,
asynchronously-asserted reset (`` `MA_ASSERT_INIT ``-checked modules driven
by `posedge clk or negedge rst_n`), so a single pair of helpers here avoids
every testbench re-deriving the same clock/reset boilerplate.
"""

from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


def start_clock(signal, period_ns=10):
    """Start and return a free-running Clock driving `signal`."""
    clock = Clock(signal, period_ns, unit="ns")
    clock.start()
    return clock


async def reset_dut(rst_n, clk, cycles=5):
    """Assert active-low `rst_n` for `cycles` rising edges of `clk`, then release it."""
    rst_n.value = 0
    for _ in range(cycles):
        await RisingEdge(clk)
    rst_n.value = 1
    await RisingEdge(clk)
