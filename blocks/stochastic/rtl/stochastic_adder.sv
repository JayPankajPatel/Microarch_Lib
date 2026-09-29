`include "ma_assert.svh"
module stochastic_adder #(
    // 5, not 4: galois_lfsr's own module default and this whole library's
    // typical operand-encoder default are both WIDTH=4/INIT_SEED=1. A
    // standalone instantiation of this module that overrides neither
    // parameter would otherwise silently collide with a same-default
    // encoder's own select-independence requirement (the exact failure
    // mode the comment below warns about) unless the caller happens to
    // notice and override one of the two -- independent-audit finding.
    // Callers composing with encoders that already use WIDTH=5 for
    // something else still need to override explicitly; there's no
    // default that's safe against every possible caller configuration,
    // only one that isn't ALSO the single most common default.
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
  // select is only APPROXIMATELY 50/50, never exactly: a maximal-length
  // W-bit LFSR is a balanced m-sequence, meaning ANY single output bit
  // (including the MSB used here) is 1 for exactly 2^(W-1) of the
  // sequence's 2^W-1 states and 0 for the remaining 2^(W-1)-1 -- an
  // inherent, unavoidable property of maximal-length LFSRs (the period is
  // always odd, so an exact even split is mathematically impossible from
  // a single bit), not a bug fixable by a different width/seed/tap choice.
  // At the default SELECT_LFSR_WIDTH=5, select is 1 with probability
  // 16/31 (~0.5161), giving stochastic_out an A/B weighting of ~15/31
  // versus ~16/31 instead of exactly 1/2 versus 1/2 -- independent-audit
  // finding (originally measured at the old WIDTH=4 default: 8/15
  // ~0.5333). This is why scaled_sum_statistical_property's tolerance is
  // 0.05, not an arbitrarily-chosen number: it must clear this structural
  // bias (~0.016 at WIDTH=5) plus real sampling noise, not just sampling
  // noise alone. If a caller's application requires exact (not
  // approximate) (A+B)/2 over a defined window, this single-bit-from-an-
  // LFSR select mechanism cannot provide that by itself regardless of
  // width/seed.
  logic [SELECT_LFSR_WIDTH-1:0] select_lfsr_out;
  logic select_bit;
  logic select_en;

  galois_lfsr #(
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

endmodule : stochastic_adder
