`include "ma_assert.svh"
module binary_to_stocastic #(
  parameter int WIDTH = 4
  )(
  input logic clk,
  input logic [WIDTH-1:0] binary_in, 
  input logic rst_n,
  output logic stochastic_out
);
`MA_ASSERT_INIT(ValidBinarytoStocasticCheck, WIDTH inside {[2:64]}) // 2 to 64 inclusive
 logic [WIDTH-1:0] random_number; 

 galois_lfsr #(
  .WIDTH(WIDTH)
  )
  RNG
(
  .clk(clk),
  .rst_n(rst_n),
  .out(random_number)
);

assign stochastic_out =((random_number < binary_in) ? 1'b1 : 1'b0);

endmodule : binary_to_stocastic
