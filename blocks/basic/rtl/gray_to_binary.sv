`include "ma_assert.svh"
module gray_to_binary #(
    parameter int DATA_WIDTH = 0
) (
    input  logic [DATA_WIDTH-1:0] gray,
    output logic [DATA_WIDTH-1:0] binary
);

  `MA_ASSERT_ELABOR(ValidDataWidth, DATA_WIDTH > 0)

  always_comb begin
    binary[DATA_WIDTH-1] = gray[DATA_WIDTH-1];
    for (int i = DATA_WIDTH - 2; i >= 0; i = i - 1) begin
      binary[i] = binary[i+1] ^ gray[i];
    end
  end

endmodule : gray_to_binary
