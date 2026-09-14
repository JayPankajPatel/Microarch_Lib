"""Protocol-agnostic Cocotb testbench lifecycle support.

Protocol-specific testbenches should inherit from :class:`BaseTB` and add
their own VIP, drivers, monitors, and scoreboards. This class intentionally
knows only how to find a DUT clock/reset and manage their common lifecycle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


class BaseTB(ABC):
    """Abstract base for a protocol-specific Cocotb testbench.

    Args:
        dut: Top-level design-under-test handle supplied by Cocotb.
        clock_name: Name of the DUT clock signal.
        reset_name: Name of the DUT reset signal.
        reset_active_level: Logic level that asserts reset. Use ``False``
            for an active-low ``rst_n`` and ``True`` for an active-high
            ``rst``.
        clock_period_ns: Free-running clock period in nanoseconds.

    Subclasses must implement :meth:`_build_interfaces` to construct their
    drivers, monitors, or verification IP after the common DUT handles have
    been resolved. ``BaseTB`` supplies the clock and reset lifecycle; it does
    not prescribe protocol-specific transactions or scoreboards.
    """

    def __init__(
        self,
        dut: Any,
        *,
        clock_name: str = "clk",
        reset_name: str = "rst_n",
        reset_active_level: bool = False,
        clock_period_ns: int = 10,
    ) -> None:
        if clock_period_ns <= 0:
            raise ValueError("clock_period_ns must be positive")

        self.dut = dut
        self.clk = getattr(dut, clock_name)
        self.reset_signal = getattr(dut, reset_name)
        self.reset_active_level = reset_active_level
        self.clock_period_ns = clock_period_ns
        self._clock_started = False
        self._interfaces_built = False

    def build_interfaces(self) -> None:
        """Construct protocol-specific drivers, monitors, and VIP once.

        This template method deliberately runs after subclass construction,
        avoiding a call to an overridden method from ``BaseTB.__init__``.
        """
        if self._interfaces_built:
            return

        self._build_interfaces()
        self._interfaces_built = True

    @abstractmethod
    def _build_interfaces(self) -> None:
        """Construct protocol-specific drivers, monitors, and VIP.

        ``self.dut``, ``self.clk``, and ``self.reset_signal`` are available
        before this hook is called. Start the simulation clock explicitly
        with :meth:`start_clock` when the test is ready to run.
        """

    def start_clock(self) -> None:
        """Start the DUT clock once for this testbench instance."""
        if self._clock_started:
            return

        clock = Clock(self.clk, self.clock_period_ns, unit="ns")
        cocotb.start_soon(clock.start())
        self._clock_started = True

    async def reset(self, cycles: int = 2) -> None:
        """Assert reset for ``cycles`` rising edges, then release it."""
        if cycles < 1:
            raise ValueError("cycles must be at least one")

        self.reset_signal.value = self.reset_active_level
        for _ in range(cycles):
            await RisingEdge(self.clk)

        self.reset_signal.value = not self.reset_active_level
        await RisingEdge(self.clk)
