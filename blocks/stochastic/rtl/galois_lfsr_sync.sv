`include "ma_assert.svh"
// Synchronous-reset variant of galois_lfsr.sv, for targets whose flip-flop
// primitive has no async reset input (e.g. FABulous fabric BELs -- see
// docs/adr/0020 and ~/wiki/fpga_stochastic_blocks/reusable_lessons/
// fabric-ff-primitive-sync-reset-only.md). Identical logic; the only
// change is the always_ff sensitivity list. Kept as a parallel file, not a
// replacement: galois_lfsr.sv stays the verified async-reset default.
module galois_lfsr_sync #(
    parameter int WIDTH = 4,
    parameter bit [WIDTH-1:0] INIT_SEED = WIDTH'(1)
) (
    input logic clk,
    input logic en,
    input logic rst_n,
    output logic [WIDTH-1:0] out
);

  // we can only have an LFSR that is 2 bits to 64 bits inclusive, wide based on
  // the polynomial array we have, if more is needed, the array only must change
  `MA_ASSERT_ELABOR(ValidLFSRSizeCheck, WIDTH inside {[2 : 64]})  // 2 to 64 inclusive
  `MA_ASSERT_ELABOR(NoZeroSeed, INIT_SEED != '0)  // 2 to 64 inclusive


  // Synthesizable TAPS Look-Up "Table" (0-Indexed, aligned for i-1 checks).
  // Argument bounds [0:64] match the LFSR WIDTH parameter directly.
  //
  // Expressed as a constant function (case statement) rather than a
  // `localparam` array of indexed-assignment-pattern entries: the array
  // form doesn't parse under Yosys's native Verilog frontend (used by the
  // SymbiYosys formal flow in verif/formal/), which supports only a small
  // subset of SystemVerilog. `automatic` here only affects simulation
  // local-variable storage (per-call, not shared/static) -- with no
  // recursion and a compile-time-constant argument (`n = WIDTH` below),
  // this synthesizes to pure constant folding, not a runtime call stack.
  //
  // Low-Hamming-weight (sparse) masks; see
  // docs/adr/0005-taps-lut-sparse-vs-dense-ppa.md for the PPA comparison and
  // primitivity verification, and docs/adr/0008-taps-lut-yosys-frontend-encoding.md
  // for why this is a function instead of a `localparam` array.
  function automatic bit [63:0] taps(int n);
    case (n)
      0: taps = 64'h0;
      1: taps = 64'h0;
      2: taps = 64'h1;
      3: taps = 64'h1;
      4: taps = 64'h4;  // q[2]
      5: taps = 64'h4;  // q[2]
      6: taps = 64'h10;  // q[4]
      7: taps = 64'h20;  // q[5]
      8: taps = 64'h38;  // q[5], q[4], q[3]
      9: taps = 64'h10;  // q[4]
      10: taps = 64'h40;  // q[6]
      11: taps = 64'h100;  // q[8]
      12: taps = 64'h29;
      13: taps = 64'h241;
      14: taps = 64'h409;
      15: taps = 64'h2000;  // q[13]
      16: taps = 64'h406;
      17: taps = 64'h2000;  // q[13]
      18: taps = 64'h400;  // q[10]
      19: taps = 64'h1101;
      20: taps = 64'h10000;  // q[16]
      21: taps = 64'h40000;  // q[18]
      22: taps = 64'h100000;  // q[20]
      23: taps = 64'h20000;  // q[17]
      24: taps = 64'h104001;
      25: taps = 64'h200000;  // q[21]
      26: taps = 64'h142;
      27: taps = 64'h13;
      28: taps = 64'h1000000;  // q[24]
      29: taps = 64'h4000000;  // q[26]
      30: taps = 64'h4020001;
      31: taps = 64'h8000000;  // q[27]
      32: taps = 64'h200003;
      33: taps = 64'h1000;  // q[12]
      34: taps = 64'hC02;
      35: taps = 64'h2;  // q[1]
      36: taps = 64'h400;  // q[10]
      37: taps = 64'hA02;  // q[11], q[9], q[1]
      38: taps = 64'h14002000;
      39: taps = 64'h8;  // q[3]
      40: taps = 64'h140002;  // q[20], q[18], q[1]
      41: taps = 64'h4;  // q[2]
      42: taps = 64'h4020000040;
      43: taps = 64'h38;  // q[5], q[3], q[2]
      44: taps = 64'h32;  // q[5], q[4], q[1]
      45: taps = 64'h40080040000;
      46: taps = 64'hC00001;
      47: taps = 64'h10;  // q[4]
      48: taps = 64'h400002001000;
      49: taps = 64'h100;  // q[8]
      50: taps = 64'h10080002000;
      51: taps = 64'h1200010;
      52: taps = 64'h4;  // q[2]
      53: taps = 64'h400100200;
      54: taps = 64'h20000010080;
      55: taps = 64'h800000;  // q[23]
      56: taps = 64'h4024000;
      57: taps = 64'h40;  // q[6]
      58: taps = 64'h40000;  // q[18]
      59: taps = 64'h300002;  // q[21], q[20], q[1]
      60: taps = 64'h1;
      61: taps = 64'h200000040001000;
      62: taps = 64'h8000010000040;
      63: taps = 64'h1;
      64: taps = 64'h4040000000000020;
      default: taps = 64'h0;
    endcase
  endfunction

  localparam n = WIDTH;
  // Yosys's native frontend doesn't support bit-selecting a function call's
  // return value directly (`taps(n)[...]`); precompute it into a localparam
  // once instead, which also avoids calling `taps(n)` on every loop
  // iteration below.
  localparam bit [63:0] tap_mask = taps(n);
  logic [n-1:0] q;
  logic feedback;
  assign feedback = q[n-1];
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      q <= INIT_SEED;
    end else if (en) begin
      q[0] <= feedback;
      for (int i = 1; i < n; i = i + 1) begin
        // tap_mask bit b always means polynomial term x^(b+1) (ascending
        // degree with bit index). This Galois circuit needs the tap for
        // degree k injected at stage (n-k) -- descending degree as stages
        // move away from the feedback re-entry point at q[n-1] -- so reading
        // the mask at [n-1-i] (not [i]) corrects for that ascending-vs-
        // descending mismatch. See docs/adr/0006.
        q[i] <= (q[i-1]) ^ (feedback & tap_mask[n-1-i]);
      end
    end
  end

  assign out = q;

`ifdef FORMAL
  // Formal-only: `bind`ing a separate checker module parses fine under
  // Yosys's native frontend but the bound instance is silently dropped
  // during `prep -top` hierarchy elaboration (confirmed empirically: no
  // `$check`/`$assert` cell appears in `stat` output, so the property is
  // never actually checked). An inline assertion, guarded by `` `ifdef
  // FORMAL `` the same way `` `ifdef SYNTHESIS ``/`` `YOSYS `` guard
  // MA_ASSERT_ELABOR above, does survive elaboration. See
  // docs/adr/0009-formal-checker-inline-not-bind.md.
  //
  // Without constraining the initial state, the BMC base case can start
  // from an arbitrary (unconstrained) q, including q == '0, which trivially
  // violates no_lockup with no real counterexample behind it -- forcing
  // rst_n low at the trace's first step drives q to INIT_SEED before the
  // property is ever checked, matching how this module is actually used.
  initial assume (!rst_n);
  always @(posedge clk)
    if (rst_n) begin
      no_lockup : assert (out != '0);
    end
`endif

endmodule : galois_lfsr_sync
