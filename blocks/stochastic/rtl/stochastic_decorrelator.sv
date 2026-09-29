`include "ma_assert.svh"
// Clean-room reimplementation of the CORLD-D in-stream decorrelator idea
// from Asadi et al., "ECO: Enhanced In-Stream Correlation Manipulation for
// Low-Discrepancy Stochastic Computing" (IEEE TVLSI vol. 33 no. 11, Nov
// 2025) and its ICCAD 2021 predecessor "CORLD." NOT a port of either
// paper's reference Verilog (github.com/asadisina/CORLD): that code uses
// blocking assignments inside clocked always blocks (sim/synth mismatch
// risk) and never resets one of its own output registers. This module
// implements the algorithm from the papers' prose description instead, in
// this repo's own Gaisler two-process style, and is verified against this
// repo's own methodology (exact population-count preservation, an
// independent golden model, and a queue-based ready/valid scoreboard)
// rather than the papers' own reported numbers -- see docs/adr/0019 for why
// "a paper/vendor says it works" is not sufficient evidence in this
// codebase. This module targets only CORLD-D (Section III); the paper's
// CORLD-C correlator (Section II-A, for operations like min/max that need
// positively-correlated inputs, not our multiply use case) and the ECO
// balancing enhancement (Section IV, for pseudorandom/LFSR-sourced streams
// specifically) are out of scope here and not implemented.
//
// Core idea: this repo's existing decorrelation approach (separate LFSR
// seeds far enough apart in phase -- ADR 0018/0019) requires the streams
// to already be independent-by-construction, and provably cannot achieve
// that below WIDTH=7 (the LFSR period is too short relative to any useful
// sample count, regardless of seed choice). This module instead takes two
// ARBITRARY (possibly fully correlated, e.g. from a single shared LFSR) 1-
// bit-per-cycle stochastic streams and re-quantizes each into a low-
// discrepancy bitstream representing the SAME density, using a bit-
// reversed counter as a deterministic Sobol-like threshold source (a Van
// der Corput sequence) instead of an LFSR at all -- so it isn't subject to
// the LFSR-period constraint ADR 0019 found.
//
// Stream A's comparator index is simply its position within the current
// segment (`cnt`). Stream B's comparator index is `cnt` rotated by
// `segment_offset` -- the number of segments completed so far, mod 2^FS --
// so each successive output segment uses a circularly-shifted copy of the
// SAME bit-reversed threshold ordering. This is an exact permutation (every
// index 0..2^FS-1 appears exactly once per segment, so a segment's ones
// count is always preserved exactly), unlike a naive fixed/only-sometimes
// mechanism: a CONSTANT (non-rotating) offset would not decorrelate two
// equal-density streams, since both would threshold the same accumulated
// count against the same fixed pattern, merely shifted, every segment. The
// rotation sweeps the relative phase between the two grids through the
// full range over 2^FS segments instead of staying fixed.
//
// One segment (2^FS real-transfer cycles) of latency: a segment's ones-
// count is only known once fully accumulated, so it's quantized into the
// NEXT segment's output, not its own.
//
// The output side is a proper one-entry elastic register (skid buffer),
// not a bare combinational pass-through: `out_valid` marks the slot
// occupied, new input pairs are only accepted once the slot is empty or
// is being drained this same cycle (so warm-up never depends on
// `ready_stochastic_out`, and a stalled input never causes a stale output
// to be silently re-consumed under `valid && ready`).
module stochastic_decorrelator #(
    parameter int FS = 4  // segment size is 2^FS cycles
) (
    input  logic clk,
    input  logic rst_n,
    input  logic stochastic_in_a,
    input  logic valid_stochastic_in_a,
    output logic ready_stochastic_in_a,
    input  logic stochastic_in_b,
    input  logic valid_stochastic_in_b,
    output logic ready_stochastic_in_b,
    input  logic ready_stochastic_out,
    output logic valid_stochastic_out,
    output logic stochastic_out_a,
    output logic stochastic_out_b
);
  // Practical, explicitly-verified range -- matches the paper's own
  // evaluated FS=2..5 (Tables I/II/IV), not an unverified upper bound.
  `MA_ASSERT_ELABOR(ValidFixerSize, FS inside {[2 : 8]})

  localparam int unsigned SegMax = (1 << FS) - 1;

  // Reverses the low FS bits of x -- the Van der Corput / Sobol-like
  // ordering that turns "count 0, 1, 2, ..." into a low-discrepancy
  // (uniformly-spaced-as-you-go) sequence when used as a comparator
  // threshold source, per docs/adr/0008's precedent for automatic
  // functions parsing under Yosys's native frontend.
  function automatic logic [FS-1:0] rev_bits(input logic [FS-1:0] x);
    for (int i = 0; i < FS; i++) rev_bits[i] = x[FS-1-i];
  endfunction

  typedef struct packed {
    logic [FS-1:0] cnt;             // shared accumulation-segment position (A and B)
    logic [FS:0]   acc_a;           // A's current-segment ones accumulator
    logic [FS:0]   reg_a;           // A's previous-segment ones count (quantized this segment)
    logic [FS:0]   acc_b;           // B's current-segment ones accumulator
    logic [FS:0]   reg_b;           // B's previous-segment ones count
    logic [FS-1:0] segment_offset;  // completed-segment count mod 2^FS -- B's rotation amount
    logic          enabled;         // first segment has fully completed
    logic          out_a;
    logic          out_b;
    logic          out_valid;       // output slot occupied (elastic register)
  } decorr_t;
  decorr_t r, rin;

  // Elastic-register accept/ready: a new input pair is accepted whenever
  // the output slot is empty OR is being drained this same cycle (zero-
  // bubble refill, same pattern stochastic_to_binary.sv uses for its own
  // window-boundary reopen) -- critically, accept does NOT require
  // ready_stochastic_out when the slot is already empty, so warm-up (no
  // output has ever been produced yet) can proceed with no downstream
  // consumer at all. Neither input's readiness depends on its OWN validity
  // gating the other, matching the two-producer join pattern
  // stochastic_multiplier.sv/stochastic_adder.sv use per ADR 0012/0016.
  logic slot_available;
  logic accept_this_cycle;
  assign slot_available = !r.out_valid || ready_stochastic_out;
  assign accept_this_cycle = valid_stochastic_in_a && valid_stochastic_in_b && slot_available;
  assign ready_stochastic_in_a = slot_available && valid_stochastic_in_b;
  assign ready_stochastic_in_b = slot_available && valid_stochastic_in_a;

  always_comb begin
    logic segment_done;
    logic [FS-1:0] cmp_idx_b;
    logic consume_this_cycle;
    rin = r;
    segment_done = (r.cnt == FS'(SegMax));
    cmp_idx_b = r.cnt - r.segment_offset;  // FS-bit wraparound subtraction: exact mod-2^FS rotation
    consume_this_cycle = r.out_valid && ready_stochastic_out;

    if (accept_this_cycle) begin
      // Outputs use THIS cycle's pre-update comparator index against the
      // ALREADY-LATCHED previous-segment counts (r.reg_a/r.reg_b) -- one
      // segment of pipeline latency, matching "accumulate this segment,
      // quantize during the next."
      rin.out_a = (FS + 1)'(rev_bits(r.cnt)) < r.reg_a;
      rin.out_b = (FS + 1)'(rev_bits(cmp_idx_b)) < r.reg_b;
      rin.out_valid = r.enabled;

      if (segment_done) begin
        rin.reg_a = r.acc_a + (FS + 1)'(stochastic_in_a);
        rin.acc_a = '0;
        rin.reg_b = r.acc_b + (FS + 1)'(stochastic_in_b);
        rin.acc_b = '0;
        rin.enabled = 1'b1;
        rin.cnt = '0;
        rin.segment_offset = r.segment_offset + 1'b1;
      end else begin
        rin.acc_a = r.acc_a + (FS + 1)'(stochastic_in_a);
        rin.acc_b = r.acc_b + (FS + 1)'(stochastic_in_b);
        rin.cnt = r.cnt + 1'b1;
      end
    end else if (consume_this_cycle) begin
      // Slot drained this cycle with nothing to refill it -- clear valid
      // rather than let the consumer see a "successful" valid&&ready
      // handshake against data that's actually a stale repeat.
      rin.out_valid = 1'b0;
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      r.cnt <= '0;
      r.acc_a <= '0;
      r.reg_a <= '0;
      r.acc_b <= '0;
      r.reg_b <= '0;
      r.segment_offset <= '0;
      r.enabled <= '0;
      r.out_a <= '0;
      r.out_b <= '0;
      r.out_valid <= '0;
    end else begin
      r <= rin;
    end
  end

  assign valid_stochastic_out = rst_n && r.out_valid;
  assign stochastic_out_a = r.out_a;
  assign stochastic_out_b = r.out_b;

endmodule : stochastic_decorrelator
