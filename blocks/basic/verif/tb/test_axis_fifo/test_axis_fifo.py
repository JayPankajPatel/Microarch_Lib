"""Cocotb AXI-Stream tests for the one-entry elastic FIFO.

The AXI-Stream VIP supplies a source that obeys TVALID/TREADY and a sink
that can insert backpressure. Each byte is sent as an individual frame
because this introductory FIFO intentionally has no TLAST port yet.
"""

import itertools

import cocotb
from axis_tb import AxisTB
from cocotbext.axi import AxiStreamFrame


class TB(AxisTB):
    def __init__(self, dut):
        super().__init__(
            dut,
            reset_name="rst",
            reset_active_level=True,
        )

    async def reset(self):
        self.start_clock()
        await super().reset()

    async def send_bytes(self, values):
        for value in values:
            await self.source.send(AxiStreamFrame([value]))

    async def expect_bytes(self, expected):
        for index, value in enumerate(expected):
            frame = await self.sink.recv()
            actual = list(frame.tdata)
            assert actual == [value], (
                f"transfer {index}: received {actual}, expected [{value}]"
            )


@cocotb.test()
async def preserves_order_without_stalls(dut):
    """The FIFO must deliver every byte in FIFO order."""
    tb = TB(dut)
    await tb.reset()

    expected = list(range(16))
    await tb.send_bytes(expected)
    await tb.expect_bytes(expected)


@cocotb.test()
async def preserves_order_under_backpressure(dut):
    """A stalled output must neither lose nor reorder offered data."""
    tb = TB(dut)
    await tb.reset()

    # True pauses the sink, driving TREADY low for that cycle.
    pauses = itertools.cycle([False, False, True, False, True])
    tb.sink.set_pause_generator(pauses)

    expected = [(3 * index) & 0xFF for index in range(32)]
    await tb.send_bytes(expected)
    await tb.expect_bytes(expected)
