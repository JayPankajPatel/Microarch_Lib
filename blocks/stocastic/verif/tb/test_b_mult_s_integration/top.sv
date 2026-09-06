`include "ma_assert.svh"
// Test-only integration wrapper: two binary_stochastic_converter encoders
// feed stochastic_multiplier, whose product bitstream feeds
// stochastic_to_binary -- exercising a full binary-in -> multiply ->
// binary-out chain (encoder x2 -> multiplier -> decoder), not just a
// single module or a pairwise loopback. Not a synthesizable product block,
// so it lives with the test rather than under rtl/.
//
//   binary_in_a -> [encoder A] --stochastic_a--\
//                                                +--> [multiplier] --stochastic_product--> [decoder] -> binary_out
//   binary_in_b -> [encoder B] --stochastic_b--/
//
// Encoders A and B MUST use distinct INIT_SEED values (see docs/adr/0015):
// with the same WIDTH and the same default seed, their internal
// galois_lfsrs advance in lockstep and produce fully-correlated streams --
// the multiplier's AND would then compute min(a,b), not a*b, while still
// looking protocol-correct (valid handshakes, plausible-looking bits).
module top #(
    parameter int WIDTH = 4,
    parameter bit [WIDTH-1:0] INIT_SEED_A = WIDTH'(1),
    parameter bit [WIDTH-1:0] INIT_SEED_B = WIDTH'(2)
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

  logic stochastic_a, valid_stochastic_a, ready_stochastic_a, last_cycle_a;
  /* verilator lint_off UNUSEDSIGNAL */
  // last_cycle_b is intentionally left unconsumed inside this module (only
  // last_cycle_a feeds the decoder's boundary_in, per the simultaneity
  // guarantee below) -- it's exposed purely for the testbench to check
  // that guarantee directly (dut.last_cycle_b), not dead code.
  logic stochastic_b, valid_stochastic_b, ready_stochastic_b, last_cycle_b;
  /* verilator lint_on UNUSEDSIGNAL */
  logic stochastic_product, valid_stochastic_product, ready_stochastic_product;

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

  stochastic_multiplier u_multiplier (
      .clk(clk),
      .rst_n(rst_n),
      .stochastic_in_a(stochastic_a),
      .valid_stochastic_in_a(valid_stochastic_a),
      .ready_stochastic_in_a(ready_stochastic_a),
      .stochastic_in_b(stochastic_b),
      .valid_stochastic_in_b(valid_stochastic_b),
      .ready_stochastic_in_b(ready_stochastic_b),
      .ready_stochastic_out(ready_stochastic_product),
      .valid_stochastic_out(valid_stochastic_product),
      .stochastic_out(stochastic_product)
  );

  // The multiplier's join mutually gates each encoder's own `en` on the
  // OTHER encoder's valid (see stochastic_multiplier.sv), so once both are
  // busy their out_counters advance in lockstep, real-transfer for
  // real-transfer -- with equal WIDTH (enforced by this module sharing one
  // WIDTH parameter for both encoders), last_cycle_a and last_cycle_b are
  // therefore guaranteed simultaneous, not just coincidentally similar.
  // Only one is wired to the decoder's boundary_in; the testbench checks
  // this simultaneity claim directly rather than trusting it silently. See
  // docs/adr/0017.

  stochastic_to_binary #(
      .WIDTH(WIDTH)
  ) u_decoder (
      .clk(clk),
      .rst_n(rst_n),
      .stochastic_in(stochastic_product),
      .valid_stochastic_in(valid_stochastic_product),
      .boundary_in(last_cycle_a),
      .ready_binary_out(ready_binary_out),
      .ready_stochastic_in(ready_stochastic_product),
      .valid_binary_out(valid_binary_out),
      .binary_out(binary_out)
  );
endmodule : top
