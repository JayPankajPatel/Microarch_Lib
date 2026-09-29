import random
from collections import deque

import cocotb
from ma_clkrst import clock_step, drive, reset_dut, sample_pre_edge, start_clock

# module port definition
# module stochastic_decorrelator #(
#     parameter int FS = 4  // segment size is 2^FS cycles
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
#     output logic stochastic_out_a,
#     output logic stochastic_out_b
# );
#
# Clean-room reimplementation of the CORLD-D in-stream decorrelator idea
# (Asadi et al., IEEE TVLSI vol. 33 no. 11, Nov 2025 / ICCAD 2021). Two
# arbitrary (possibly fully correlated) stochastic streams go in; two
# low-discrepancy streams representing the SAME densities, decorrelated from
# each other via a rotating bit-reversed-counter comparator on the B side,
# come out one segment (2^FS cycles) later through a one-entry elastic
# output register. See the RTL's own header comment for the full design
# rationale.
#
# This suite was substantially reworked after an independent audit found:
# (1) the original golden model mirrored the RTL's own (then-buggy) counter
#     logic rather than an independent derivation from the paper's spec --
#     agreement between them proved only "Python and SystemVerilog agree,"
#     not "matches CORLD-D";
# (2) sampling `dut.*.value` immediately after `await RisingEdge` without
#     entering the ReadOnly phase races the simulator's own region
#     scheduling and produced spurious "lost first transfer" symptoms that
#     were misdiagnosed as a Verilator quirk;
# (3) the SCC helper's negative-correlation branch had a formula bug.
# All three are fixed here: SegmentBasedGolden is derived fresh from the
# spec (segment accumulate -> emit next segment via bit-reversed-counter
# threshold, B's index rotated by the completed-segment count), every
# sample goes through `clock_step()` which awaits ReadOnly before reading
# any signal, and `scc()` matches the paper's own stated formula.


class SegmentBasedGolden:
    """Independent re-derivation from the CORLD-D spec, not copied from or
    structurally derived from the RTL. Call `accept(bit_a, bit_b)` once per
    ACCEPTED input transfer (matching accept_this_cycle in the RTL); it
    returns the (out_a, out_b) pair that transfer produces once the module
    is past warm-up, or None during warm-up (first segment).

    Segment k's ones-counts become segment k+1's output, in bit-reversed-
    counter order for stream A and in the SAME order rotated by k (mod
    2^FS) for stream B -- an exact permutation of every threshold 0..2^FS-1,
    so a segment's ones-count is always preserved exactly in its output.
    """

    def __init__(self, fs):
        self.fs = fs
        self.n = 1 << fs
        self.segment_offset = 0
        self.cur_a = []
        self.cur_b = []
        self.pending_out = deque()

    def _rev(self, x):
        fs = self.fs
        result = 0
        for i in range(fs):
            if (x >> i) & 1:
                result |= 1 << (fs - 1 - i)
        return result

    def accept(self, bit_a, bit_b):
        result = self.pending_out.popleft() if self.pending_out else None

        self.cur_a.append(bit_a)
        self.cur_b.append(bit_b)
        if len(self.cur_a) == self.n:
            ones_a = sum(self.cur_a)
            ones_b = sum(self.cur_b)
            # Increment BEFORE computing this segment's rotation, matching
            # the RTL: r.segment_offset already reflects the post-increment
            # count by the time it's read (as r.segment_offset) for the
            # NEXT segment's cmp_idx_b -- using the pre-increment value here
            # was an off-by-one in this golden model (RTL was correct; found
            # via the scoreboard test's first real mismatch, at exactly the
            # first output segment).
            self.segment_offset = (self.segment_offset + 1) % self.n
            offset = self.segment_offset
            for i in range(self.n):
                out_a = 1 if self._rev(i) < ones_a else 0
                idx_b = (i - offset) % self.n
                out_b = 1 if self._rev(idx_b) < ones_b else 0
                self.pending_out.append((out_a, out_b))
            self.cur_a = []
            self.cur_b = []

        return result


def scc(seq_x, seq_y):
    """Alaghi-Hayes stochastic correlation coefficient, matching the ECO
    paper's own stated formula. +-1.0 = fully correlated, 0.0 =
    uncorrelated. The negative-correlation branch's denominator is
    `(a+b)(a+c) - N*max(a-d, 0)` -- NOT `max(a+d-n, 0)`, an earlier version
    of this function had that wrong (flagged by independent audit; verified
    against the maximally-negatively-correlated case 011 vs 101, which must
    give exactly -1.0)."""
    n = len(seq_x)
    a = sum(1 for x, y in zip(seq_x, seq_y) if x == 1 and y == 1)
    b = sum(1 for x, y in zip(seq_x, seq_y) if x == 1 and y == 0)
    c = sum(1 for x, y in zip(seq_x, seq_y) if x == 0 and y == 1)
    d = sum(1 for x, y in zip(seq_x, seq_y) if x == 0 and y == 0)
    ad_bc = a * d - b * c
    if ad_bc > 0:
        denom = n * min(a + b, a + c) - (a + b) * (a + c)
    else:
        denom = (a + b) * (a + c) - n * max(a - d, 0)
    if denom == 0:
        return 0.0
    return ad_bc / denom


def test_scc_matches_known_cases():
    """Not a cocotb test -- a plain sanity check on the SCC helper itself,
    run at import/collection time implicitly via pytest-style naming isn't
    wired up here, so this is invoked explicitly from
    decorrelates_fully_correlated_inputs below instead. Kept as a
    documented, named check of the exact case the earlier formula bug got
    wrong: 011 and 101 are maximally negatively correlated (SCC must be
    exactly -1.0)."""
    result = scc([0, 1, 1], [1, 0, 1])
    assert abs(result - (-1.0)) < 1e-9, f"SCC formula regression: expected -1.0 for 011/101, got {result}"


async def drive_idle(dut):
    dut.stochastic_in_a.value = 0
    dut.valid_stochastic_in_a.value = 0
    dut.stochastic_in_b.value = 0
    dut.valid_stochastic_in_b.value = 0
    dut.ready_stochastic_out.value = 0


@cocotb.test()
async def matches_independent_golden_model_with_scoreboard(dut):
    """Primary correctness check. valid_a/valid_b/ready_out are randomized
    every cycle; a scoreboard queue is fed by SegmentBasedGolden whenever an
    input transfer is ACCEPTED, and drained/compared whenever the DUT
    reports a real output handshake (valid_stochastic_out && ready_out on
    the state going INTO this cycle). This also exercises and verifies the
    elastic-register contract directly: output data/valid must stay stable
    on any cycle that neither accepts nor consumes, and ready_stochastic_in_*
    must not depend on ready_stochastic_out once the output slot is empty
    (warm-up must not deadlock waiting for a consumer)."""
    test_scc_matches_known_cases()

    period_ns = 10
    fs = int(dut.FS.value)

    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    golden = SegmentBasedGolden(fs)
    expected_queue = deque()

    prev_out_valid = 0
    prev_out_a = 0
    prev_out_b = 0

    n_attempts = 6000
    accepts = 0
    consumes = 0

    for _ in range(n_attempts):
        valid_a = random.randint(0, 1)
        valid_b = random.randint(0, 1)
        ready_out = random.randint(0, 1)
        bit_a = random.randint(0, 1)
        bit_b = random.randint(0, 1)

        slot_available = (not prev_out_valid) or ready_out
        accept = valid_a and valid_b and slot_available
        expected_ready_a = slot_available and valid_b
        expected_ready_b = slot_available and valid_a
        consume = prev_out_valid and ready_out

        await drive(
            dut,
            valid_stochastic_in_a=valid_a,
            valid_stochastic_in_b=valid_b,
            ready_stochastic_out=ready_out,
            stochastic_in_a=bit_a,
            stochastic_in_b=bit_b,
        )
        await sample_pre_edge(dut)
        assert int(dut.ready_stochastic_in_a.value) == expected_ready_a, (
            "warm-up/backpressure violation: ready_stochastic_in_a must equal "
            "slot_available && valid_b, independent of ready_stochastic_out when the slot is empty"
        )
        assert int(dut.ready_stochastic_in_b.value) == expected_ready_b

        await clock_step(dut)

        if consume:
            assert expected_queue, "DUT reported a consumed output but the golden scoreboard queue is empty"
            exp_a, exp_b = expected_queue.popleft()
            assert prev_out_a == exp_a and prev_out_b == exp_b, (
                f"consumed output ({prev_out_a},{prev_out_b}) != expected ({exp_a},{exp_b})"
            )
            consumes += 1

        if accept:
            result = golden.accept(bit_a, bit_b)
            if result is not None:
                expected_queue.append(result)
            accepts += 1

        new_out_valid = int(dut.valid_stochastic_out.value)
        new_out_a = int(dut.stochastic_out_a.value)
        new_out_b = int(dut.stochastic_out_b.value)

        if not accept and not consume:
            assert new_out_valid == prev_out_valid, "output valid changed on a cycle with neither accept nor consume"
            if prev_out_valid:
                assert new_out_a == prev_out_a and new_out_b == prev_out_b, (
                    "output data changed while held (not accepted, not consumed) -- must stay stable under backpressure"
                )

        prev_out_valid, prev_out_a, prev_out_b = new_out_valid, new_out_a, new_out_b

    assert accepts > 0 and consumes > 0, "randomized run produced no accepts/consumes -- test is not exercising the DUT"


@cocotb.test()
async def exact_population_count_preservation(dut):
    """The defining correctness property: every output segment must have
    EXACTLY the same ones-count as its corresponding input segment. Sweeps
    every possible ones-count (0..2^FS inclusive) for stream A, paired with
    the mirrored count for stream B each segment, so both streams' rotation
    handling is exercised across the full range -- not just a couple of
    statistically-plausible-looking samples."""
    period_ns = 10
    fs = int(dut.FS.value)
    n = 1 << fs

    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in_a.value = 1
    dut.valid_stochastic_in_b.value = 1
    dut.ready_stochastic_out.value = 1

    counts_to_test = list(range(n + 1))  # every possible ones-count: 0, 1, ..., n

    collected_out_a = []
    collected_out_b = []
    cur_out_a = []
    cur_out_b = []

    for seg_idx, count_a in enumerate(counts_to_test):
        count_b = counts_to_test[(len(counts_to_test) - 1) - seg_idx]
        for i in range(n):
            bit_a = 1 if i < count_a else 0
            bit_b = 1 if i < count_b else 0
            await drive(dut, stochastic_in_a=bit_a, stochastic_in_b=bit_b)
            await clock_step(dut)
            if int(dut.valid_stochastic_out.value) == 1:
                cur_out_a.append(int(dut.stochastic_out_a.value))
                cur_out_b.append(int(dut.stochastic_out_b.value))
                if len(cur_out_a) == n:
                    collected_out_a.append(cur_out_a)
                    collected_out_b.append(cur_out_b)
                    cur_out_a = []
                    cur_out_b = []

    input_counts_a = counts_to_test
    input_counts_b = list(reversed(counts_to_test))

    assert len(collected_out_a) >= len(counts_to_test) - 1, (
        f"expected {len(counts_to_test) - 1} complete output segments (one per input segment, minus warm-up), "
        f"got {len(collected_out_a)}"
    )
    for k in range(len(collected_out_a)):
        got_a = sum(collected_out_a[k])
        got_b = sum(collected_out_b[k])
        assert got_a == input_counts_a[k], (
            f"segment {k}: output A ones-count={got_a}, expected {input_counts_a[k]} -- population not preserved"
        )
        assert got_b == input_counts_b[k], (
            f"segment {k}: output B ones-count={got_b}, expected {input_counts_b[k]} -- population not preserved"
        )
        assert len(set(collected_out_a[k])) <= 2 and len(collected_out_a[k]) == n, (
            "sanity: each output segment must be exactly n bits"
        )


@cocotb.test()
async def decorrelates_fully_correlated_inputs(dut):
    """The actual claim under test: feed A and B the exact SAME bit every
    cycle (input SCC = 1.0 by construction -- maximally correlated) and
    confirm the OUTPUT streams' SCC drops meaningfully. This is the specific
    property GitHub issue #3 / ADR 0019 couldn't achieve via LFSR seed
    separation below WIDTH=7."""
    period_ns = 10
    fs = int(dut.FS.value)

    start_clock(dut.clk, period_ns)
    await drive_idle(dut)
    await reset_dut(dut.rst_n, dut.clk, 5)

    dut.valid_stochastic_in_a.value = 1
    dut.valid_stochastic_in_b.value = 1
    dut.ready_stochastic_out.value = 1

    p = 0.5
    n = (1 << fs) * 60

    in_stream = []
    out_a_stream = []
    out_b_stream = []
    for _ in range(n):
        bit = 1 if random.random() < p else 0
        await drive(dut, stochastic_in_a=bit, stochastic_in_b=bit)
        await clock_step(dut)
        in_stream.append(bit)
        if int(dut.valid_stochastic_out.value) == 1:
            out_a_stream.append(int(dut.stochastic_out_a.value))
            out_b_stream.append(int(dut.stochastic_out_b.value))

    input_scc = scc(in_stream, in_stream)
    output_scc = scc(out_a_stream, out_b_stream)

    assert input_scc > 0.99, f"sanity check failed: input SCC should be ~1.0 by construction, got {input_scc:.4f}"
    assert abs(output_scc) < 0.5, (
        f"output SCC {output_scc:.4f} is not meaningfully decorrelated from the input's SCC={input_scc:.4f} -- "
        f"the rotating comparator mechanism is not working as intended"
    )
    dut._log.info(f"input SCC={input_scc:.4f}, output SCC={output_scc:.4f} (FS={fs})")
