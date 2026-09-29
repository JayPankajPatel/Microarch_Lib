import random

import cocotb
from ma_clkrst import clock_step, drive, reset_dut, start_clock

# module port definition
# module stochastic_to_binary #(
#     parameter int WIDTH = 4
# ) (
#     input logic clk,
#     input logic rst_n,
#     input logic stochastic_in,
#     input logic valid_stochastic_in,
#     input logic boundary_in,
#     input logic ready_binary_out,
#     output logic ready_stochastic_in,
#     output logic valid_binary_out,
#     output logic [WIDTH-1:0] binary_out
# );
#
# boundary_in is meaningful only on a cycle a sample is actually
# transferred (valid_stochastic_in && ready_stochastic_in both high) --
# asserting it there tells the decoder "this is the last sample of the
# current window," replacing the older design's reliance on a local
# cycle_count reaching a fixed target (see docs/adr/0017). These
# module-level tests drive it explicitly (high on the intended last sample
# of each window, low otherwise) rather than relying on any implicit
# per-module window length.
#
# All input changes go through drive() (FallingEdge-based) and all signal
# reads through clock_step() (RisingEdge+ReadOnly) -- see ma_clkrst.py's
# module docstring and docs/adr/0021. Both ready_stochastic_in and
# valid_binary_out here are pure functions of this module's OWN registered
# state (`r.last_sample_seen`/`r.valid_binary_out`), with no dependency on
# any freshly-driven external input in their own combinational expression,
# so a post-edge clock_step() read is correct for both -- no polling or
# guessed settling-edge count needed once writes are FallingEdge-driven,
# unlike the earlier version of this file.


def golden_model(bits):
    """Independently predict binary_out for one accumulation window:
    binary_out is just the popcount of the stochastic bits accepted during
    the window -- no LFSR, no protocol state, just count the 1s. `bits` is
    the list of stochastic_in values fed in, in order, for exactly one
    window (however many samples that window turns out to have, as marked
    by boundary_in -- these tests always use max_cycles-sample windows).
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
    await drive(dut, valid_stochastic_in=0, stochastic_in=0, boundary_in=0, ready_binary_out=0)
    await reset_dut(dut.rst_n, dut.clk, 5)

    sto_buffer = []
    for i in range(max_cycles):
        dut_in = random.randint(0, 1)
        sto_buffer.append(dut_in)
        await drive(
            dut,
            valid_stochastic_in=1,
            ready_binary_out=1,
            stochastic_in=dut_in,
            boundary_in=1 if i == max_cycles - 1 else 0,
        )
        await clock_step(dut)

    # The boundary sample was accepted on the last loop iteration's edge;
    # the completion latch fires on the NEXT accept-cycle's transition, so
    # one more clock_step (no new drive needed, nothing changes) makes
    # valid_binary_out visible. Deterministic with FallingEdge-based
    # driving -- no settling-edge guesswork.
    await clock_step(dut)

    expected = golden_model(sto_buffer)
    assert dut.valid_binary_out.value == 1, "valid_binary_out should assert once the window completes"
    assert int(dut.binary_out.value) == expected, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected}"
    )


@cocotb.test()
async def mid_accumulation_stall_ignores_ready_binary_out(dut):
    """ready_binary_out dropping mid-window must not affect accumulation --
    accumulation only depends on valid_stochastic_in/ready_stochastic_in
    (i.e. a real transfer happening), never on the output-side ready (see
    stochastic_binary_converter.json's E<->F edge: ready_binary_out low
    during accumulation, sample still accepted).
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    await drive(dut, valid_stochastic_in=0, stochastic_in=0, boundary_in=0, ready_binary_out=0)
    await reset_dut(dut.rst_n, dut.clk, 5)

    sto_buffer = []
    for i in range(max_cycles):
        dut_in = random.randint(0, 1)
        sto_buffer.append(dut_in)
        await drive(
            dut,
            valid_stochastic_in=1,
            stochastic_in=dut_in,
            boundary_in=1 if i == max_cycles - 1 else 0,
            # Raise ready_binary_out partway through -- accumulation must
            # not react to it either way.
            ready_binary_out=1 if i >= max_cycles - 3 else 0,
        )
        await clock_step(dut)
        if i < max_cycles - 1:
            # Excludes the boundary sample itself (i == max_cycles - 1):
            # accepting THAT sample correctly sets last_sample_seen, which
            # correctly drops ready_stochastic_in on this same edge -- the
            # window really is done at that point. This assertion is about
            # every sample BEFORE the window closes, not the closing one.
            assert dut.ready_stochastic_in.value == 1, (
                f"sample {i}: ready_stochastic_in dropped mid-accumulation even "
                "though the window isn't done -- accumulation must not depend "
                "on ready_binary_out"
            )

    await clock_step(dut)

    expected = golden_model(sto_buffer)
    assert dut.valid_binary_out.value == 1
    assert int(dut.binary_out.value) == expected, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected}"
    )


@cocotb.test()
async def valid_binary_out_should_hold_through_post_completion_stall(dut):
    """stochastic_binary_converter.json's B<->C edge specifies the intended
    behavior: once a window completes, valid_binary_out should assert
    independent of ready_binary_out and hold there (binary_out stable)
    until the consumer actually asserts ready.
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    await drive(dut, valid_stochastic_in=0, stochastic_in=0, boundary_in=0, ready_binary_out=0)
    await reset_dut(dut.rst_n, dut.clk, 5)

    sto_buffer = []
    for i in range(max_cycles):
        dut_in = random.randint(0, 1)
        sto_buffer.append(dut_in)
        await drive(
            dut,
            valid_stochastic_in=1,
            stochastic_in=dut_in,
            boundary_in=1 if i == max_cycles - 1 else 0,
        )
        await clock_step(dut)

    await clock_step(dut)

    expected = golden_model(sto_buffer)
    assert dut.valid_binary_out.value == 1, (
        "valid_binary_out should assert as soon as the window is done, "
        "independent of ready_binary_out"
    )
    assert int(dut.binary_out.value) == expected

    # Drop valid_stochastic_in/boundary_in NOW, before the stall loop below
    # -- not just before the final drain write. The window's completion
    # reopens the accumulator (last_sample_seen clears, ready_stochastic_in
    # goes high again) in this SAME transition, so leaving
    # valid_stochastic_in asserted with the stale boundary_in=1 left over
    # from the last accumulated sample would let the very next stall-loop
    # iteration silently accept one more sample and immediately complete a
    # bogus second "window" (confirmed by direct tracing: this caused the
    # eventual drain to need an extra cycle, consumed by re-latching that
    # bogus window before actually clearing valid).
    await drive(dut, valid_stochastic_in=0, boundary_in=0)

    for _ in range(3):
        await clock_step(dut)
        assert dut.valid_binary_out.value == 1, "valid_binary_out must stay asserted through the stall"
        assert int(dut.binary_out.value) == expected, "binary_out must stay stable while stalled"

    await drive(dut, ready_binary_out=1)
    await clock_step(dut)
    assert dut.valid_binary_out.value == 0, "valid_binary_out should drop once the handshake completes"


@cocotb.test()
async def transient_ready_before_valid_must_not_drop_result(dut):
    """The specific adversarial legal sequence an independent audit flagged:
    ready_binary_out flutters high then low WHILE the window is still
    accumulating (before valid_binary_out has ever become externally
    visible), rather than staying low throughout like
    valid_binary_out_should_hold_through_post_completion_stall tests. A
    prior version of this module decided whether to immediately reopen
    using whatever ready_binary_out happened to read on the cycle the
    window's LAST sample was accepted -- one cycle before valid became
    externally visible -- so a stale "ready was high a moment ago" reading
    could cause the result to be silently dropped without ready and valid
    ever actually having been true on the SAME cycle. The fix makes the
    slot-drain decision depend only on r.valid_binary_out (already
    externally visible) and ready_binary_out sampled the SAME cycle, which
    structurally cannot observe a not-yet-visible valid.
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    await drive(dut, valid_stochastic_in=0, stochastic_in=0, boundary_in=0, ready_binary_out=0)
    await reset_dut(dut.rst_n, dut.clk, 5)

    sto_buffer = []
    for i in range(max_cycles):
        dut_in = random.randint(0, 1)
        sto_buffer.append(dut_in)
        if i == max_cycles - 1:
            # Flutter ready high then immediately low again, on the very
            # cycle the window's last sample is accepted -- one cycle
            # before valid_binary_out can possibly become externally
            # visible. A consumer's ready is legally allowed to do this;
            # it must not be mistaken for a real handshake against THIS
            # result.
            await drive(dut, valid_stochastic_in=1, stochastic_in=dut_in, boundary_in=1, ready_binary_out=1)
            await clock_step(dut)
            await drive(dut, ready_binary_out=0)
            continue
        await drive(dut, valid_stochastic_in=1, stochastic_in=dut_in, boundary_in=0)
        await clock_step(dut)

    await drive(dut, valid_stochastic_in=0, boundary_in=0)
    await clock_step(dut)

    expected = golden_model(sto_buffer)
    assert dut.valid_binary_out.value == 1, "result was dropped without ready and valid ever having been true on the same cycle"
    assert int(dut.binary_out.value) == expected

    for _ in range(3):
        await drive(dut)
        await clock_step(dut)
        assert dut.valid_binary_out.value == 1, (
            "result was dropped without ready and valid ever having been true on the same cycle"
        )
        assert int(dut.binary_out.value) == expected, "binary_out must stay stable while the result is unconsumed"

    await drive(dut, ready_binary_out=1)
    await clock_step(dut)
    assert dut.valid_binary_out.value == 0


@cocotb.test()
async def simultaneous_output_drain_and_input_accept_must_not_drop_input(dut):
    """The other adversarial legal sequence an independent audit flagged,
    distinct from transient_ready_before_valid_must_not_drop_result above:
    a completed result sits unconsumed in the output slot while the NEXT
    window is already accumulating (last_sample_seen=0, so
    ready_stochastic_in is high and new samples are being accepted). On the
    cycle the consumer finally raises ready_binary_out to drain the old
    result, a new input sample is ALSO being accepted that same cycle --
    two operations touching disjoint state (valid_binary_out vs.
    ones_count/last_sample_seen) that a prior version's mutually-exclusive
    `else if` chain treated as an either-or, silently discarding whichever
    input sample coincided with a drain despite the module having already
    told the producer it accepted that sample (ready_stochastic_in was
    high). This directly checks that the concurrently-accepted sample is
    NOT lost: it must show up in the next window's final popcount.
    """
    period_ns = 10
    width = len(dut.binary_out)
    max_cycles = (1 << width) - 1
    start_clock(dut.clk, period_ns)
    await drive(dut, valid_stochastic_in=0, stochastic_in=0, boundary_in=0, ready_binary_out=0)
    await reset_dut(dut.rst_n, dut.clk, 5)

    # Window 1: complete it with ready_binary_out held low, so its result
    # sits unconsumed in the slot once done.
    for i in range(max_cycles):
        await drive(
            dut,
            valid_stochastic_in=1,
            stochastic_in=random.randint(0, 1),
            boundary_in=1 if i == max_cycles - 1 else 0,
        )
        await clock_step(dut)

    # Drop valid_stochastic_in (and the stale boundary_in=1 left over from
    # window 1's last sample) before the completion edge: with
    # last_sample_seen about to clear, ready_stochastic_in goes high again
    # immediately, and leaving valid_stochastic_in asserted with a stale
    # boundary_in would let a spurious extra accept complete a bogus
    # 1-sample "window" right away, corrupting the precondition this test
    # relies on.
    await drive(dut, valid_stochastic_in=0, boundary_in=0)
    await clock_step(dut)
    assert dut.valid_binary_out.value == 1, "window 1 should have completed"

    # Window 2's samples, tracked independently of the DUT.
    window_2_bits = [random.randint(0, 1) for _ in range(max_cycles)]

    # The adversarial cycle: drive window 2's FIRST sample while
    # simultaneously raising ready_binary_out to drain window 1's result.
    # ready_stochastic_in must already be high here (last_sample_seen was
    # cleared when window 1's result was latched), so this sample IS
    # accepted on this exact edge per the handshake contract.
    assert dut.ready_stochastic_in.value == 1, "decoder should already be accepting window 2's samples"
    await drive(
        dut,
        valid_stochastic_in=1,
        stochastic_in=window_2_bits[0],
        boundary_in=0,
        ready_binary_out=1,
    )
    await clock_step(dut)

    # Remaining samples of window 2, streamed normally.
    for i in range(1, max_cycles):
        await drive(dut, stochastic_in=window_2_bits[i], boundary_in=1 if i == max_cycles - 1 else 0)
        await clock_step(dut)

    await clock_step(dut)
    expected = golden_model(window_2_bits)
    assert int(dut.binary_out.value) == expected, (
        f"window 2 binary_out={int(dut.binary_out.value)} != expected {expected} "
        f"(bits={window_2_bits}) -- the sample accepted concurrently with window 1's "
        "drain was lost"
    )


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
    await drive(dut, valid_stochastic_in=0, stochastic_in=0, boundary_in=0, ready_binary_out=0)
    await reset_dut(dut.rst_n, dut.clk, 5)

    window_1 = []
    window_2 = []
    for i in range(max_cycles):
        dut_in = random.randint(0, 1)
        window_1.append(dut_in)
        await drive(
            dut,
            valid_stochastic_in=1,
            ready_binary_out=1,
            stochastic_in=dut_in,
            boundary_in=1 if i == max_cycles - 1 else 0,
        )
        await clock_step(dut)

    # Drop valid_stochastic_in (and boundary_in) before the completion edge
    # -- the RTL's completion sequence is one registered transition (latch
    # result, reopen accumulator, all in the same rin update), so this is
    # purely a hygiene precaution against a stray stale boundary_in, not a
    # multi-edge wait like the pre-migration version needed.
    await drive(dut, valid_stochastic_in=0, boundary_in=0)
    await clock_step(dut)

    expected_1 = golden_model(window_1)
    assert dut.valid_binary_out.value == 1
    assert int(dut.binary_out.value) == expected_1, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected_1} "
        f"for window 1 ({window_1})"
    )
    assert dut.ready_stochastic_in.value == 1, "decoder should already be ready to accept window 2's samples"

    for i in range(max_cycles):
        dut_in = random.randint(0, 1)
        window_2.append(dut_in)
        await drive(
            dut,
            valid_stochastic_in=1,
            stochastic_in=dut_in,
            boundary_in=1 if i == max_cycles - 1 else 0,
        )
        await clock_step(dut)

    await clock_step(dut)

    expected_2 = golden_model(window_2)
    assert int(dut.binary_out.value) == expected_2, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected_2} "
        f"for window 2 (window_1={window_1}, window_2={window_2}) -- second window's "
        "result must not be corrupted by the first window"
    )
