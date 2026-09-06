`include "ma_assert.svh"
// Test-only integration wrapper: two binary_stochastic_converter encoders
// feed stochastic_adder, whose scaled-sum bitstream feeds
// stochastic_to_binary -- exercising a full binary-in -> add -> binary-out
// chain (encoder x2 -> adder -> decoder), mirroring
// test_b_mult_s_integration/top.sv but with the adder in place of the
// multiplier. Not a synthesizable product block, so it lives with the
// test rather than under rtl/.
//
//   binary_in_a -> [encoder A] --stochastic_a--\
//                                                +--> [adder] --stochastic_sum--> [decoder] -> binary_out
//   binary_in_b -> [encoder B] --stochastic_b--/
//
// Two decorrelation requirements apply here, both elaboration-checked
// below (neither is a rigorous independence proof -- see docs/adr/0015
// and docs/adr/0014 -- just a guard against the laziest accidental
// collision):
// 1. Encoders A and B need distinct INIT_SEED (docs/adr/0015) -- same
//    reasoning as the multiplier composition: identical seed + WIDTH
//    means fully correlated operand streams.
// 2. The adder's own select LFSR (docs/adr/0014) must also be
//    decorrelated from BOTH operand streams, not just from each other.
//    All three LFSRs (encoder A, encoder B, the adder's SELECT_RNG)
//    advance in lockstep on the same real-transfer cycles (the adder's
//    join couples them the same way stochastic_multiplier's join does),
//    so if SELECT_LFSR_WIDTH/SELECT_INIT_SEED happened to numerically
//    coincide with an encoder's WIDTH/INIT_SEED, the select bit would
//    just BE that encoder's own bitstream -- fully correlated with one
//    operand, silently breaking the adder's core independence
//    requirement. Using a different SELECT_LFSR_WIDTH than WIDTH
//    guarantees a structurally different taps polynomial (see
//    galois_lfsr.sv's TAPS_LUT), not just a different seed under the same
//    one.
module top #(
    parameter int WIDTH = 4,
    parameter bit [WIDTH-1:0] INIT_SEED_A = WIDTH'(1),
    parameter bit [WIDTH-1:0] INIT_SEED_B = WIDTH'(2),
    parameter int SELECT_LFSR_WIDTH = 5,
    parameter bit [SELECT_LFSR_WIDTH-1:0] SELECT_INIT_SEED = SELECT_LFSR_WIDTH'(1)
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] binary_in_a,
    input  logic             valid_binary_in_a,
    input  logic [WIDTH-1:0] binary_in_b,
    input  logic             valid_binary_in_b,
    input  logic             ready_binary_out,
    output logic             ready_binary_in_a,
    output logic             ready_binary_in_b,
    output logic             valid_binary_out,
    output logic [WIDTH-1:0] binary_out
);
  `MA_ASSERT_ELABOR(DistinctEncoderSeeds, INIT_SEED_A != INIT_SEED_B)
  `MA_ASSERT_ELABOR(SelectLFSRDecorrelatedFromOperands, SELECT_LFSR_WIDTH != WIDTH)

  logic stochastic_a, valid_stochastic_a, ready_stochastic_a, last_cycle_a;
  /* verilator lint_off UNUSEDSIGNAL */
  // last_cycle_b is intentionally left unconsumed inside this module (only
  // last_cycle_a feeds the decoder's boundary_in, per the simultaneity
  // guarantee below) -- it's exposed purely for the testbench to check
  // that guarantee directly (dut.last_cycle_b), not dead code.
  logic stochastic_b, valid_stochastic_b, ready_stochastic_b, last_cycle_b;
  /* verilator lint_on UNUSEDSIGNAL */
  logic stochastic_sum, valid_stochastic_sum, ready_stochastic_sum;

  binary_stochastic_converter #(
      .WIDTH(WIDTH),
      .INIT_SEED(INIT_SEED_A)
  ) u_encoder_a (
      .clk(clk),
      .rst_n(rst_n),
      .binary_in(binary_in_a),
      .valid_binary_in(valid_binary_in_a),
      .ready_stochastic_out(ready_stochastic_a),
      .ready_binary_in(ready_binary_in_a),
      .valid_stochastic_out(valid_stochastic_a),
      .stochastic_out(stochastic_a),
      .last_cycle(last_cycle_a)
  );

  binary_stochastic_converter #(
      .WIDTH(WIDTH),
      .INIT_SEED(INIT_SEED_B)
  ) u_encoder_b (
      .clk(clk),
      .rst_n(rst_n),
      .binary_in(binary_in_b),
      .valid_binary_in(valid_binary_in_b),
      .ready_stochastic_out(ready_stochastic_b),
      .ready_binary_in(ready_binary_in_b),
      .valid_stochastic_out(valid_stochastic_b),
      .stochastic_out(stochastic_b),
      .last_cycle(last_cycle_b)
  );

  stochastic_adder #(
      .SELECT_LFSR_WIDTH(SELECT_LFSR_WIDTH),
      .SELECT_INIT_SEED(SELECT_INIT_SEED)
  ) u_adder (
      .clk(clk),
      .rst_n(rst_n),
      .stochastic_in_a(stochastic_a),
      .valid_stochastic_in_a(valid_stochastic_a),
      .ready_stochastic_in_a(ready_stochastic_a),
      .stochastic_in_b(stochastic_b),
      .valid_stochastic_in_b(valid_stochastic_b),
      .ready_stochastic_in_b(ready_stochastic_b),
      .ready_stochastic_out(ready_stochastic_sum),
      .valid_stochastic_out(valid_stochastic_sum),
      .stochastic_out(stochastic_sum)
  );

  // Same simultaneity guarantee as test_b_mult_s_integration/top.sv: the
  // adder's join mutually gates each encoder's own `en` on the OTHER
  // encoder's valid, so with equal WIDTH on both encoders their
  // out_counters advance in lockstep and last_cycle_a/last_cycle_b are
  // guaranteed simultaneous. Only last_cycle_a feeds boundary_in; the
  // testbench checks the guarantee directly rather than trusting it
  // silently. See docs/adr/0017.

  stochastic_to_binary #(
      .WIDTH(WIDTH)
  ) u_decoder (
      .clk(clk),
      .rst_n(rst_n),
      .stochastic_in(stochastic_sum),
      .valid_stochastic_in(valid_stochastic_sum),
      .boundary_in(last_cycle_a),
      .ready_binary_out(ready_binary_out),
      .ready_stochastic_in(ready_stochastic_sum),
      .valid_binary_out(valid_binary_out),
      .binary_out(binary_out)
  );
endmodule : top
