import random

import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock

# Integration test: two binary_stochastic_converter encoders -> a shared
# stochastic_multiplier -> stochastic_to_binary. Exercises the full chain
# end to end, not just a single module or a pairwise loopback.
#
# module top #(
#     parameter int WIDTH = 4,
#     parameter bit [WIDTH-1:0] INIT_SEED_A = WIDTH'(1),
#     parameter bit [WIDTH-1:0] INIT_SEED_B = WIDTH'(2)
# ) (
#     input  logic             clk,
#     input  logic             rst_n,
#     input  logic [WIDTH-1:0] binary_in_a,
#     input  logic             valid_binary_in_a,
#     input  logic [WIDTH-1:0] binary_in_b,
#     input  logic             valid_binary_in_b,
#     input  logic             ready_binary_out,
#     output logic             ready_binary_in_a,
#     output logic             ready_binary_in_b,
#     output logic             valid_binary_out,
#     output logic [WIDTH-1:0] binary_out
# );
#
# Two structural findings this composition surfaced (see docs/adr/0016,
# 0017), both directly exercised below:
# 1. binary_stochastic_converter's accept can no longer depend on
#    ready_stochastic_out (a mutual-startup deadlock otherwise: each
#    encoder's own "downstream ready" is gated on the OTHER encoder
#    already being valid, per stochastic_multiplier's join equations, so
#    with both starting idle neither could ever begin).
# 2. stochastic_to_binary now closes its window on an explicit boundary_in
#    pulse from the producer (here, either encoder's last_cycle -- the
#    multiplier's join forces them to be simultaneous, checked below)
#    rather than matching a locally-counted length against the encoder's,
#    since that only stays aligned by coincidence, not by construction.


@cocotb.test()
async def smoke_test_no_deadlock(dut):
    """The most basic possible check: two encoders driven from a cold reset
    must actually produce a result, not deadlock. This is exactly the
    scenario that hung forever before the accept-gate fix (docs/adr/0016)
    -- both encoders waiting on each other's valid via the multiplier's
    join equations.
    """
    period_ns = 10
    width = len(dut.binary_in_a)
    max_value = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.binary_in_a.value = random.randint(0, max_value)
    dut.binary_in_b.value = random.randint(0, max_value)
    dut.valid_binary_in_a.value = 1
    dut.valid_binary_in_b.value = 1
    dut.ready_binary_out.value = 1

    for _ in range(200):
        await RisingEdge(dut.clk)
        if dut.valid_binary_out.value == 1:
            break
    else:
        raise AssertionError(
            "chain never produced a binary_out result -- likely the "
            "mutual-startup deadlock from docs/adr/0016 has regressed"
        )


@cocotb.test()
async def product_matches_golden_model_over_multiple_windows(dut):
    """Drive several (a, b) pairs and confirm binary_out tracks the actual
    number of 1-bits the multiplier produced during each window -- not a
    closed-form a*b prediction (this module's own statistical accuracy is
    a property of the stochastic representation, not something a handful
    of windows can validate; that's a separate characterization exercise).
    This test's job is structural: does the chain produce a result every
    window, and is binary_out an honest count of what the multiplier
    actually output between two boundary_in pulses.
    """
    period_ns = 10
    width = len(dut.binary_in_a)
    max_value = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    values_a = [random.randint(1, max_value) for _ in range(3)]
    values_b = [random.randint(1, max_value) for _ in range(3)]

    dut.ready_binary_out.value = 1
    dut.valid_binary_in_a.value = 1
    dut.valid_binary_in_b.value = 1
    dut.binary_in_a.value = values_a[0]
    dut.binary_in_b.value = values_b[0]

    idx_a, idx_b = 1, 1
    windows_seen = 0
    ones_in_window = 0
    max_cycles = 3000
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)

        assert int(dut.last_cycle_a.value) == int(dut.last_cycle_b.value)

        if dut.ready_binary_in_a.value == 1 and idx_a < len(values_a):
            dut.binary_in_a.value = values_a[idx_a]
            idx_a += 1
        if dut.ready_binary_in_b.value == 1 and idx_b < len(values_b):
            dut.binary_in_b.value = values_b[idx_b]
            idx_b += 1

        # Check completion *before* recording this cycle's transfer: by the
        # cycle valid_binary_out first reads 1, the decoder's fast-path
        # reopen may have already landed in the same register update, so a
        # transfer observed at this same snapshot could belong to the
        # *next* window, not the one that just closed (same ordering bug
        # class found and fixed in test_loopback_stochastic).
        #
        # These must be two independent `if`s, not `if`/`elif`: the decoder
        # can complete a window AND accept a new sample for the next window
        # on the very same edge (ADR 0021's decoder slot-race fix made this
        # legal-and-correct). Resetting ones_in_window happens in the first
        # block (window closing), so a same-cycle transfer added in the
        # second block correctly lands in the fresh next-window accumulator
        # -- an `elif` would silently drop that sample from every window's
        # count instead (independent-audit finding).
        if dut.valid_binary_out.value == 1:
            windows_seen += 1
            assert int(dut.binary_out.value) == ones_in_window, (
                f"window {windows_seen}: binary_out={int(dut.binary_out.value)} != "
                f"actual product-stream popcount {ones_in_window} observed since the "
                "previous window closed"
            )
            ones_in_window = 0
            if windows_seen >= 3:
                break
        if int(dut.u_multiplier.valid_stochastic_out.value) == 1 and int(
            dut.u_multiplier.ready_stochastic_out.value
        ) == 1:
            ones_in_window += int(dut.u_multiplier.stochastic_out.value)
    else:
        raise AssertionError(f"only observed {windows_seen} windows in {max_cycles} cycles")
