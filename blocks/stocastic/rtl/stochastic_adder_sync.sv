`include "ma_assert.svh"
// Synchronous-reset variant of stochastic_adder.sv, for targets whose
// flip-flop primitive has no async reset input (e.g. FABulous fabric
// BELs -- see docs/adr/0020 and ~/wiki/fpga_stochastic_blocks/
// reusable_lessons/fabric-ff-primitive-sync-reset-only.md). This module
// has no always_ff of its own (pure combinational join, see
// stochastic_multiplier.sv for the same pattern) -- the only change is
// instantiating galois_lfsr_sync for the select RNG instead of
// galois_lfsr, so the whole reset domain stays consistently synchronous.
// Kept as a parallel file: stochastic_adder.sv stays the verified
// async-reset default.
module stochastic_adder_sync #(
    parameter int SELECT_LFSR_WIDTH = 4,
    parameter bit [SELECT_LFSR_WIDTH-1:0] SELECT_INIT_SEED = SELECT_LFSR_WIDTH'(1)
) (
    input logic clk,
    input logic rst_n,
    input logic stochastic_in_a,
    input logic valid_stochastic_in_a,
    output logic ready_stochastic_in_a,
    input logic stochastic_in_b,
    input logic valid_stochastic_in_b,
    output logic ready_stochastic_in_b,
    input logic ready_stochastic_out,
    output logic valid_stochastic_out,
    output logic stochastic_out
);
  `MA_ASSERT_ELABOR(ValidSelectLFSRWidthCheck, SELECT_LFSR_WIDTH inside {[2 : 64]})  // 2 to 64 inclusive

  // Textbook stochastic addition: MUX(select, A, B), scaling the true sum
  // to (A+B)/2 since a stochastic bitstream can't represent p>1. select
  // must be an independent-of-A-and-B random bit, freshly drawn per output
  // bit -- reusing A's or B's own LFSR (or a correlated one: same taps,
  // same phase) would make this MUX not actually random relative to its
  // inputs, silently producing a biased/wrong result instead of a loud
  // failure. SELECT_LFSR_WIDTH/SELECT_INIT_SEED default away from
  // galois_lfsr's own default (WIDTH picked by the operand encoder,
  // INIT_SEED=1) but a caller composing this with encoders that already
  // use WIDTH=4/INIT_SEED=1 must override at least one of these two
  // parameters, or independence isn't real, just assumed.
  logic [SELECT_LFSR_WIDTH-1:0] select_lfsr_out;
  logic select_bit;
  logic select_en;

  galois_lfsr_sync #(
      .WIDTH(SELECT_LFSR_WIDTH),
      .INIT_SEED(SELECT_INIT_SEED)
  ) SELECT_RNG (
      .clk(clk),
      .en(select_en),
      .rst_n(rst_n),
      .out(select_lfsr_out)
  );

  // Pure combinational join (see stochastic_multiplier.sv for the same
  // two-producer-into-one-consumer pattern) plus a MUX -- no registered
  // state of its own beyond the select LFSR, since there's nothing to
  // accumulate across cycles.
  assign valid_stochastic_out = valid_stochastic_in_a && valid_stochastic_in_b;
  assign ready_stochastic_in_a = ready_stochastic_out && valid_stochastic_in_b;
  assign ready_stochastic_in_b = ready_stochastic_out && valid_stochastic_in_a;

  // Advance the select LFSR only on cycles a bit is actually produced
  // (valid && ready) -- one fresh random draw per real output bit, not per
  // attempted cycle, matching how the encoder/decoder pace their own LFSR
  // advances against real transfers rather than wall-clock cycles.
  assign select_en = valid_stochastic_out && ready_stochastic_out;
  assign select_bit = select_lfsr_out[SELECT_LFSR_WIDTH-1];
  assign stochastic_out = select_bit ? stochastic_in_b : stochastic_in_a;

endmodule : stochastic_adder_sync
