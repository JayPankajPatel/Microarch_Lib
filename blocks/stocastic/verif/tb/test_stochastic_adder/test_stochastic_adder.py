import random

import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock
from pylfsr import LFSR

# module port definition
# module stochastic_adder #(
#     parameter int SELECT_LFSR_WIDTH = 4,
#     parameter bit [SELECT_LFSR_WIDTH-1:0] SELECT_INIT_SEED = SELECT_LFSR_WIDTH'(1)
# ) (
#     input  logic clk,
#     input  logic rst_n,
#     input  logic stochastic_in_a,
#     input  logic valid_stochastic_in_a,
#     output logic ready_stochastic_in_a,
#     input  logic stochastic_in_b,
#     input  logic valid_stochastic_in_b,
#     output logic ready_stochastic_in_b,
#     input  logic ready_stochastic_out,
#     output logic valid_stochastic_out,
#     output logic stochastic_out
# );
#
# Textbook stochastic addition: stochastic_out = MUX(select, A, B), an
# independent random select bit picking A or B each real-transfer cycle --
# this scales the true sum to (A+B)/2 (a stochastic bitstream can't
# represent p>1). select must be independent of A and B, so this module
# draws it from its own internal galois_lfsr (SELECT_RNG), advanced only on
# cycles a bit is actually produced (valid && ready).

# Mirrors galois_lfsr.sv's TAPS_LUT exactly -- keep in sync with the other
# tb dirs' copies (see test_binary_to_stochastic/test_binary_stochastic.py
# for why this is duplicated rather than imported).
TAPS_LUT = {
    0: 0x0, 1: 0x0, 2: 0x1, 3: 0x1, 4: 0x4, 5: 0x4, 6: 0x10, 7: 0x20,
    8: 0x38, 9: 0x10, 10: 0x40, 11: 0x100, 12: 0x29, 13: 0x241, 14: 0x409,
    15: 0x2000, 16: 0x406,
}


def fpoly_for(width):
    mask = TAPS_LUT[width]
    taps = [i + 1 for i in range(width) if (mask >> i) & 1]
    return sorted(set(taps + [width]), reverse=True)


def state_to_int(state, width):
    value = 0
    for j, bit in enumerate(state):
        value |= (int(bit) & 1) << (width - 1 - j)
    return value


def golden_select_bits(width, init_seed, count):
    """Predict `count` select bits (the LFSR's MSB, matching
    select_lfsr_out[SELECT_LFSR_WIDTH-1] in the RTL) starting from
    init_seed, advancing once per predicted bit -- same "compare against
    pre-advance state" convention test_binary_stochastic.py's golden_model
    uses for the encoder's own random_number.
    """
    fpoly = fpoly_for(width)
    initstate = [(init_seed >> (width - 1 - j)) & 1 for j in range(width)]
    ref = LFSR(fpoly=fpoly, initstate=initstate, conf="galois", verbose=False)
    state = state_to_int(initstate, width)
    bits = []
    for _ in range(count):
        bits.append((state >> (width - 1)) & 1)
        ref.next()
        state = state_to_int(ref.state, width)
    return bits


async def drive_idle(dut):
    dut.stochastic_in_a.value = 0
    dut.valid_stochastic_in_a.value = 0
    dut.stochastic_in_b.value = 0
    dut.valid_stochastic_in_b.value = 0
    dut.ready_stochastic_out.value = 0


@cocotb.test()
async def basic_both_ready_every_cycle(dut):
    """Both operands present valid data and the consumer is always ready --
    every cycle should fire, and stochastic_out should be A or B according
    to the independently-predicted select-LFSR sequence.
    """
    period_ns = 10
    select_width = len(dut.select_lfsr_out)
    init_seed = int(dut.SELECT_RNG.INIT_SEED.value)

    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in_a.value = 1
    dut.valid_stochastic_in_b.value = 1
    dut.ready_stochastic_out.value = 1

    n = 50
    select_bits = golden_select_bits(select_width, init_seed, n)
    for i in range(n):
        bit_a = random.randint(0, 1)
        bit_b = random.randint(0, 1)
        dut.stochastic_in_a.value = bit_a
        dut.stochastic_in_b.value = bit_b
        await RisingEdge(dut.clk)

        assert dut.ready_stochastic_in_a.value == 1
        assert dut.ready_stochastic_in_b.value == 1
        assert dut.valid_stochastic_out.value == 1
        expected = bit_b if select_bits[i] else bit_a
        assert int(dut.stochastic_out.value) == expected, (
            f"cycle {i}: stochastic_out={int(dut.stochastic_out.value)} != expected "
            f"{expected} (select={select_bits[i]}, a={bit_a}, b={bit_b})"
        )


@cocotb.test()
async def one_operand_stall_holds_no_fire(dut):
    """B drops valid while A stays valid and downstream stays ready. No
    output should fire, A must not be told ready, and the select LFSR must
    not advance (no bit produced, so no fresh select should be consumed).
    """
    period_ns = 10
    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in_a.value = 1
    dut.valid_stochastic_in_b.value = 0
    dut.ready_stochastic_out.value = 1
    dut.stochastic_in_a.value = 1
    dut.stochastic_in_b.value = 0

    select_state_before = int(dut.select_lfsr_out.value)
    for _ in range(10):
        await RisingEdge(dut.clk)
        assert dut.ready_stochastic_in_a.value == 0, (
            "A must not be told ready while B has no valid bit -- consuming from A alone would desync the streams"
        )
        assert dut.valid_stochastic_out.value == 0, "no output should fire while B is stalled"
        assert int(dut.select_lfsr_out.value) == select_state_before, (
            "select LFSR must not advance on a cycle no bit is actually produced"
        )

    dut.valid_stochastic_in_b.value = 1
    dut.stochastic_in_b.value = 1
    await RisingEdge(dut.clk)
    assert dut.ready_stochastic_in_a.value == 1
    assert dut.ready_stochastic_in_b.value == 1
    assert dut.valid_stochastic_out.value == 1


@cocotb.test()
async def downstream_stall_holds_backpressure_and_select_lfsr(dut):
    """Both operands valid every cycle but the consumer isn't ready --
    backpressure must propagate to both operand-side readys, and the select
    LFSR must not advance either (advancing it would burn a random draw on
    a bit nobody consumes, desyncing the golden model from the DUT for
    every bit after the stall).
    """
    period_ns = 10
    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in_a.value = 1
    dut.valid_stochastic_in_b.value = 1
    dut.stochastic_in_a.value = 1
    dut.stochastic_in_b.value = 1
    dut.ready_stochastic_out.value = 0

    select_state_before = int(dut.select_lfsr_out.value)
    for _ in range(10):
        await RisingEdge(dut.clk)
        assert dut.ready_stochastic_in_a.value == 0
        assert dut.ready_stochastic_in_b.value == 0
        assert dut.valid_stochastic_out.value == 1, (
            "valid_stochastic_out should still reflect valid_a && valid_b -- VALID must not wait for READY"
        )
        assert int(dut.select_lfsr_out.value) == select_state_before, (
            "select LFSR must not advance while downstream isn't ready to consume the bit"
        )

    dut.ready_stochastic_out.value = 1
    await RisingEdge(dut.clk)
    assert dut.ready_stochastic_in_a.value == 1
    assert dut.ready_stochastic_in_b.value == 1


@cocotb.test()
async def back_to_back_streaming_random_join(dut):
    """Long random run with A's valid, B's valid, and downstream's ready
    independently randomized each cycle. Confirms the join fires exactly
    when both operands are valid and downstream is ready, and that
    stochastic_out matches the independently-predicted select-LFSR
    sequence applied to whatever A and B actually presented on each cycle
    a transfer really happened.
    """
    period_ns = 10
    select_width = len(dut.select_lfsr_out)
    init_seed = int(dut.SELECT_RNG.INIT_SEED.value)

    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    # Generous upper bound: worst case every one of the 500 attempted cycles
    # is a real transfer.
    select_bits = golden_select_bits(select_width, init_seed, 500)
    select_idx = 0

    consumed_a = []
    consumed_b = []
    out_stream = []

    for _ in range(500):
        bit_a = random.randint(0, 1)
        bit_b = random.randint(0, 1)
        valid_a = random.randint(0, 1)
        valid_b = random.randint(0, 1)
        ready_out = random.randint(0, 1)

        dut.stochastic_in_a.value = bit_a
        dut.stochastic_in_b.value = bit_b
        dut.valid_stochastic_in_a.value = valid_a
        dut.valid_stochastic_in_b.value = valid_b
        dut.ready_stochastic_out.value = ready_out

        await RisingEdge(dut.clk)

        expected_valid_out = valid_a and valid_b
        expected_ready_a = ready_out and valid_b
        expected_ready_b = ready_out and valid_a

        assert dut.valid_stochastic_out.value == expected_valid_out
        assert dut.ready_stochastic_in_a.value == expected_ready_a
        assert dut.ready_stochastic_in_b.value == expected_ready_b

        real_transfer = expected_valid_out and ready_out
        if real_transfer:
            expected = bit_b if select_bits[select_idx] else bit_a
            assert int(dut.stochastic_out.value) == expected, (
                f"transfer {select_idx}: stochastic_out != expected {expected} "
                f"(select={select_bits[select_idx]}, a={bit_a}, b={bit_b})"
            )
            select_idx += 1
            consumed_a.append(bit_a)
            consumed_b.append(bit_b)
            out_stream.append(int(dut.stochastic_out.value))

    assert select_idx > 0, "randomized run produced zero real transfers -- test is not exercising the join"
    assert len(consumed_a) == len(consumed_b) == len(out_stream) == select_idx


@cocotb.test()
async def scaled_sum_statistical_property(dut):
    """The textbook property this module exists to demonstrate: with A held
    at a constant 1 and B held at a constant 0 (i.e. probabilities 1.0 and
    0.0), a MUX-based stochastic adder should output a bitstream whose
    observed 1-frequency is close to 0.5 -- (1.0 + 0.0) / 2 -- not an exact
    per-bit relationship (it's still A or B verbatim each cycle, chosen by
    an independent coin flip), but a statistical one over enough samples.
    This is what distinguishes "textbook scaled adder" from a broken MUX:
    a stuck-at-0 select or a select correlated with A/B would produce a
    frequency far from 0.5 while still passing every per-bit check above.
    """
    period_ns = 10
    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.stochastic_in_a.value = 1
    dut.stochastic_in_b.value = 0
    dut.valid_stochastic_in_a.value = 1
    dut.valid_stochastic_in_b.value = 1
    dut.ready_stochastic_out.value = 1

    n = 2000
    ones = 0
    for _ in range(n):
        await RisingEdge(dut.clk)
        assert dut.valid_stochastic_out.value == 1
        ones += int(dut.stochastic_out.value)

    frequency = ones / n
    # 0.05, not an arbitrary-looking number: select is only APPROXIMATELY
    # 50/50, never exactly (see stochastic_adder.sv's own comment) -- a
    # maximal-length LFSR's odd period makes an exact single-bit 50/50
    # split mathematically impossible. At the default SELECT_LFSR_WIDTH=5
    # that structural bias alone is ~0.016 (16/31 vs 1/2), so this
    # tolerance has to clear that PLUS real sampling noise at n=2000, not
    # just sampling noise alone -- independent-audit finding.
    assert abs(frequency - 0.5) < 0.05, (
        f"observed 1-frequency {frequency:.4f} over {n} samples is too far from the "
        f"expected (A+B)/2 = 0.5 -- select bit may be stuck, biased, or correlated with A/B"
    )
