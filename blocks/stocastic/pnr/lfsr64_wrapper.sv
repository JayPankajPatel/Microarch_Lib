// Fixed-WIDTH=64 synthesis harness for the sparse-vs-dense TAPS_LUT PPA
// comparison (github.com/JayPankajPatel/Microarch_Lib/issues/1). Not
// library RTL -- lives outside rtl/ so the pre-commit lint hook (which
// globs blocks/*/rtl/*.sv) doesn't pick it up.
module lfsr64_wrapper (
  input  logic        clk,
  input  logic        rst_n,
  output logic [63:0] out
);

galois_lfsr #(
  .WIDTH(64),
  .INIT_SEED(64'h1)
) u_lfsr (
  .clk    (clk),
  .rst_n  (rst_n),
  .out    (out)
);

endmodule : lfsr64_wrapper
