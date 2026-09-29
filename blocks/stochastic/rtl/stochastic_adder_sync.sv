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
    // See stochastic_adder.sv's identical comment: 5, not 4, because 4 is
    // both galois_lfsr's own module default and this library's typical
    // operand-encoder default, so a standalone instantiation overriding
    // neither parameter would otherwise silently collide with a same-
    // default encoder's select-independence requirement.
    parameter int SELECT_LFSR_WIDTH = 5,
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
  // failure. A caller composing this with encoders that already use
  // WIDTH=5/INIT_SEED=1 for something else must still override at least
  // one of SELECT_LFSR_WIDTH/SELECT_INIT_SEED, or independence isn't real,
  // just assumed.
  //
  // select is only APPROXIMATELY 50/50, never exactly -- see
  // stochastic_adder.sv's identical comment for the full explanation
  // (a maximal-length LFSR's odd period makes an exact 50/50 single-bit
  // split mathematically impossible; at the default SELECT_LFSR_WIDTH=5
  // select is 1 with probability 16/31, not 1/2).
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
