import random

import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock

# Integration/loopback test for GitHub issue #2: binary_stochastic_converter
# (the encoder) and stochastic_to_binary (the decoder) each pass their own
# module-level tests but disagree with each other on how many bits make up
# "one window" -- the encoder streams 2**WIDTH bits/burst, the decoder
# accumulates over 2**WIDTH-1 samples. loopback_top.sv wires the encoder's
# stochastic_out straight into the decoder's stochastic_in so that
# composition can be exercised directly, instead of trusting each module's
# isolated testbench to imply correct system-level behavior.
#
# module loopback_top #(
#     parameter int WIDTH = 4
# ) (
#     input  logic             clk,
#     input  logic             rst_n,
#     input  logic [WIDTH-1:0] binary_in,
#     input  logic             valid_binary_in,
#     input  logic             ready_binary_out,
#     output logic             ready_binary_in,
#     output logic             valid_binary_out,
#     output logic [WIDTH-1:0] binary_out
# );
#
# All bookkeeping below runs in a single coroutine, one RisingEdge at a time,
# rather than splitting tape-recording into a separate cocotb.start_soon
# task: two tasks both reacting to the same RisingEdge have no guaranteed
# relative order within that simulation step, which was empirically
# confirmed here to produce a spurious off-by-one in which window a
# boundary-straddling sample got attributed to. Single coroutine, single
# per-cycle snapshot -- no such race is possible.


def golden_model(window_bits):
    """binary_out for one decoder window is just the popcount of whatever
    bits were actually transferred during it -- same accumulation model
    test_stochastic_to_binary.py's golden_model uses, applied here to the
    tape recorded from the real wire instead of a hand-derived bit list.
    """
    return sum(bit for bit, _burst_ordinal in window_bits)


@cocotb.test()
async def single_window_binary_out_matches_actual_transferred_bits(dut):
    """Sanity check with no cross-burst complexity: the decoder's very first
    post-reset window (2**WIDTH-1 samples) is entirely contained within the
    encoder's first burst (2**WIDTH bits), so this just confirms the two
    modules' handshakes compose correctly and the decoder's arithmetic on
    the real wire matches the golden model -- no window-boundary mismatch
    is exercised yet (see the back-to-back test below for that).
    """
    period_ns = 10
    width = len(dut.binary_in)
    max_value = (1 << width) - 1
    max_cycles = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.binary_in.value = random.randint(0, max_value)
    dut.valid_binary_in.value = 1
    dut.ready_binary_out.value = 1

    tape = []
    for _ in range(max_cycles * 4):
        await RisingEdge(dut.clk)
        # Check completion *before* recording this snapshot's transfer: by
        # the cycle valid_binary_out first reads 1, the fast-path reopen has
        # already landed in the same register update, so a transfer
        # condition read at this same snapshot predicts the *next* window's
        # first sample, not one belonging to this window.
        if dut.valid_binary_out.value == 1:
            break
        if dut.valid_stochastic_link.value == 1 and dut.ready_stochastic_link.value == 1:
            tape.append((int(dut.stochastic_link.value), 0))
    else:
        raise AssertionError("decoder never completed a window")

    dut.valid_binary_in.value = 0

    assert len(tape) == max_cycles, (
        f"expected exactly {max_cycles} transferred samples in the first "
        f"window, tape has {len(tape)}: {tape}"
    )
    expected = golden_model(tape)
    assert int(dut.binary_out.value) == expected, (
        f"binary_out={int(dut.binary_out.value)} != golden model expected {expected} "
        f"for actually-transferred bits {tape}"
    )


@cocotb.test()
async def back_to_back_bursts_stay_aligned_under_tight_backpressure_coupling(dut):
    """Empirically investigates GitHub issue #2's window-length mismatch
    with a producer that never drops valid_binary_in (always has the next
    value queued, mirroring test_binary_stochastic.py's
    continuous_valid_binary_in_zero_bubble_back_to_back) and a consumer that
    holds ready_binary_out high throughout.

    The naive expectation (and the issue's original concern) is that a
    decoder window (2**WIDTH-1 samples) is one sample shorter than an
    encoder burst (2**WIDTH bits), so windows should drift relative to
    bursts and eventually straddle two different binary_in values. That
    does NOT happen in this configuration: completing a window forces the
    decoder's ready_stochastic_in low for exactly one cycle (see
    stochastic_binary_converter.sv's `ready_stochastic_in = rst_n &&
    (r.cycle_count != MAX_CYCLES)`, sampled combinationally on the cycle
    cycle_count first reads MAX_CYCLES, before the same-cycle fast-path
    reopen is visible), which stalls the encoder for exactly one cycle too
    (`en = busy && ready_stochastic_out`). That one stall cycle exactly
    absorbs the one-bit length difference, so burst and window boundaries
    stay coincident -- the two modules' independent off-by-ones cancel out
    under tight point-to-point valid/ready coupling.

    This means issue #2's real risk is narrower than originally framed: it
    only bites when the encoder and decoder are *not* directly
    handshake-coupled this way -- e.g. a shared LFSR/bus feeding multiple
    decoders, a FIFO or buffer between them, or anything that lets the
    encoder free-run independent of the decoder's readiness. Worth folding
    back into issue #2 before deciding how urgently to fix the underlying
    off-by-one.

    Still checked here regardless: binary_out is always an honest popcount
    of whatever was actually transferred during that window -- the
    handshake composition and accumulation arithmetic are correct.
    """
    period_ns = 10
    width = len(dut.binary_in)
    max_value = (1 << width) - 1
    max_cycles = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    values = []
    while len(values) < 8:
        candidate = random.randint(0, max_value)
        if not values or candidate != values[-1]:
            values.append(candidate)
    next_value_idx = 1

    dut.binary_in.value = values[0]
    dut.valid_binary_in.value = 1
    dut.ready_binary_out.value = 1

    tape = []
    windows = []  # (binary_out, tape length at the completion cycle)
    burst_ordinal = 0  # values[0]'s burst; incremented on each later accept
    prev_ready_binary_in = 1  # idle post-reset, matches the state set above

    max_wait_cycles = max_cycles * 4 * len(values)
    cycles = 0
    while len(windows) < 6 and cycles < max_wait_cycles:
        await RisingEdge(dut.clk)
        cycles += 1

        ready_binary_in_now = int(dut.ready_binary_in.value)
        if prev_ready_binary_in == 1 and ready_binary_in_now == 0:
            burst_ordinal += 1  # a new burst was just accepted this edge
        prev_ready_binary_in = ready_binary_in_now

        if ready_binary_in_now == 1 and next_value_idx < len(values):
            dut.binary_in.value = values[next_value_idx]
            next_value_idx += 1

        # Completion check comes before recording this snapshot's transfer
        # (see single_window_binary_out_matches_actual_transferred_bits for
        # why: a transfer condition read the same cycle valid_binary_out
        # first reads 1 predicts the *next* window's first sample).
        if dut.valid_binary_out.value == 1 and (
            not windows or windows[-1][1] != len(tape)
        ):
            windows.append((int(dut.binary_out.value), len(tape)))
        elif dut.valid_stochastic_link.value == 1 and dut.ready_stochastic_link.value == 1:
            tape.append((int(dut.stochastic_link.value), burst_ordinal))

    assert len(windows) >= 6, (
        f"decoder only completed {len(windows)} windows in the time budget"
    )

    tape_pos = 0
    for window_idx, (binary_out, tape_len_at_completion) in enumerate(windows):
        window_bits = tape[tape_pos:tape_len_at_completion]
        expected = golden_model(window_bits)
        assert binary_out == expected, (
            f"window {window_idx}: binary_out={binary_out} != popcount of "
            f"actually-transferred bits {expected} for window {window_bits}"
        )
        sources = {source for _bit, source in window_bits}
        assert len(sources) == 1, (
            f"window {window_idx} spans more than one encoder burst "
            f"(sources {sources}): {window_bits}. If this now fails, the "
            "tight backpressure coupling this test relies on to keep "
            "burst/window boundaries aligned (see this test's docstring) "
            "has changed -- re-check whether issue #2 is now live in this "
            "configuration too."
        )
        tape_pos = tape_len_at_completion
