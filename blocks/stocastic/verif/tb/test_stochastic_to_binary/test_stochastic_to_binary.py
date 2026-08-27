import random

import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock

# module port definition
# module stochastic_to_binary #(
#     parameter int WIDTH = 4
# ) (
#     input logic clk,
#     input logic rst_n,
#     input logic stochastic_in,
#     input logic valid_stochastic_in,
#     input logic ready_binary_out,
#     output logic ready_stochastic_in,
#     output logic valid_binary_out,
#     output logic [WIDTH-1:0] binary_out
# );


async def wait_for_valid_binary_out(dut, max_edges=5):
    """Poll for valid_binary_out instead of assuming a fixed settling-edge
    count. How many edges a write needs to become visible to the DUT's
    combinational logic under cocotb+Verilator turned out to be
    context-sensitive (confirmed empirically: identical-looking code
    structured slightly differently needed 1 edge in one arrangement, 2 in
    another) rather than a fixed property of "first write" vs "later
    write" as originally assumed -- see the back_to_back_windows debugging
    in conversation history. Polling sidesteps needing to predict it.
    """
    for _ in range(max_edges):
        await RisingEdge(dut.clk)
        if dut.valid_binary_out.value == 1:
            return
    raise AssertionError(f"valid_binary_out did not assert within {max_edges} edges")


async def wait_for_ready_stochastic_in(dut, max_edges=5):
    """Poll for ready_stochastic_in -- i.e. the module has actually finished
    reopening for a new window, not just that valid_binary_out has appeared.
    These are two separate registered transitions (latch-and-show, then
    reset-and-clear one cycle later, guaranteed by their mutual exclusion in
    the RTL's always_comb), so waiting only for valid_binary_out is one
    cycle too early to safely start driving the next window's samples.
    """
    for _ in range(max_edges):
        await RisingEdge(dut.clk)
        if dut.ready_stochastic_in.value == 1:
            return
    raise AssertionError(f"ready_stochastic_in did not reassert within {max_edges} edges")


def golden_model(bits):
    """Independently predict binary_out for one accumulation window:
    binary_out is just the popcount of the `MAX_CYCLES` stochastic bits
    accepted during the window -- no LFSR, no protocol state, just count
    the 1s. `bits` is the list of stochastic_in values fed in, in order.
    """
    return sum(bits)


@cocotb.test()
async def smoke_test(dut):
    """This test is simply testing if the accumlation logic is correct
    and does not account for handshaking sematics and backpressure.
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    dut.valid_stochastic_in.value = 0
    dut.stochastic_in.value = 0
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in.value = 1
    dut.ready_binary_out.value = 1
    sto_buffer = []
    for _ in range(max_cycles):
        dut_in = random.randint(0, 1)
        sto_buffer.append(dut_in)
        dut.stochastic_in.value = dut_in
        await RisingEdge(dut.clk)

    # Two settling edges. Confirmed via direct VCD inspection (dump.vcd,
    # t=50000-60000): rin reacts combinationally in the same instant inputs
    # change (correct), but the write of valid_stochastic_in/ready_binary_out
    # right after reset_dut() isn't sampled by the always_ff until the clock
    # edge *after* the next one -- a real cocotb+Verilator write-visibility
    # characteristic (same one binary_stochastic_converter's testbench
    # documents independently for ready_stochastic_out), not an RTL bug or a
    # simple edge-boundary race (confirmed: inserting a FallingEdge before
    # the first write doesn't remove the delay). NOTE: this two-edge count
    # is NOT a universal "every write needs a settling edge" rule -- later
    # debugging (back_to_back_windows) found the exact count is
    # context-sensitive, and settled on polling (wait_for_valid_binary_out)
    # instead of a fixed count for that test. Two edges specifically here
    # matches what's actually observed for this write-right-after-reset_dut()
    # pattern.
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    expected = golden_model(sto_buffer)
    assert dut.valid_binary_out.value == 1, "valid_binary_out should assert once the window completes"
    assert int(dut.binary_out.value) == expected, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected}"
    )


@cocotb.test()
async def mid_accumulation_stall_ignores_ready_binary_out(dut):
    """ready_binary_out dropping mid-window must not affect accumulation --
    cycle_count/ones_count only depend on valid_stochastic_in, never on the
    output-side ready (see stochastic_binary_converter.json's E<->F edge:
    ready_binary_out low during accumulation, sample still accepted).
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    dut.valid_stochastic_in.value = 0
    dut.stochastic_in.value = 0
    dut.ready_binary_out.value = 0
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in.value = 1
    sto_buffer = []
    for i in range(max_cycles):
        dut_in = random.randint(0, 1)
        sto_buffer.append(dut_in)
        dut.stochastic_in.value = dut_in
        if i == max_cycles - 3:
            # raise ready_binary_out with a few cycles of margin before the
            # completion boundary, so the write has settled well before
            # r.cycle_count actually reaches MAX_CYCLES
            dut.ready_binary_out.value = 1
        await RisingEdge(dut.clk)
        assert dut.ready_stochastic_in.value == 1, (
            f"sample {i}: ready_stochastic_in dropped mid-accumulation even "
            "though the window isn't done -- accumulation must not depend "
            "on ready_binary_out"
        )

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    expected = golden_model(sto_buffer)
    assert dut.valid_binary_out.value == 1
    assert int(dut.binary_out.value) == expected, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected}"
    )


@cocotb.test()
async def valid_binary_out_should_hold_through_post_completion_stall(dut):
    """KNOWN FAILING TEST -- pins down an open bug, does not pass yet.

    stochastic_binary_converter.json's B<->C edge specifies the intended
    behavior: once a window completes, valid_binary_out should assert
    independent of ready_binary_out and hold there (binary_out stable)
    until the consumer actually asserts ready. The current RTL's
    completion branch instead requires ready_binary_out to already be high
    before it will ever assert valid_binary_out --
    `if (r.cycle_count == MAX_CYCLES && ready_binary_out)` -- so if the
    consumer isn't ready right when the window finishes, valid_binary_out
    never appears until ready_binary_out does, instead of appearing first
    and being held. This test encodes the *intended* (diagram) behavior
    and is expected to fail until that decoupling is fixed -- see the
    skid-buffer/valid-ready decoupling discussion this test was written
    from.
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    dut.valid_stochastic_in.value = 0
    dut.stochastic_in.value = 0
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in.value = 1
    dut.ready_binary_out.value = 0  # consumer not ready when the window completes
    sto_buffer = []
    for _ in range(max_cycles):
        dut_in = random.randint(0, 1)
        sto_buffer.append(dut_in)
        dut.stochastic_in.value = dut_in
        await RisingEdge(dut.clk)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    expected = golden_model(sto_buffer)
    assert dut.valid_binary_out.value == 1, (
        "valid_binary_out should assert as soon as the window is done, "
        "independent of ready_binary_out -- currently fails because the "
        "completion branch requires ready_binary_out already high"
    )
    assert int(dut.binary_out.value) == expected

    for _ in range(3):
        await RisingEdge(dut.clk)
        assert dut.valid_binary_out.value == 1, "valid_binary_out must stay asserted through the stall"
        assert int(dut.binary_out.value) == expected, "binary_out must stay stable while stalled"

    dut.ready_binary_out.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.valid_binary_out.value == 0, "valid_binary_out should drop once the handshake completes"


@cocotb.test()
async def back_to_back_windows(dut):
    """After one window completes, the next window's samples --
    ready_binary_out held high throughout -- must accumulate independently
    and not be corrupted by the previous window's leftover state. Uses a
    brief valid_stochastic_in drop at the window boundary (see comment
    below) rather than a fully gapless stream.
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    dut.valid_stochastic_in.value = 0
    dut.stochastic_in.value = 0
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in.value = 1
    dut.ready_binary_out.value = 1

    window_1 = []
    window_2 = []
    for _ in range(max_cycles):
        dut_in = random.randint(0, 1)
        window_1.append(dut_in)
        dut.stochastic_in.value = dut_in
        await RisingEdge(dut.clk)

    # Drop valid_stochastic_in before polling for completion -- the RTL's
    # completion sequence is two separate registered transitions (latch and
    # show valid, then reset and clear one cycle later, guaranteed by their
    # mutual exclusion in always_comb), so there are a couple of cycles here
    # where an accumulation branch firing on stale stochastic_in would be a
    # phantom sample. The completion branches don't read
    # valid_stochastic_in, so dropping it here doesn't interfere with
    # observing window 1's own completion.
    dut.valid_stochastic_in.value = 0
    await wait_for_valid_binary_out(dut)

    expected_1 = golden_model(window_1)
    assert int(dut.binary_out.value) == expected_1, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected_1} "
        f"for window 1 ({window_1})"
    )

    # valid_binary_out appearing is not the same cycle as the module
    # actually reopening -- wait for ready_stochastic_in too before driving
    # window 2's samples, or the first one or two risk landing during the
    # still-in-flight reset.
    await wait_for_ready_stochastic_in(dut)

    dut.valid_stochastic_in.value = 1
    for _ in range(max_cycles):
        dut_in = random.randint(0, 1)
        window_2.append(dut_in)
        dut.stochastic_in.value = dut_in
        await RisingEdge(dut.clk)

    await wait_for_valid_binary_out(dut)

    expected_2 = golden_model(window_2)
    assert int(dut.binary_out.value) == expected_2, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected_2} "
        f"for window 2 (window_1={window_1}, window_2={window_2}) -- second window's "
        "result must not be corrupted by the first window"
    )
