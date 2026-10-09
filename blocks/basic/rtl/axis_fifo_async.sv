`include "ma_assert.svh"
module wptr_full #(
    parameter int unsigned DEPTH = 0
) (
    input logic wclk,
    input logic wrst_n,
    input logic winc,
    output logic wptr,
    output logic [$clog2(DEPTH)-1:0] waddr
);

  `MA_ASSERT_ELABOR(ValidAddr, DEPTH >= 2)
  `MA_ASSERT_ELABOR(PowerOf2Addr, (DEPTH > 0) && (DEPTH & DEPTH - 1) == 0)

  logic wptr_d;
  logic [$clog2(DEPTH)-1:0] waddr_d;

  always_ff @(posedge wclk) begin
    if (!wrst_n) begin
      wptr  <= '0;
      waddr <= '0;
    end else begin
      wptr  <= wptr_d;
      waddr <= waddr_d;
    end
  end

endmodule : wptr_full

module axis_fifo_async ();

endmodule : axis_fifo_async
