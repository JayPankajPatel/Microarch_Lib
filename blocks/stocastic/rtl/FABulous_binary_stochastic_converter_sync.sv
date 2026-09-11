// Synchronous-reset variant of binary_stochastic_converter.sv, for targets
// whose flip-flop primitive has no async reset input (e.g. FABulous
// fabric BELs -- see docs/adr/0020 and ~/wiki/fpga_stochastic_blocks/
// reusable_lessons/fabric-ff-primitive-sync-reset-only.md). Identical
// logic; only the always_ff sensitivity list changes, and it instantiates
// counter_sync/galois_lfsr_sync instead of counter/galois_lfsr so the
// whole reset domain stays consistently synchronous. Kept as a parallel
// file: binary_stochastic_converter.sv stays the verified async-reset
// default.
module FABulous_binary_stochastic_converter_sync #(
    parameter int WIDTH = 8,
    // Two encoder instances sharing the default seed (or any identical
    // seed+WIDTH pair) drive their internal galois_lfsr in lockstep --
    // fully correlated random streams. Composing multiple encoders whose
    // outputs feed a shared consumer (e.g. stochastic_multiplier) requires
    // giving each instance a distinct INIT_SEED, or the multiplier's AND
    // silently computes min(a,b) instead of a*b -- a well-known
    // stochastic-computing correctness trap that looks protocol-correct
    // (valid handshakes, plausible-looking bits) while being numerically
    // wrong. See docs/adr/0015.
    parameter bit [WIDTH-1:0] INIT_SEED = WIDTH'(1)
) (
    (* FABulous, EXTERNAL, SHARED_PORT *) input logic UserCLK,
    input logic [WIDTH-1:0] binary_in,
    // Keep reset normally routable. If the containing tile deliberately
    // provides one reset shared by all of its BELs, this port and the
    // corresponding tile JUMP may instead be marked SHARED_RESET.
    input logic rst_n,
    input logic valid_binary_in,
    input logic ready_stochastic_out,
    output logic ready_binary_in,
    output logic valid_stochastic_out,
    output logic stochastic_out,
    output logic last_cycle
);

  // There is deliberately no FABulous SHARED_ENABLE port. The wrapped
  // converter derives its internal counter/LFSR advance enable from its
  // busy state and ready_stochastic_out, so the ready/valid handshake must
  // remain visible to the normal routing fabric.
  binary_stochastic_converter_sync #(
      .WIDTH(WIDTH),
      .INIT_SEED(INIT_SEED)
  ) BEL (
      .clk(UserCLK),
      .binary_in(binary_in),
      .rst_n(rst_n),
      .valid_binary_in(valid_binary_in),
      .ready_stochastic_out(ready_stochastic_out),
      .ready_binary_in(ready_binary_in),
      .valid_stochastic_out(valid_stochastic_out),
      .stochastic_out(stochastic_out),
      .last_cycle(last_cycle)
  );

endmodule : FABulous_binary_stochastic_converter_sync
