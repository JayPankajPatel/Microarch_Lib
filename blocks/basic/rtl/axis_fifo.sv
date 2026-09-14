// This module is a toy module to test some verification bootstraping
module axis_fifo #(
    parameter int unsigned WIDTH = 8
) (
    input logic clk,
    input logic rst,
    output logic [WIDTH-1:0] m_axis_tdata,
    output logic m_axis_tvalid,
    input logic m_axis_tready,
    input logic [WIDTH-1:0] s_axis_tdata,
    input logic s_axis_tvalid,
    output logic s_axis_tready
);

  typedef struct packed {
    logic full;
    logic [WIDTH-1:0] data;
  } fifo_t;
  fifo_t r, rin;
  always_ff @(posedge clk) begin
    if (rst) begin
      r <= '{full: '0, data: '0};
    end else begin
      r <= rin;
    end
  end

  always_comb begin
    rin = r;
    if (m_axis_tvalid && m_axis_tready) begin
      rin.full = 1'b0;
    end
    if (s_axis_tvalid && s_axis_tready) begin
      rin.data = s_axis_tdata;
      rin.full = 1'b1;
    end
  end

  assign m_axis_tdata  = r.data;
  assign m_axis_tvalid = r.full;
  assign s_axis_tready = !r.full || m_axis_tready;

endmodule : axis_fifo
