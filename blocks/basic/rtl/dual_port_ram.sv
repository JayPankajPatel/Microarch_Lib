`include "ma_assert.svh"
// Dual port ram intended to be inferred RAM block (BRAM for Xilinx terms)
// 1 cycle delay when reading, buffer output
module dual_port_ram #(
    parameter int unsigned DATA_WIDTH = 0,
    parameter int unsigned DEPTH = 0
) (
    input logic wclk,
    input logic rclk,
    input logic wen,
    input logic ren,
    input logic [$clog2(DEPTH)-1:0] raddr,
    input logic [$clog2(DEPTH)-1:0] waddr,
    input logic [DATA_WIDTH-1:0] wdata,
    output logic [DATA_WIDTH-1:0] rdata
);
  `MA_ASSERT_ELABOR(ValidDataWidth, DATA_WIDTH >= 1)
  `MA_ASSERT_ELABOR(ValidAddr, DEPTH >= 2)
  `MA_ASSERT_ELABOR(PowerOf2DataWidth, (DATA_WIDTH > 0) && (DATA_WIDTH & DATA_WIDTH - 1) == 0)
  `MA_ASSERT_ELABOR(PowerOf2Addr, (DEPTH > 0) && (DEPTH & DEPTH - 1) == 0)
  logic [DATA_WIDTH-1:0] ram[DEPTH];

  always_ff @(posedge wclk) begin
    if (wen) begin
      ram[waddr] <= wdata;
    end
  end
  always_ff @(posedge rclk) begin
    if (ren) begin
      rdata <= ram[raddr];
    end
  end



endmodule : dual_port_ram
