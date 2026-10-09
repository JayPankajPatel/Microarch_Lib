`include "ma_assert.svh"
// pg. 8 SNUG 2002 FIFO1 Figure 4
module dual_n_bit_gray_counter #(
    parameter int DATA_WIDTH = 0
) (
    input logic clk,
    input logic rst_n,
    input logic en,
    output logic [DATA_WIDTH-1:0] addr,
    output logic [DATA_WIDTH:0] ptr
);
  `MA_ASSERT_ELABOR(ValidDataWidth, DATA_WIDTH > 1)
  typedef struct packed {
    logic [DATA_WIDTH:0] bin;
    logic [DATA_WIDTH:0] gray;
  } data_rep_t;
  // r is the current and rin is the next value
  data_rep_t r, rin;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      r <= '0;
    end else begin
      r <= rin;
    end
  end

  always_comb begin
    rin.bin = r.bin + en;
  end

  binary_to_gray #(
      .DATA_WIDTH(DATA_WIDTH + 1)
  ) b2g_dual_n_bit_gray_counter (
      .binary(rin.bin),
      .gray  (rin.gray)
  );

  always_comb begin
    addr = r.bin[DATA_WIDTH-1:0];
    ptr  = r.gray;
  end
endmodule : dual_n_bit_gray_counter
