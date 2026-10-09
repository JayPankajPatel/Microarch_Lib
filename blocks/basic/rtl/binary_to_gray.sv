`include "ma_assert.svh"
module binary_to_gray #(
    parameter int DATA_WIDTH = 0
) (
    input  logic [DATA_WIDTH-1:0] binary,
    output logic [DATA_WIDTH-1:0] gray
);

  `MA_ASSERT_ELABOR(ValidDataWidth, DATA_WIDTH > 0)

  always_comb begin
    gray = (binary ^ (binary >> 1));
  end


endmodule : binary_to_gray
