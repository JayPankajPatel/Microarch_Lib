// FPGA area/power comparison target: the full stochastic-computing 4-bit
// multiply chain (2x binary_stochastic_converter -> stochastic_multiplier
// -> stochastic_to_binary), matching test_b_mult_s_integration/top.sv's
// composition, wrapped for standalone Vivado synthesis on the Zybo Z7.
//
// Operands are driven by free-running counters (not tied to constants)
// so Vivado's synthesis can't constant-fold the whole design away --
// utilization/power numbers need to reflect the real logic, not an
// optimized-out no-op. product_out is the decoder's own accumulated
// popcount; only its low nibble is wired to board LEDs (a full physical
// demo -- switch-selected operands, multi-digit readout -- is a separate,
// optional follow-up; this wrapper's job is to give Vivado a legitimate,
// unoptimizable synthesis target for utilization/power reporting).
//
// Known caveat (see Microarch_Lib GitHub issue #3 and
// ~/wiki/fpga_stochastic_blocks/decision_logs/stochastic-v0-evidence-and-v1-candidate-2026-09-06.md):
// at WIDTH=4 (period 15), no fixed-seed-pair choice on this LFSR
// polynomial gives an accurate product estimate -- the period is too
// short relative to any useful N. This wrapper's seed choice does not
// attempt to work around that; it exists for area/power comparison, not a
// numerically-trustworthy multiply demo. Fixing that needs either a wider
// LFSR or an asymmetric operand-width scheme, out of scope here.
module sc_multiply_top #(
    parameter int WIDTH = 4
) (
    input  logic       clk,
    output logic [3:0] led
);
  // No external reset pin for this synthesis/utilization-only comparison
  // target -- tied high internally (never reset) rather than exposing an
  // unconstrained top-level port.
  logic rst_n;
  assign rst_n = 1'b1;

  logic [WIDTH-1:0] binary_in_a, binary_in_b;
  logic [WIDTH-1:0] product_out;
  logic             valid_out;

  // Free-running operand generators -- deliberately simple counters, not
  // meant to be a realistic workload, just enough toggling activity that
  // synthesis can't treat the multiply logic as dead/constant.
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) binary_in_a <= '0;
    else binary_in_a <= binary_in_a + 1'b1;
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) binary_in_b <= WIDTH'(3);
    else binary_in_b <= binary_in_b + WIDTH'(3);
  end

  logic stochastic_a, valid_stochastic_a, ready_stochastic_a, last_cycle_a;
  /* verilator lint_off UNUSEDSIGNAL */
  // last_cycle_b intentionally unconsumed -- same simultaneity guarantee
  // as test_b_mult_s_integration/top.sv (docs/adr/0017), only last_cycle_a
  // drives the decoder's boundary_in.
  logic stochastic_b, valid_stochastic_b, ready_stochastic_b, last_cycle_b;
  /* verilator lint_on UNUSEDSIGNAL */
  logic stochastic_product, valid_stochastic_product, ready_stochastic_product;

  binary_stochastic_converter #(
      .WIDTH(WIDTH),
      .INIT_SEED(WIDTH'(1))
  ) u_encoder_a (
      .clk(clk),
      .rst_n(rst_n),
      .binary_in(binary_in_a),
      .valid_binary_in(1'b1),
      .ready_stochastic_out(ready_stochastic_a),
      /* verilator lint_off PINCONNECTEMPTY */
      .ready_binary_in(),
      /* verilator lint_on PINCONNECTEMPTY */
      .valid_stochastic_out(valid_stochastic_a),
      .stochastic_out(stochastic_a),
      .last_cycle(last_cycle_a)
  );

  binary_stochastic_converter #(
      .WIDTH(WIDTH),
      .INIT_SEED(WIDTH'(5))
  ) u_encoder_b (
      .clk(clk),
      .rst_n(rst_n),
      .binary_in(binary_in_b),
      .valid_binary_in(1'b1),
      .ready_stochastic_out(ready_stochastic_b),
      /* verilator lint_off PINCONNECTEMPTY */
      .ready_binary_in(),
      /* verilator lint_on PINCONNECTEMPTY */
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

  stochastic_to_binary #(
      .WIDTH(WIDTH)
  ) u_decoder (
      .clk(clk),
      .rst_n(rst_n),
      .stochastic_in(stochastic_product),
      .valid_stochastic_in(valid_stochastic_product),
      .boundary_in(last_cycle_a),
      .ready_binary_out(1'b1),
      .ready_stochastic_in(ready_stochastic_product),
      .valid_binary_out(valid_out),
      .binary_out(product_out)
  );

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) led <= '0;
    else if (valid_out) led <= product_out[3:0];
  end
endmodule : sc_multiply_top
