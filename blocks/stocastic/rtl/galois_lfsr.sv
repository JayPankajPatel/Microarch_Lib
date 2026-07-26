`include "ma_assert.svh"
module galois_lfsr #(
  parameter int WIDTH = 4,
  parameter bit [WIDTH-1:0] INIT_SEED = WIDTH'(1)
  )
(
  input logic clk,
  input logic rst_n,
  output logic [WIDTH-1:0] out
);

// we can only have an LFSR that is 2 bits to 64 bits inclusive, wide based on
// the polynomial array we have, if more is needed, the array only must change
`MA_ASSERT_INIT(ValidLFSRSizeCheck, WIDTH inside {[2:64]}) // 2 to 64 inclusive
`MA_ASSERT_INIT(NoZeroSeed, INIT_SEED != '0) // 2 to 64 inclusive


// Synthesizable TAPS Look-Up Table (0-Indexed, aligned for i-1 checks)
// Array bounds [0:64] match the LFSR WIDTH parameter directly.
//
// Low-Hamming-weight (sparse) masks; see
// docs/adr/0005-taps-lut-sparse-vs-dense-ppa.md for the PPA comparison and
// primitivity verification.
localparam bit [63:0] TAPS_LUT [0:64] = '{
    0  : 64'h0,
    1  : 64'h0,
    2  : 64'h1,
    3  : 64'h1,
    4  : 64'h4,                 // q[2]
    5  : 64'h4,                 // q[2]
    6  : 64'h10,                // q[4]
    7  : 64'h20,                // q[5]
    8  : 64'h38,                // q[5], q[4], q[3]
    9  : 64'h10,                // q[4]
    10 : 64'h40,                // q[6]
    11 : 64'h100,               // q[8]
    12 : 64'h29,
    13 : 64'h241,
    14 : 64'h409,
    15 : 64'h2000,              // q[13]
    16 : 64'h406,
    17 : 64'h2000,              // q[13]
    18 : 64'h400,               // q[10]
    19 : 64'h1101,
    20 : 64'h10000,             // q[16]
    21 : 64'h40000,             // q[18]
    22 : 64'h100000,            // q[20]
    23 : 64'h20000,             // q[17]
    24 : 64'h104001,
    25 : 64'h200000,            // q[21]
    26 : 64'h142,
    27 : 64'h13,
    28 : 64'h1000000,           // q[24]
    29 : 64'h4000000,           // q[26]
    30 : 64'h4020001,
    31 : 64'h8000000,           // q[27]
    32 : 64'h200003,
    33 : 64'h1000,              // q[12]
    34 : 64'hC02,
    35 : 64'h2,                 // q[1]
    36 : 64'h400,               // q[10]
    37 : 64'hA02,               // q[11], q[9], q[1]
    38 : 64'h14002000,
    39 : 64'h8,                 // q[3]
    40 : 64'h140002,            // q[20], q[18], q[1]
    41 : 64'h4,                 // q[2]
    42 : 64'h4020000040,
    43 : 64'h38,                // q[5], q[3], q[2]
    44 : 64'h32,                // q[5], q[4], q[1]
    45 : 64'h40080040000,
    46 : 64'hC00001,
    47 : 64'h10,                // q[4]
    48 : 64'h400002001000,
    49 : 64'h100,               // q[8]
    50 : 64'h10080002000,
    51 : 64'h1200010,
    52 : 64'h4,                 // q[2]
    53 : 64'h400100200,
    54 : 64'h20000010080,
    55 : 64'h800000,            // q[23]
    56 : 64'h4024000,
    57 : 64'h40,                // q[6]
    58 : 64'h40000,             // q[18]
    59 : 64'h300002,            // q[21], q[20], q[1]
    60 : 64'h1,
    61 : 64'h200000040001000,
    62 : 64'h8000010000040,
    63 : 64'h1,
    64 : 64'h4040000000000020
};

logic [WIDTH-1:0] q;
always_ff @(posedge clk or negedge rst_n) begin 
  if(!rst_n) begin 
    q <= INIT_SEED; 
  end
  else begin
    for(int i = WIDTH-1; i >= 0; i--) begin 
      q[i] <= ((TAPS_LUT[WIDTH][i]) ? (q[(i+1) % WIDTH] ^ q[0]) : (q[(i+1) % WIDTH]));
    end
  end
end

assign out = q; 

endmodule : galois_lfsr
