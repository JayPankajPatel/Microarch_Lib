"""Shared cocotb clock and reset helpers for Microarch_Lib testbenches.

All blocks in this repo use a free-running clock and an active-low,
asynchronously-asserted reset (`` `MA_ASSERT_INIT ``-checked modules driven
by `posedge clk or negedge rst_n`), so a single pair of helpers here avoids
every testbench re-deriving the same clock/reset boilerplate.

`drive`/`sample_pre_edge`/`clock_step` below are the phase-safe edge-timing
discipline originally developed independently in
test_stochastic_decorrelator.py and test_stochastic_to_binary.py, promoted
here so every testbench in this repo shares one implementation instead of
each re-deriving (or not deriving at all) the same fix. Writing a `.value =`
right before or after a bare `await RisingEdge` and reading it back
immediately is not reliably safe under cocotb+Verilator: combinational
signals that depend on a freshly-written input can read as unsettled right
at that edge even though a read moments later shows the settled value, and
purely-combinational (non-registered) signals read immediately after an
edge reflect the register's state AFTER that edge's update -- i.e. what
will determine the NEXT edge, not what determined the one that just
happened. Both were root-caused (not worked around with extra `await
RisingEdge`s or guessed settling-edge counts) via direct hierarchical
signal tracing during this repo's encoder/decoder/decorrelator fixes -- see
docs/adr/0021.
"""

from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge


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


async def drive(dut, **values):
    """Set input values on a FallingEdge -- a writable phase, mid-cycle,
    giving combinational logic a full half-period to settle before the next
    RisingEdge evaluates it. Driving right before/after a RisingEdge (no
    FallingEdge in between) is not reliably safe (see this module's
    docstring).

    INVARIANT: drive() and clock_step() must strictly alternate -- every
    drive() call must be followed by exactly one clock_step() before the
    next drive(). Calling drive() twice in a row (directly, or because a
    helper's own trailing drive() is followed by a caller/loop that starts
    with its own drive()) does not error -- it just awaits the *next*
    FallingEdge, a full period later, silently skipping the RisingEdge in
    between. Symptoms look like an RTL bug (bits desync from a golden
    model, valid drops mid-burst) but are actually the testbench losing a
    cycle. If a value needs changing without "spending" a standalone
    drive()/clock_step() pair, fold it into the kwargs of whichever drive()
    call already comes next, rather than adding a new one."""
    await FallingEdge(dut.clk)
    for name, val in values.items():
        getattr(dut, name).value = val


async def sample_pre_edge(dut):
    """Enter the read-only phase mid-cycle (after `drive()`, before the next
    RisingEdge) to safely sample PURE-COMBINATIONAL signals that depend on
    a register's CURRENT (not-yet-updated) state -- e.g. a ready output
    computed from `r.something && external_input`. These are NOT
    registered: reading them right AFTER a RisingEdge instead reflects the
    register's just-updated (post-edge) value combined with whatever
    inputs are still held from before the next drive() call -- i.e. what
    will determine the NEXT edge's transition, not the one that just
    happened. Registered outputs (anything that is, or is a direct
    continuous assign of, a flopped signal) are read correctly post-edge
    via clock_step() instead."""
    await ReadOnly()


async def clock_step(dut):
    """Advance to the next RisingEdge and enter the read-only phase before
    any signal is sampled, so that edge's always_ff update and all
    combinational settling are guaranteed complete. Use this to sample
    REGISTERED outputs -- for purely-combinational signals, use
    sample_pre_edge() instead, called before this. cocotb disallows writes
    during ReadOnly, so always pair this with a `drive()` call on the
    FOLLOWING FallingEdge; never write again until the next `drive()`."""
    await RisingEdge(dut.clk)
    await ReadOnly()
