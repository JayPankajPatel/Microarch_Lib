module stochastic_multiplier (
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic clk,
    input  logic rst_n,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic stochastic_in_a,
    input  logic valid_stochastic_in_a,
    output logic ready_stochastic_in_a,
    input  logic stochastic_in_b,
    input  logic valid_stochastic_in_b,
    output logic ready_stochastic_in_b,
    input  logic ready_stochastic_out,
    output logic valid_stochastic_out,
    output logic stochastic_out
);
  // Stochastic multiplication is just AND -- no registered state needed,
  // this is a pure combinational join of two independent producers into one
  // consumer. Each producer's ready is gated on the *other* producer's
  // valid (not its own), so a bit is only ever consumed from A when B has
  // one ready that same cycle, and vice versa; valid_out only asserts when
  // both do. clk/rst_n are unused by the join itself but kept in the port
  // list to match every other block's convention in this repo.
  assign valid_stochastic_out   = valid_stochastic_in_a && valid_stochastic_in_b;
  assign ready_stochastic_in_a  = ready_stochastic_out && valid_stochastic_in_b;
  assign ready_stochastic_in_b  = ready_stochastic_out && valid_stochastic_in_a;
  assign stochastic_out         = stochastic_in_a && stochastic_in_b;

endmodule : stochastic_multiplier
