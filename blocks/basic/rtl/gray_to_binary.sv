`include "ma_assert.svh"
module gray_to_binary #(
    parameter int WIDTH = 0
) (
    input  logic [WIDTH-1:0] gray,
    output logic [WIDTH-1:0] binary
);

  `MA_ASSERT_ELABOR(ValidWidth, WIDTH > 0)

  always_comb begin
    binary[WIDTH-1] = gray[WIDTH-1];
    for (int i = WIDTH - 2; i >= 0; i = i - 1) begin
      binary[i] = binary[i+1] ^ gray[i];
    end
  end

endmodule : gray_to_binary
