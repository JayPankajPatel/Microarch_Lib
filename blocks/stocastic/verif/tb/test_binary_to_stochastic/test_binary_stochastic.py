import random

import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock
from pylfsr import LFSR

# interface
# module binary_stochastic_converter #(
#     parameter int WIDTH = 2
# ) (
#     input logic clk,
#     input logic [WIDTH-1:0] binary_in,
#     input logic rst_n,
#     input logic valid_binary_in,
#     input logic ready_stochastic_out,
#     output logic ready_binary_in,
#     output logic valid_stochastic_out,
#     output logic stochastic_out
# );

# Protocol under test (see binary_stochastic_timing_diagram.svg):
#  - binary_in is accepted in the cycle where valid_binary_in && ready_binary_in
#    are both high (the converter is idle, i.e. not mid-burst).
#  - The next cycle onward, the converter streams exactly 2**WIDTH-1
#    stochastic bits (one full clean galois_lfsr period -- see GitHub issue
#    #2 and docs/adr/0005/0006 for why it isn't 2**WIDTH), one per cycle it
#    isn't stalled, each equal to
#    (lfsr_state < accepted_binary_in). valid_stochastic_out stays high for
#    the entire burst -- it does not toggle per bit.
#  - Downstream backpressure (ready_stochastic_out == 0) holds the current
#    bit steady (the LFSR/counter simply don't advance that cycle) and
#    stretches the burst by exactly one cycle per stalled cycle.
#  - ready_binary_in reasserts the cycle after the last bit of the burst is
#    consumed (ready_stochastic_out high on that last-bit cycle), and the
#    converter is ready to accept a new binary_in from then on.


# Mirrors galois_lfsr.sv's TAPS_LUT exactly -- keep these two tables in sync.
# (Same table as test_galois_lfsr.py; duplicated rather than imported since
# each block's testbench directory is self-contained -- see common.mk's
# PYTHONPATH, which only exposes common/verif, not sibling tb/ directories.)
TAPS_LUT = {
    0: 0x0, 1: 0x0, 2: 0x1, 3: 0x1, 4: 0x4, 5: 0x4, 6: 0x10, 7: 0x20,
    8: 0x38, 9: 0x10, 10: 0x40, 11: 0x100, 12: 0x29, 13: 0x241, 14: 0x409,
    15: 0x2000, 16: 0x406, 17: 0x2000, 18: 0x400, 19: 0x1101, 20: 0x10000,
    21: 0x40000, 22: 0x100000, 23: 0x20000, 24: 0x104001, 25: 0x200000,
    26: 0x142, 27: 0x13, 28: 0x1000000, 29: 0x4000000, 30: 0x4020001,
    31: 0x8000000, 32: 0x200003, 33: 0x1000, 34: 0xC02, 35: 0x2, 36: 0x400,
    37: 0xA02, 38: 0x14002000, 39: 0x8, 40: 0x140002, 41: 0x4,
    42: 0x4020000040, 43: 0x38, 44: 0x32, 45: 0x40080040000, 46: 0xC00001,
    47: 0x10, 48: 0x400002001000, 49: 0x100, 50: 0x10080002000,
    51: 0x1200010, 52: 0x4, 53: 0x400100200, 54: 0x20000010080,
    55: 0x800000, 56: 0x4024000, 57: 0x40, 58: 0x40000, 59: 0x300002,
    60: 0x1, 61: 0x200000040001000, 62: 0x8000010000040, 63: 0x1,
    64: 0x4040000000000020,
}


def fpoly_for(width):
    """TAPS_LUT[width] bit i means galois_lfsr.sv XORs feedback into
    q[width-1-i] -> pylfsr fpoly value i+1 (see docs/adr/0006)."""
    mask = TAPS_LUT[width]
    taps = [i + 1 for i in range(width) if (mask >> i) & 1]
    return sorted(set(taps + [width]), reverse=True)


def state_to_int(state, width):
    # pylfsr's galois branch sources feedback from state[0] and shifts new
    # bits into state[-1] -- the opposite end from galois_lfsr.sv, which
    # sources feedback from q[WIDTH-1] and shifts new bits into q[0]. So
    # state[j] corresponds to q[width-1-j], not q[j]. Verified empirically
    # against the RTL's actual recurrence for WIDTH=4,13,19 before trusting
    # this mapping (see docs/adr/0006).
    value = 0
    for j, bit in enumerate(state):
        value |= (int(bit) & 1) << (width - 1 - j)
    return value


def golden_model(width, lfsr_state, binary_in_value):
    """Independently predict one full 2**WIDTH-1-bit burst (one clean
    galois_lfsr period -- see GitHub issue #2) for a given binary_in, using
    pylfsr as the LFSR reference (same construction test_galois_lfsr.py
    already validates the RTL against) rather than reading the DUT's
    internal random_number signal.

    `lfsr_state` is the LFSR's *current* state going into this burst -- only
    INIT_SEED for the very first burst after reset. Since the LFSR isn't
    reset between bursts (only rst_n resets it), back-to-back bursts must
    thread the returned `end_state` into the next call's `lfsr_state`, or
    the golden model desyncs from the DUT after the first burst.

    Returns `(bits, end_state)`: `bits` is a list of 2**WIDTH-1 bits in
    emission order (index 0 == first bit of the burst); `end_state` is the
    LFSR's state after this burst's 2**WIDTH-1 advances, to feed into the
    next call.
    """
    fpoly = fpoly_for(width)
    initstate = [(lfsr_state >> (width - 1 - j)) & 1 for j in range(width)]
    ref = LFSR(fpoly=fpoly, initstate=initstate, conf="galois", verbose=False)

    # Bit 0 of a burst is compared against lfsr_state itself -- the accept
    # cycle registers en=1 but the LFSR's own always_ff hasn't fired yet, so
    # random_number still reads the pre-burst state for that first bit (see
    # the cyc0/cyc1 debug trace: rand=1(seed) on the first bit, rand=2 on
    # the second). Each subsequent bit compares against the state one
    # ref.next() further along, matching the RTL's per-bit LFSR advance.
    state = state_to_int(initstate, width)
    bits = []
    for _ in range((1 << width) - 1):
        bits.append(1 if state < binary_in_value else 0)
        ref.next()
        state = state_to_int(ref.state, width)
    return bits, state


async def accept_transfer(dut, binary_in_value):
    """Drive one binary_in handshake; returns on the cycle acceptance takes
    effect (ready_binary_in drops from its idle-high to 0), at which point
    bit 0 of the burst is already valid on stochastic_out this same cycle."""
    dut.binary_in.value = binary_in_value
    dut.valid_binary_in.value = 1
    dut.ready_stochastic_out.value = 1
    while True:
        await RisingEdge(dut.clk)
        if dut.ready_binary_in.value == 0:
            break
    dut.valid_binary_in.value = 0


async def stream_burst(dut, expected_bits, stall_at=None, stall_len=0):
    """Consume one full burst, checking each bit against `expected_bits`
    (from golden_model) and the valid/ready protocol. `stall_at` (if given)
    is the bit index at which to hold ready_stochastic_out low for
    `stall_len` cycles before resuming, to exercise the backpressure/stall
    behavior from the diagram.

    Timing note: a value written to ready_stochastic_out from a running
    cocotb coroutine isn't visible to the DUT's combinational `en` logic
    until the clock edge *after* the next one -- the edge immediately
    following a write still behaves as if the old value were still driven
    (confirmed empirically: en reads back stale in the same instant the
    write is issued, and one extra LFSR advance slips through on the very
    next edge). Both dropping and re-raising ready_stochastic_out therefore
    need one "settling" edge before the new value's effect is real; that
    settling bit is still checked against the golden model (it's a normal
    bit, not yet an actual stall), just not yet subject to the hold check.
    """
    bits_consumed = 0
    saw_valid = False

    while bits_consumed < len(expected_bits):
        assert (
            dut.valid_stochastic_out.value == 1
        ), f"valid_stochastic_out dropped mid-burst at bit {bits_consumed}"
        saw_valid = True

        expected_bit = expected_bits[bits_consumed]
        actual_bit = int(dut.stochastic_out.value)
        assert actual_bit == expected_bit, (
            f"bit {bits_consumed}: stochastic_out={actual_bit} != "
            f"golden model expected {expected_bit}"
        )

        if stall_at is not None and bits_consumed == stall_at and stall_len > 0:
            dut.ready_stochastic_out.value = 0

            await RisingEdge(dut.clk)  # settling edge: write not visible yet
            bits_consumed += 1
            assert int(dut.stochastic_out.value) == expected_bits[bits_consumed], (
                f"settling bit {bits_consumed} (ready_stochastic_out drop "
                f"not yet visible to the DUT) didn't match the golden model"
            )

            held_bit = int(dut.stochastic_out.value)
            for _ in range(stall_len):
                await RisingEdge(dut.clk)
                assert (
                    dut.valid_stochastic_out.value == 1
                ), "valid_stochastic_out must stay asserted through a stall"
                assert (
                    int(dut.stochastic_out.value) == held_bit
                ), "stochastic_out must hold steady while stalled"

            dut.ready_stochastic_out.value = 1
            await RisingEdge(dut.clk)  # settling edge: still behaves as stalled
            assert int(dut.stochastic_out.value) == held_bit, (
                "resume settling cycle (ready_stochastic_out raise not yet "
                "visible to the DUT) should still show the held bit"
            )
            continue

        await RisingEdge(dut.clk)
        bits_consumed += 1

    assert saw_valid, "burst never asserted valid_stochastic_out"


@cocotb.test()
async def single_transfer_matches_waveform_protocol(dut):
    """No stalls: a full burst streams valid, bit-for-bit, then hands off cleanly."""
    period_ns = 10
    width = len(dut.binary_in)
    max_value = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    assert dut.ready_binary_in.value == 1, "converter should be idle-ready after reset"

    init_seed = int(dut.RNG.INIT_SEED.value)
    binary_in_value = random.randint(0, max_value)
    expected_bits, _ = golden_model(width, init_seed, binary_in_value)

    await accept_transfer(dut, binary_in_value)
    await stream_burst(dut, expected_bits)

    await RisingEdge(dut.clk)
    assert dut.valid_stochastic_out.value == 0, "valid must drop after the last bit"
    assert (
        dut.ready_binary_in.value == 1
    ), "ready_binary_in must reassert after the burst"


@cocotb.test()
async def stall_holds_bit_and_stretches_busy(dut):
    """Backpressure mid-burst holds the current bit and delays completion,
    matching the diagram's repeated `b2` while ready_stochastic_out is low."""
    period_ns = 10
    width = len(dut.binary_in)
    max_value = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    init_seed = int(dut.RNG.INIT_SEED.value)
    binary_in_value = random.randint(0, max_value)
    expected_bits, _ = golden_model(width, init_seed, binary_in_value)

    # stall_at must leave room for stream_burst's post-stall "settling bit"
    # check (it indexes expected_bits[stall_at+1]) -- bit 2 is safely
    # mid-burst for WIDTH>=3 (burst length 2**WIDTH-1 >= 7), but at WIDTH=2
    # the burst is only 3 bits long and bit 2 is the last one, so clamp.
    stall_at = min(2, len(expected_bits) - 2)
    await accept_transfer(dut, binary_in_value)
    await stream_burst(dut, expected_bits, stall_at=stall_at, stall_len=2)

    await RisingEdge(dut.clk)
    assert dut.valid_stochastic_out.value == 0
    assert dut.ready_binary_in.value == 1


@cocotb.test()
async def back_to_back_transfers(dut):
    """After one burst completes, a new binary_in can be accepted immediately.

    Also directly checks RNG.out against the golden model's threaded LFSR
    state at the start of every burst -- this is the actual reproducibility
    property GitHub issue #2 was about (a burst-to-burst phase drift is
    exactly what an out_counter that leaks residual state across bursts
    would cause, per docs/adr/0013), not just "does stochastic_out match
    bit-for-bit" (which stream_burst already checks but which wouldn't by
    itself distinguish a clean-period desync from a coincidentally-matching
    one over just 3 bursts).
    """
    period_ns = 10
    width = len(dut.binary_in)
    max_value = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    lfsr_state = int(dut.RNG.INIT_SEED.value)
    for _ in range(3):
        assert int(dut.RNG.out.value) == lfsr_state, (
            "LFSR state at burst start must match the golden model's "
            "threaded state -- a mismatch here means out_counter (or the "
            "LFSR itself) is leaking state across bursts instead of "
            "completing one clean period per burst"
        )
        binary_in_value = random.randint(0, max_value)
        expected_bits, lfsr_state = golden_model(width, lfsr_state, binary_in_value)
        await accept_transfer(dut, binary_in_value)
        await stream_burst(dut, expected_bits)
        await RisingEdge(dut.clk)
        assert dut.ready_binary_in.value == 1


@cocotb.test()
async def continuous_valid_binary_in_zero_bubble_back_to_back(dut):
    """A producer that never drops valid_binary_in (always has the next
    value ready to go) must still see: (1) burst 1's binary_in_d isn't
    corrupted by binary_in changing on the bus mid-burst -- only the
    accept-cycle's `if (!r.busy)` branch ever writes binary_in_d, and it's
    structurally unreachable while r.busy == 1, since the always_comb block
    branches on r.busy first; (2) burst 2 is accepted on the earliest cycle
    it possibly could be -- the very first cycle ready_binary_in reads 1 --
    with no extra delay beyond the one register-latency cycle any
    registered-output FSM inherently needs (rin computed this cycle is only
    visible on outputs next cycle, so "burst ends" and "next burst visibly
    started" can never land on the same observable cycle, continuously-held
    valid_binary_in or not).
    """
    period_ns = 10
    width = len(dut.binary_in)
    max_value = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    lfsr_state = int(dut.RNG.INIT_SEED.value)

    binary_in_1 = random.randint(0, max_value)
    binary_in_2 = random.randint(0, max_value)
    while binary_in_2 == binary_in_1:  # keep them distinct so corruption is detectable
        binary_in_2 = random.randint(0, max_value)

    expected_bits_1, lfsr_state = golden_model(width, lfsr_state, binary_in_1)
    expected_bits_2, lfsr_state = golden_model(width, lfsr_state, binary_in_2)

    dut.binary_in.value = binary_in_1
    dut.valid_binary_in.value = 1
    dut.ready_stochastic_out.value = 1
    while True:
        await RisingEdge(dut.clk)
        if dut.ready_binary_in.value == 0:
            break

    # Burst 1 accepted. Immediately swap binary_in to the second value while
    # keeping valid_binary_in asserted the whole time -- this is the
    # "producer never drops valid, always has the next value queued up"
    # scenario. If binary_in_d were ever wrongly re-latched mid-burst, this
    # would corrupt burst 1's bits with binary_in_2 partway through.
    dut.binary_in.value = binary_in_2

    await stream_burst(dut, expected_bits_1)

    # This is the one register-latency idle cycle every registered-output
    # FSM needs: ready_binary_in has *just* become 1 (rin computed on the
    # last-bit cycle is only now visible), so the earliest the accept
    # condition can even be *evaluated* is this cycle -- not before.
    assert dut.ready_binary_in.value == 1, (
        "expected exactly the one unavoidable idle cycle where "
        "ready_binary_in first reads 1 before the next burst can start"
    )
    assert dut.valid_stochastic_out.value == 0

    # Since valid_binary_in and ready_stochastic_out were already both
    # asserted going into this cycle, the accept condition fires this same
    # cycle -- so burst 2 must be visibly running by the very next edge,
    # with no *additional* delay beyond that one unavoidable idle cycle.
    await RisingEdge(dut.clk)
    assert dut.ready_binary_in.value == 0, (
        "burst 2 should be accepted immediately (no extra delay beyond the "
        "one unavoidable register-latency cycle), since valid_binary_in was "
        "already held high"
    )
    assert dut.valid_stochastic_out.value == 1

    dut.valid_binary_in.value = 0
    await stream_burst(dut, expected_bits_2)

    await RisingEdge(dut.clk)
    assert dut.valid_stochastic_out.value == 0
    assert dut.ready_binary_in.value == 1
