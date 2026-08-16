`include "ma_assert.svh"
module binary_stochastic_converter #(
    parameter int WIDTH = 2
) (
    input logic clk,
    input logic [WIDTH-1:0] binary_in,
    input logic rst_n,
    input logic valid_binary_in,
    input logic ready_stochastic_out,
    output logic ready_binary_in,
    output logic valid_stochastic_out,
    output logic stochastic_out,
    output logic last_cycle
);
  `MA_ASSERT_INIT(ValidBinarytoStocasticCheck, WIDTH inside {[2 : 64]})  // 2 to 64 inclusive
  localparam int n = WIDTH;
  // takes 2^N cycles to convert a binary number to a stochastic bit stream
  localparam [$clog2((1 << n))-1:0] target_cycle_count = (1 << ((n))) - 1;
  logic [n-1:0] random_number;
  /* verilator lint_off ASCRANGE */
  logic [$clog2((1 << n))-1:0] out_counter;
  logic en; 

  typedef struct packed {
    logic [n-1:0] binary_in_d;
    logic ready_binary_in;
    logic valid_stochastic_out;
    logic busy;
  } state_t;

  state_t r, rin;

  counter #(
      .UPTO(target_cycle_count)
  ) counter (
      .clk(clk),
      .en(en),
      .rst_n(rst_n),
      .out(out_counter)
  );
  galois_lfsr #(
      .WIDTH(WIDTH)
  ) RNG (
      .clk(clk),
      .en(en),
      .rst_n(rst_n),
      .out(random_number)
  );

  always_comb begin
    rin = r;  // default: hold every field unless overridden below

    if (!r.busy) begin
      if (valid_binary_in && ready_stochastic_out) begin
        rin.binary_in_d = binary_in;
        rin.busy = 1'b1;
        rin.ready_binary_in = 1'b0;
        rin.valid_stochastic_out = 1'b1;
      end
    end else begin
      if ((out_counter == target_cycle_count) && ready_stochastic_out) begin
        // last bit is being consumed this cycle
        rin.ready_binary_in = 1'b1;
        rin.valid_stochastic_out = 1'b0;
        rin.busy = 1'b0;
      end else begin
        rin.ready_binary_in = 1'b0;
        rin.valid_stochastic_out = 1'b1;
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      r.binary_in_d <= '0;
      r.ready_binary_in <= '1;
      r.valid_stochastic_out <= '0;
      r.busy <= '0;
    end else begin
      r <= rin;
    end
  end

  assign last_cycle = r.busy && (out_counter == target_cycle_count);
  assign en = (r.busy && ready_stochastic_out);
  assign ready_binary_in = r.ready_binary_in;
  assign valid_stochastic_out = r.valid_stochastic_out;
  assign stochastic_out = ((random_number < r.binary_in_d) ? 1'b1 : 1'b0);
endmodule : binary_stochastic_converter
