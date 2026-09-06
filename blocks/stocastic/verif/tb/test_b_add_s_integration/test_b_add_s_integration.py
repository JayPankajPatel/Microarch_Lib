import random

import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock

# Integration test: two binary_stochastic_converter encoders -> a shared
# stochastic_adder -> stochastic_to_binary. Mirrors
# test_b_mult_s_integration with the adder in place of the multiplier.
#
# module top #(
#     parameter int WIDTH = 4,
#     parameter bit [WIDTH-1:0] INIT_SEED_A = WIDTH'(1),
#     parameter bit [WIDTH-1:0] INIT_SEED_B = WIDTH'(2),
#     parameter int SELECT_LFSR_WIDTH = 5,
#     parameter bit [SELECT_LFSR_WIDTH-1:0] SELECT_INIT_SEED = SELECT_LFSR_WIDTH'(1)
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
# The adder's join has the exact same shape as stochastic_multiplier's
# (docs/adr/0012), so the same two structural findings apply here without
# needing to be rediscovered: the encoder accept-gate fix (docs/adr/0016)
# is already general (not multiplier-specific), and the decoder's
# boundary_in synchronization (docs/adr/0017) generalizes the same way,
# using either encoder's last_cycle (checked for simultaneity below).


@cocotb.test()
async def smoke_test_no_deadlock(dut):
    """Same defensive check as test_b_mult_s_integration's smoke test:
    confirm two encoders driven from cold reset actually produce a result
    through this different join-shaped consumer, rather than assuming the
    ADR 0016 fix generalizes without checking.
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
            "chain never produced a binary_out result -- check whether the "
            "docs/adr/0016 accept-gate fix still holds for this join shape"
        )


@cocotb.test()
async def sum_matches_golden_model_over_multiple_windows(dut):
    """Drive several (a, b) pairs and confirm binary_out tracks the actual
    number of 1-bits the adder produced during each window. Structural
    check only (does the chain produce an honest count of whatever the
    adder actually output between two boundary_in pulses) -- not a
    closed-form (a+b)/2 prediction, which is a statistical property needing
    far more samples than a handful of windows can validate (see
    docs/adr/0014's own scoping of stochastic_adder's statistical test).
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

        assert int(dut.last_cycle_a.value) == int(dut.last_cycle_b.value), (
            "last_cycle_a and last_cycle_b diverged -- the adder's join "
            "should keep both encoders' burst boundaries simultaneous when "
            "WIDTH matches on both sides"
        )

        if dut.ready_binary_in_a.value == 1 and idx_a < len(values_a):
            dut.binary_in_a.value = values_a[idx_a]
            idx_a += 1
        if dut.ready_binary_in_b.value == 1 and idx_b < len(values_b):
            dut.binary_in_b.value = values_b[idx_b]
            idx_b += 1

        # Check completion *before* recording this cycle's transfer -- see
        # test_b_mult_s_integration for why (a same-cycle next-window
        # sample can otherwise leak into the previous window's total).
        if dut.valid_binary_out.value == 1:
            windows_seen += 1
            assert int(dut.binary_out.value) == ones_in_window, (
                f"window {windows_seen}: binary_out={int(dut.binary_out.value)} != "
                f"actual sum-stream popcount {ones_in_window} observed since the "
                "previous window closed"
            )
            ones_in_window = 0
            if windows_seen >= 3:
                break
        elif int(dut.u_adder.valid_stochastic_out.value) == 1 and int(
            dut.u_adder.ready_stochastic_out.value
        ) == 1:
            ones_in_window += int(dut.u_adder.stochastic_out.value)
    else:
        raise AssertionError(f"only observed {windows_seen} windows in {max_cycles} cycles")
