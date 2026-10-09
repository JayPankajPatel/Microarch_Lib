// Formal hookup for axis_fifo: environment assumption plus AXI-Stream
// checkers on both ports. axis_fifo.sv itself contains no verification code.
// See docs/adr/0025.

`include "ma_sva.svh"

module axis_fifo_formal_env (
    input logic clk,
    input logic rst
);
  `MA_ASSUME_RESET_AT_START(clk, rst)  // active-high reset
endmodule : axis_fifo_formal_env

bind axis_fifo axis_fifo_formal_env u_formal_env (.clk(clk), .rst(rst));

bind axis_fifo ma_axis_checker #(
    .payload_t(logic [WIDTH-1:0]),
    .DUT_IS_TX(1'b0)
) u_s_axis_chk (
    .clk(clk), .rst_n(!rst),
    .tvalid(s_axis_tvalid), .tready(s_axis_tready), .payload(s_axis_tdata)
);

bind axis_fifo ma_axis_checker #(
    .payload_t(logic [WIDTH-1:0]),
    .DUT_IS_TX(1'b1)
) u_m_axis_chk (
    .clk(clk), .rst_n(!rst),
    .tvalid(m_axis_tvalid), .tready(m_axis_tready), .payload(m_axis_tdata)
);
