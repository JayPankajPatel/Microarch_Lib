
`include "ma_assert.svh"
module stochastic_to_binary #(
    parameter int WIDTH = 4
) (
    input logic clk,
    input logic stochastic_in,
    input logic rst_n,
    output logic [WIDTH-1:0] binary_out
);
  `MA_ASSERT_INIT(ValidStocastictoBinaryCheck, WIDTH inside {[2 : 64]})  // 2 to 64 inclusive

  logic [WIDTH-1:0] cycle_count;
  logic [WIDTH-1:0] ones_count;

  localparam int MAX_CYCLES = (1 << WIDTH) - 1'b1;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      binary_out  <= '0;
      cycle_count <= '0;
      ones_count  <= '0;
    end else begin
      cycle_count <= cycle_count + 1'b1;
      if (cycle_count == MAX_CYCLES) begin
        binary_out <= ones_count;
        ones_count <= stochastic_in;
      end else begin
        ones_count <= stochastic_in + ones_count;
      end
    end
  end

endmodule : stochastic_to_binary
