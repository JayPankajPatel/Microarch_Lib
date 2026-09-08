`include "ma_assert.svh"
// Synchronous-reset variant of counter.sv, for targets whose flip-flop
// primitive has no async reset input (e.g. FABulous fabric BELs -- see
// docs/adr/0020 and ~/wiki/fpga_stochastic_blocks/reusable_lessons/
// fabric-ff-primitive-sync-reset-only.md). Identical logic to counter.sv;
// the only change is the always_ff sensitivity list (no `or negedge rst_n`)
// -- `if (!rst_n)` now reads synchronously instead of asynchronously, which
// is correct and sufficient for this module's existing reset/clear
// structure. Kept as a parallel file, not a replacement: counter.sv stays
// the verified async-reset default for every ASIC-target use.
module counter_sync #(
    /* verilator lint_off WIDTHEXPAND */
    // See counter.sv's identical comment: `int` (32-bit signed) can't hold
    // UPTO=2^64-1 and silently reinterprets values >= 2^31 as negative.
    parameter longint unsigned UPTO = 100
) (
    input logic clk,
    input logic en,
    input logic clr,
    input logic rst_n,
    output logic [$clog2(UPTO)-1:0] out
);
  `MA_ASSERT_ELABOR(ValidCounterSize, UPTO > 0)

  // clr takes priority over en so a caller can synchronously restart a
  // count window on the same cycle it would otherwise have incremented
  // (e.g. reusing this counter across back-to-back windows without
  // depending on its natural bit-width wraparound landing back on 0 --
  // that only happens to line up when UPTO is itself a power of 2).
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      out <= '0;
    end else if (clr) begin
      out <= '0;
    end else if (en) begin
      out <= out + 1'b1;
    end
  end
endmodule : counter_sync
