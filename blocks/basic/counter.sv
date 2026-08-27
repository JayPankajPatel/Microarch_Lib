`include "ma_assert.svh"
module counter #(
    /* verilator lint_off WIDTHEXPAND */
    parameter int UPTO = 100
) (
    input logic clk,
    input logic en,
    input logic rst_n,
    output logic [$clog2(UPTO)-1:0] out
);
  `MA_ASSERT_ELABOR(ValidCounterSize, UPTO > 0)

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out <= '0;
    end else if (en) begin
      out <= out + 1'b1;
    end
  end
endmodule : counter
