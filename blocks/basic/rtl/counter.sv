`include "ma_assert.svh"
module counter #(
    /* verilator lint_off WIDTHEXPAND */
    // longint unsigned (64 bits), not int (32-bit signed): a 32-bit
    // parameter can't hold UPTO=2^64-1 (the largest value
    // binary_stochastic_converter's WIDTH<=64 needs), and worse, silently
    // reinterprets any value >= 2^31 as negative -- independent-audit
    // finding, confirmed via Yosys elaboration showing UPTO going negative
    // at the caller's WIDTH=32 and out_counter's port width simply not
    // matching the caller's wire at WIDTH=33/64.
    parameter longint unsigned UPTO = 100
) (
    input logic clk,
    input logic en,
    input logic clr,
    input logic rst_n,
    output logic [$clog2(UPTO)-1:0] out
);
  `MA_ASSERT_ELABOR(ValidCounterSize, UPTO > 0)

  // clr takes priority over en so a caller can synchronously restart a
  // count window on the same cycle it would otherwise have incremented
  // (e.g. reusing this counter across back-to-back windows without
  // depending on its natural bit-width wraparound landing back on 0 --
  // that only happens to line up when UPTO is itself a power of 2).
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out <= '0;
    end else if (clr) begin
      out <= '0;
    end else if (en) begin
      out <= out + 1'b1;
    end
  end
endmodule : counter
