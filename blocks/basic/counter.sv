`include "ma_assert.svh"
module counter #(
  parameter int UPTO = 100
  )
(
  input logic clk,
  input logic rst_n,
  output logic [$clog(UPTO)-1:0] out
);
`MA_ASSERT_INIT(ValidCounterSize, UPTO > 0) // 2 to 64 inclusive

always_ff @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin 
    out <= '0; 
  end
  else begin
    out <= out + 1'b1; 
  end
end
endmodule : counter
