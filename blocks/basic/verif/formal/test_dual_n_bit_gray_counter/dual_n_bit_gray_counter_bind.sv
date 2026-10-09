// Formal hookup for dual_n_bit_gray_counter: reset-at-start environment
// assumption plus a checker over the internal binary/gray pair.
// dual_n_bit_gray_counter.sv itself contains no verification code.
// See docs/adr/0025.

`include "ma_sva.svh"

module dual_n_bit_gray_counter_formal_env (
    input logic clk,
    input logic rst_n
);
  `MA_ASSUME_RESET_AT_START(clk, !rst_n)  // active-low reset
endmodule : dual_n_bit_gray_counter_formal_env

module dual_n_bit_gray_counter_checker #(
    parameter int W = 2  // counter width in bits (ADDR_WIDTH + 1)
) (
    input logic         clk,
    input logic         rst_n,
    input logic         en,
    input logic [W-1:0] bin,
    input logic [W-1:0] gray
);
  // 0 only at step 0, where $past has no history (rules without disable iff).
  // verilator lint_off PROCASSINIT
  logic f_past_valid = 1'b0;  // initializer = formal initial state
  // verilator lint_on PROCASSINIT
  always @(posedge clk) f_past_valid <= 1'b1;

  // Registered gray always encodes the registered binary value.
  `MA_ASSERT_SVA(gray_encodes_bin, gray == (bin ^ (bin >> 1)), clk, !rst_n)
  // Synchronous reset: the cycle after a reset edge both registers are 0.
  `MA_ASSERT_SVA(reset_clears,
                 !f_past_valid || $past(rst_n) || (bin == '0 && gray == '0), clk, 1'b0)
  // Binary advances by en each cycle, wrapping at W bits.
  `MA_ASSERT_SVA(bin_increments,
                 !$past(rst_n) || (bin == $past(bin) + W'($past(en))), clk, !rst_n)
  // Gray-code property: at most one bit changes per cycle, including the
  // wrap from all-ones binary back to zero.
  `MA_ASSERT_SVA(gray_single_bit_change,
                 !$past(rst_n) || (((gray ^ $past(gray)) & ((gray ^ $past(gray)) - 1'b1)) == '0), clk, !rst_n)

  `MA_COVER_SVA(counts_up, $past(rst_n && en) && gray != $past(gray), clk, !rst_n)
  `MA_COVER_SVA(wraps, $past(rst_n && en && bin == '1) && bin == '0, clk, !rst_n)
endmodule : dual_n_bit_gray_counter_checker

bind dual_n_bit_gray_counter dual_n_bit_gray_counter_formal_env u_formal_env (
    .clk(clk), .rst_n(rst_n)
);

bind dual_n_bit_gray_counter dual_n_bit_gray_counter_checker #(
    .W(ADDR_WIDTH + 1)
) u_chk (
    .clk(clk), .rst_n(rst_n), .en(en), .bin(r.bin), .gray(r.gray)
);
