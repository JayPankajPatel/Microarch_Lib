"""AXI-Stream Cocotb testbench support built on ``BaseTB``."""

from __future__ import annotations

from typing import Any

from cocotbext.axi import (
    AxiStreamBus,
    AxiStreamMonitor,
    AxiStreamSink,
    AxiStreamSource,
)

from base_tb import BaseTB


class AxisTB(BaseTB):
    """Provide AXI-Stream source, sink, and optional monitor VIP.

    ``source`` acts as the upstream master connected to the DUT's input
    stream. ``sink`` acts as the downstream slave connected to the DUT's
    output stream. Signal names are discovered from conventional prefixes,
    such as ``s_axis_tdata`` and ``m_axis_tready``.
    """

    def __init__(
        self,
        dut: Any,
        *,
        s_axis_prefix: str = "s_axis",
        m_axis_prefix: str = "m_axis",
        monitor_prefix: str | None = None,
        clock_name: str = "clk",
        reset_name: str = "rst_n",
        reset_active_level: bool = False,
        clock_period_ns: int = 10,
    ) -> None:
        self.s_axis_prefix = s_axis_prefix
        self.m_axis_prefix = m_axis_prefix
        self.monitor_prefix = monitor_prefix
        super().__init__(
            dut,
            clock_name=clock_name,
            reset_name=reset_name,
            reset_active_level=reset_active_level,
            clock_period_ns=clock_period_ns,
        )
        self.build_interfaces()

    def _build_interfaces(self) -> None:
        """Create protocol VIP using the configured DUT signal prefixes."""
        self.source = AxiStreamSource(
            AxiStreamBus.from_prefix(self.dut, self.s_axis_prefix),
            self.clk,
            self.reset_signal,
            reset_active_level=self.reset_active_level,
        )
        self.sink = AxiStreamSink(
            AxiStreamBus.from_prefix(self.dut, self.m_axis_prefix),
            self.clk,
            self.reset_signal,
            reset_active_level=self.reset_active_level,
        )

        if self.monitor_prefix is None:
            self.monitor = None
            return

        self.monitor = AxiStreamMonitor(
            AxiStreamBus.from_prefix(self.dut, self.monitor_prefix),
            self.clk,
            self.reset_signal,
            reset_active_level=self.reset_active_level,
        )
