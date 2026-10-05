import cocotb
from cocotb.triggers import RisingEdge
from ma_clkrst import reset_dut, start_clock
from pylfsr import LFSR

# interface
# module galois_lfsr #(
#   parameter int WIDTH = 4,
#   parameter bit [WIDTH-1:0] INIT_SEED = WIDTH'(1)
#   )
# (
#   input logic clk,
#   input logic rst_n,
#   output logic [WIDTH-1:0] out
# );

# Mirrors galois_lfsr.sv's TAPS_LUT exactly -- keep these two tables in sync.
TAPS_LUT = {
    0: 0x0,
    1: 0x0,
    2: 0x1,
    3: 0x1,
    4: 0x4,
    5: 0x4,
    6: 0x10,
    7: 0x20,
    8: 0x38,
    9: 0x10,
    10: 0x40,
    11: 0x100,
    12: 0x29,
    13: 0x241,
    14: 0x409,
    15: 0x2000,
    16: 0x406,
    17: 0x2000,
    18: 0x400,
    19: 0x1101,
    20: 0x10000,
    21: 0x40000,
    22: 0x100000,
    23: 0x20000,
    24: 0x104001,
    25: 0x200000,
    26: 0x142,
    27: 0x13,
    28: 0x1000000,
    29: 0x4000000,
    30: 0x4020001,
    31: 0x8000000,
    32: 0x200003,
    33: 0x1000,
    34: 0xC02,
    35: 0x2,
    36: 0x400,
    37: 0xA02,
    38: 0x14002000,
    39: 0x8,
    40: 0x140002,
    41: 0x4,
    42: 0x4020000040,
    43: 0x38,
    44: 0x32,
    45: 0x40080040000,
    46: 0xC00001,
    47: 0x10,
    48: 0x400002001000,
    49: 0x100,
    50: 0x10080002000,
    51: 0x1200010,
    52: 0x4,
    53: 0x400100200,
    54: 0x20000010080,
    55: 0x800000,
    56: 0x4024000,
    57: 0x40,
    58: 0x40000,
    59: 0x300002,
    60: 0x1,
    61: 0x200000040001000,
    62: 0x8000010000040,
    63: 0x1,
    64: 0x4040000000000020,
}


def fpoly_for(width):
    """TAPS_LUT[width] bit i means galois_lfsr.sv XORs feedback into q[width-1-i]
    -> pylfsr fpoly value i+1 (see state_to_int for why this doesn't need to
    mirror even though the RTL's own tap read *is* mirrored: pylfsr's galois
    branch already applies taps to state[k-1] post-roll, which lands on the
    same q[width-1-i] position once state_to_int's reversed mapping is
    applied -- the two reversals cancel). WIDTH itself is pylfsr's required
    leading term (conf='galois' asserts max(fpoly) == state length).
    """
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


@cocotb.test()
async def matches_pylfsr_galois_reference(dut):
    period_ns = 10
    width = len(dut.out)
    init_seed = int(dut.INIT_SEED.value)
    dut.en.value = 1

    fpoly = fpoly_for(width)
    # Reversed mapping to match state_to_int: initstate[j] = bit (width-1-j) of seed.
    initstate = [(init_seed >> (width - 1 - j)) & 1 for j in range(width)]
    ref = LFSR(fpoly=fpoly, initstate=initstate, conf="galois", verbose=False)

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    n_cycles = 200
    for cycle in range(n_cycles):
        await RisingEdge(dut.clk)
        ref.next()
        expected = state_to_int(ref.state, width)
        actual = int(dut.out.value)
        assert actual == expected, (
            f"cycle {cycle}: dut.out=0x{actual:x} != pylfsr reference=0x{expected:x} "
            f"(WIDTH={width}, fpoly={fpoly}, seed=0x{init_seed:x})"
        )

    cocotb.log.info(
        "WIDTH=%d fpoly=%s: DUT matched pylfsr galois reference for %d cycles",
        width,
        fpoly,
        n_cycles,
    )


# Separate from the reference-model comparison above: a maximal-length LFSR
# must also visit every one of its 2^WIDTH-1 nonzero states exactly once
# before repeating (same methodology ADR 0002/0005 use for real-RTL
# confirmation). This check alone can't prove the taps are wired to the
# *intended* polynomial (any primitive polynomial reaches full length), so
# it's a complement to matches_pylfsr_galois_reference, not a replacement.
@cocotb.test()
async def reaches_maximal_length_cycle(dut):
    period_ns = 10
    width = len(dut.out)
    init_seed = int(dut.INIT_SEED.value)
    expected_period = (1 << width) - 1

    start_clock(dut.clk, period_ns)
    await reset_dut(dut.rst_n, dut.clk, 5)

    seen = []
    seen_set = set()
    for cycle in range(expected_period + 1):
        await RisingEdge(dut.clk)
        actual = int(dut.out.value)
        if actual in seen_set:
            break
        seen_set.add(actual)
        seen.append(actual)

    assert len(seen) == expected_period, (
        f"WIDTH={width} seed=0x{init_seed:x}: cycle closed after {len(seen)} "
        f"unique states, expected maximal length {expected_period} "
        f"(2^{width}-1). First repeated value: 0x{actual:x}"
    )
    assert 0 not in seen_set, (
        f"WIDTH={width}: all-zero state appeared in the cycle -- this must "
        f"never happen for a valid LFSR (NoZeroSeed guards the seed, but a "
        f"broken tap set can still reach zero from a nonzero seed)"
    )

    cocotb.log.info(
        "WIDTH=%d seed=0x%x: DUT visited all %d nonzero states before repeating",
        width,
        init_seed,
        expected_period,
    )
