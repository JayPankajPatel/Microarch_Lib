`include "ma_assert.svh"
module binary_to_gray #(
    parameter int WIDTH = 0
) (
    input  logic [WIDTH-1:0] binary,
    output logic [WIDTH-1:0] gray
);

  `MA_ASSERT_ELABOR(ValidWidth, WIDTH > 0)

  always_comb begin
    gray = (binary ^ (binary >> 1));
  end


endmodule : binary_to_gray
