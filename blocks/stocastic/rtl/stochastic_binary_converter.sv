
`include "ma_assert.svh"
module stochastic_to_binary #(
    parameter int WIDTH = 4
) (
    input logic clk,
    input logic rst_n,
    input logic stochastic_in,
    input logic valid_stochastic_in,
    input logic ready_binary_out,
    output logic ready_stochastic_in,
    output logic valid_binary_out,
    output logic [WIDTH-1:0] binary_out
);
  `MA_ASSERT_ELABOR(ValidStocastictoBinaryCheck, WIDTH inside {[2 : 64]})  // 2 to 64 inclusive

  localparam MAX_CYCLES = (1 << WIDTH) - 1'b1;
  localparam int n = WIDTH;

  typedef struct packed {
    logic [n-1:0] cycle_count;
    logic [n-1:0] ones_count;
    logic [n-1:0] binary_out_d;
    logic valid_binary_out;
  } bin_to_sto_t;
  bin_to_sto_t r, rin;

  always_comb begin
    rin = r;
    if (r.cycle_count == MAX_CYCLES && !r.valid_binary_out) begin
      // window just finished -- latch and announce
      rin.binary_out_d = r.ones_count;
      rin.valid_binary_out = 1'b1;
      if (ready_binary_out) begin
        // consumer already ready -- reopen in the same transition, zero bubble
        rin.cycle_count = '0;
        rin.ones_count  = '0;
      end
    end else if (r.cycle_count == MAX_CYCLES && ready_binary_out) begin
      // slow path: was already showing valid from a prior cycle, consumer
      // just became ready now -- consume and reopen
      rin.cycle_count = '0;
      rin.ones_count = '0;
      rin.valid_binary_out = 1'b0;
    end else if (r.valid_binary_out && r.cycle_count != MAX_CYCLES) begin
      // fast-path aftermath: already reopened (cycle_count != MAX_CYCLES,
      // unlike the still-holding slow-path case above) but still showing
      // last cycle's valid pulse -- clear it now
      rin.valid_binary_out = 1'b0;
    end else if (valid_stochastic_in && r.cycle_count != MAX_CYCLES) begin
      rin.cycle_count = r.cycle_count + 1'b1;
      rin.ones_count = r.ones_count + (stochastic_in == 1'b1);
    end
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      r.cycle_count <= '0;
      r.ones_count <= '0;
      r.binary_out_d <= '0;
      r.valid_binary_out <= '0;
    end else begin
      r <= rin;
    end
  end

  assign binary_out = r.binary_out_d;
  assign valid_binary_out = rst_n && r.valid_binary_out;
  assign ready_stochastic_in = rst_n && (r.cycle_count != MAX_CYCLES);



endmodule : stochastic_to_binary
