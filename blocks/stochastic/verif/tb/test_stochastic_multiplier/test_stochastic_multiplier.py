import random

import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock

# module port definition
# module stochastic_multiplier (
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


def golden_model(bit_a, bit_b):
    """Stochastic multiplication is just AND of the two bits that actually
    fire together on a given cycle.
    """
    return bit_a & bit_b


async def drive_idle(dut):
    dut.stochastic_in_a.value = 0
    dut.valid_stochastic_in_a.value = 0
    dut.stochastic_in_b.value = 0
    dut.valid_stochastic_in_b.value = 0
    dut.ready_stochastic_out.value = 0


@cocotb.test()
async def basic_both_ready_every_cycle(dut):
    """Both operands present valid data and the consumer is always ready --
    every cycle should fire, and stochastic_out should be the AND of
    whatever bits A and B drove that cycle.
    """
    period_ns = 10
    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in_a.value = 1
    dut.valid_stochastic_in_b.value = 1
    dut.ready_stochastic_out.value = 1

    for _ in range(50):
        bit_a = random.randint(0, 1)
        bit_b = random.randint(0, 1)
        dut.stochastic_in_a.value = bit_a
        dut.stochastic_in_b.value = bit_b
        await RisingEdge(dut.clk)

        assert dut.ready_stochastic_in_a.value == 1, "A should be ready -- B and downstream are both ready"
        assert dut.ready_stochastic_in_b.value == 1, "B should be ready -- A and downstream are both ready"
        assert dut.valid_stochastic_out.value == 1, "output should be valid every cycle when both inputs are"
        assert int(dut.stochastic_out.value) == golden_model(bit_a, bit_b), (
            f"stochastic_out={int(dut.stochastic_out.value)} != golden model expected "
            f"{golden_model(bit_a, bit_b)} for a={bit_a}, b={bit_b}"
        )


@cocotb.test()
async def one_operand_stall_holds_no_fire(dut):
    """B drops valid while A stays valid and downstream stays ready. No
    output should fire, and A must not be told ready either -- consuming a
    bit from A while B has nothing to offer would silently desynchronize
    the two bitstreams (a bit dropped from A's stream with no matching
    consumption from B).
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

    for _ in range(10):
        await RisingEdge(dut.clk)
        # ready_stochastic_in_a is gated on valid_stochastic_in_b (not on
        # B's own readiness) -- with B not offering a bit, A must not be
        # told ready, or a bit would be silently consumed from A with
        # nothing consumed from B, desyncing the two streams.
        assert dut.ready_stochastic_in_a.value == 0, (
            "A must not be told ready while B has no valid bit -- consuming from A alone would desync the streams"
        )
        # valid_stochastic_out = valid_a && valid_b regardless of readiness
        # on either side (AMBA-style: VALID must not wait for READY) -- with
        # B not valid, no output fires, independent of what ready_b reads.
        assert dut.valid_stochastic_out.value == 0, "no output should fire while B is stalled"

    # release B -- now both fire
    dut.valid_stochastic_in_b.value = 1
    dut.stochastic_in_b.value = 1
    await RisingEdge(dut.clk)
    assert dut.ready_stochastic_in_a.value == 1
    assert dut.ready_stochastic_in_b.value == 1
    assert dut.valid_stochastic_out.value == 1
    assert int(dut.stochastic_out.value) == golden_model(1, 1)


@cocotb.test()
async def downstream_stall_holds_backpressure_on_both_operands(dut):
    """Both operands have valid data every cycle but the consumer
    (ready_stochastic_out) is not ready -- backpressure must propagate to
    both ready_stochastic_in_a and ready_stochastic_in_b, so neither
    operand ever has a bit consumed out from under it. valid_stochastic_out
    itself is expected to stay high through the stall: per AMBA-style
    valid/ready rules VALID must not be made to wait for READY, so this
    module correctly presents valid_a && valid_b as valid_stochastic_out
    regardless of downstream readiness -- a transfer is only considered to
    have happened where valid AND ready are both true, which is exactly
    what ready_stochastic_in_a/b (gated on ready_stochastic_out) encode.
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

    for _ in range(10):
        await RisingEdge(dut.clk)
        assert dut.ready_stochastic_in_a.value == 0, "downstream not ready -- A must not be told ready"
        assert dut.ready_stochastic_in_b.value == 0, "downstream not ready -- B must not be told ready"
        assert dut.valid_stochastic_out.value == 1, (
            "valid_stochastic_out should still reflect valid_a && valid_b -- VALID must not wait for READY"
        )

    # release downstream -- now both fire
    dut.ready_stochastic_out.value = 1
    await RisingEdge(dut.clk)
    assert dut.ready_stochastic_in_a.value == 1
    assert dut.ready_stochastic_in_b.value == 1
    assert dut.valid_stochastic_out.value == 1
    assert int(dut.stochastic_out.value) == golden_model(1, 1)


@cocotb.test()
async def back_to_back_streaming_random_join(dut):
    """Long random run with all three of A's valid, B's valid, and the
    downstream's ready independently randomized each cycle. Confirms that
    over many cycles, a transfer happens exactly when both operands are
    valid and downstream is ready, and stochastic_out is the bitwise AND
    of whatever A and B actually presented on each such cycle -- the
    sample-for-sample streaming-join property, not just a single-shot
    check.
    """
    period_ns = 10
    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    # Independently accumulate each stream as actually *consumed* -- i.e.
    # valid && ready on that side, not just valid -- rather than trusting
    # the per-cycle formula checks below (which restate the RTL's own
    # equations and would pass for any implementation matching them, even a
    # desynced one). This is the sample-for-sample stream property the task
    # and the stochastic_to_binary bug history actually care about: A and B
    # must be consumed in lockstep, one bit per real transfer, with the
    # output stream equal to their bitwise AND pair-for-pair.
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

        assert dut.valid_stochastic_out.value == expected_valid_out, (
            f"valid_stochastic_out={int(dut.valid_stochastic_out.value)} != expected "
            f"{int(expected_valid_out)} for valid_a={valid_a}, valid_b={valid_b}"
        )
        assert dut.ready_stochastic_in_a.value == expected_ready_a, (
            f"ready_stochastic_in_a={int(dut.ready_stochastic_in_a.value)} != expected "
            f"{int(expected_ready_a)} for ready_out={ready_out}, valid_b={valid_b}"
        )
        assert dut.ready_stochastic_in_b.value == expected_ready_b, (
            f"ready_stochastic_in_b={int(dut.ready_stochastic_in_b.value)} != expected "
            f"{int(expected_ready_b)} for ready_out={ready_out}, valid_a={valid_a}"
        )

        if valid_a and dut.ready_stochastic_in_a.value == 1:
            consumed_a.append(bit_a)
        if valid_b and dut.ready_stochastic_in_b.value == 1:
            consumed_b.append(bit_b)
        if dut.valid_stochastic_out.value == 1 and ready_out:
            out_stream.append(int(dut.stochastic_out.value))

    assert len(consumed_a) > 0, "randomized run produced zero transfers -- test is not exercising the join"
    assert len(consumed_a) == len(consumed_b) == len(out_stream), (
        f"streams desynced: {len(consumed_a)} bits consumed from A, {len(consumed_b)} from B, "
        f"{len(out_stream)} produced on output -- these must all advance together, one per real transfer"
    )
    assert out_stream == [a & b for a, b in zip(consumed_a, consumed_b)], (
        "output stream is not the sample-for-sample bitwise AND of what A and B actually presented "
        "on the cycles they were each actually consumed"
    )
