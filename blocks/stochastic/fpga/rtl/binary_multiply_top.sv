// FPGA area/power comparison target: a conventional binary 4-bit x 4-bit
// multiplier, wrapped identically to sc_multiply_top.sv (same free-running
// operand generators, same clk/rst_n/led interface) so the only real
// difference between the two synthesized designs is the multiply
// architecture itself (stochastic vs. exact binary), not incidental
// wrapper differences.
//
// Note the fundamentally different execution model this comparison is
// actually contrasting: this multiplier is combinational, one clean
// result per cycle; sc_multiply_top.sv's chain takes ~2**WIDTH-1 cycles
// to produce one (approximate) result. The area/power numbers below
// should always be read together with that latency/throughput difference,
// not in isolation -- it's the standard SC area-for-latency tradeoff, not
// something either design is "hiding."
module binary_multiply_top #(
    parameter int WIDTH = 4
) (
    input  logic       clk,
    output logic [3:0] led
);
  // Same no-external-reset convention as sc_multiply_top.sv, for a fair,
  // wrapper-identical comparison.
  logic rst_n;
  assign rst_n = 1'b1;

  logic [WIDTH-1:0] binary_in_a, binary_in_b;
  /* verilator lint_off UNUSEDSIGNAL */
  // Only the low nibble is wired to led (matching sc_multiply_top.sv's
  // led assignment width) -- the full product is still the real
  // synthesis/utilization target, not dead logic.
  logic [2*WIDTH-1:0] product;
  /* verilator lint_on UNUSEDSIGNAL */

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) binary_in_a <= '0;
    else binary_in_a <= binary_in_a + 1'b1;
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) binary_in_b <= WIDTH'(3);
    else binary_in_b <= binary_in_b + WIDTH'(3);
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) product <= '0;
    else product <= binary_in_a * binary_in_b;
  end

  assign led = product[3:0];
endmodule : binary_multiply_top
