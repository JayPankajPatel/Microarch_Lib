
`include "ma_assert.svh"
module stochastic_to_binary #(
    parameter int WIDTH = 4
) (
    input logic clk,
    input logic rst_n,
    input logic stochastic_in,
    input logic valid_stochastic_in,
    // Explicit window-boundary pulse from the producer, meaningful only on
    // a cycle a sample is actually transferred (valid_stochastic_in &&
    // ready_stochastic_in): tells this module "the sample being accepted
    // this cycle is the last one of its window," instead of this module
    // inferring completion from a locally-counted cycle_count reaching a
    // fixed target. See docs/adr/0017 for why: matching burst/window
    // lengths on both sides only guarantees alignment if both sides also
    // happen to reset their counters on the same real-transfer index --
    // any transient skew (or, more generally, any topology where there's
    // no single well-defined upstream "burst length" to match against,
    // e.g. downstream of a join composing two independently-timed
    // producers) turns into a silent, permanent window/value misalignment.
    // A boundary pulse from the actual producer-side event makes this
    // module's notion of "window" externally synchronized by construction
    // rather than by coincidence.
    input logic boundary_in,
    input logic ready_binary_out,
    output logic ready_stochastic_in,
    output logic valid_binary_out,
    output logic [WIDTH-1:0] binary_out
);
  `MA_ASSERT_ELABOR(ValidStocastictoBinaryCheck, WIDTH inside {[2 : 64]})  // 2 to 64 inclusive

  localparam int n = WIDTH;

  // A real transfer happens exactly when both sides of this module's own
  // input handshake are true this cycle -- this is what boundary_in must
  // be sampled against (a boundary_in asserted on a cycle with no real
  // transfer means nothing).
  logic accept_this_cycle;
  assign accept_this_cycle = valid_stochastic_in && ready_stochastic_in;

  typedef struct packed {
    logic [n-1:0] ones_count;
    logic [n-1:0] binary_out_d;
    logic valid_binary_out;
    // Latched the cycle a boundary-flagged sample was accepted; takes over
    // cycle_count==MAX_CYCLES's old role of "the window is done, waiting to
    // announce/reopen" -- see docs/adr/0017.
    logic last_sample_seen;
  } bin_to_sto_t;
  bin_to_sto_t r, rin;

  // Output side is a proper one-entry elastic register (skid buffer):
  // valid_binary_out marks the slot occupied, and the window only latches
  // into it -- reopening the accumulator in the same transition -- once the
  // slot is empty or is being drained this same cycle. A prior version
  // decided whether to reopen using ready_binary_out sampled on the cycle
  // BEFORE valid_binary_out ever became externally visible, which is a
  // stale/speculative snapshot: if the consumer's ready happened to differ
  // between that cycle and the one where valid was actually visible, the
  // module would drop a result that was never actually transferred
  // (confirmed independent-audit finding). Gating strictly on
  // slot_available -- evaluated using ready_binary_out and valid_binary_out
  // AS THEY STAND THE SAME CYCLE -- removes that race entirely.
  logic slot_available;
  assign slot_available = !r.valid_binary_out || ready_binary_out;

  always_comb begin
    rin = r;
    if (r.last_sample_seen && slot_available) begin
      // window complete and the slot is free (empty, or drained this same
      // cycle) -- latch the result and reopen the accumulator for the next
      // window in the same transition (zero-bubble when draining).
      // ready_stochastic_in is low whenever r.last_sample_seen is high, so
      // accept_this_cycle cannot also be true here -- no conflict with the
      // independent branch below.
      rin.binary_out_d = r.ones_count;
      rin.valid_binary_out = 1'b1;
      rin.ones_count = '0;
      rin.last_sample_seen = 1'b0;
    end else begin
      // Output-slot draining and input accumulation touch disjoint state
      // (valid_binary_out vs. ones_count/last_sample_seen) and can both
      // happen on the same edge -- e.g. a completed-but-unconsumed result
      // sitting in the slot gets drained (ready_binary_out) on the exact
      // same cycle a new sample for the NEXT window is accepted
      // (valid_stochastic_in && ready_stochastic_in, since last_sample_seen
      // is 0 while accumulating). A prior version chained these as
      // mutually-exclusive `else if` branches: the drain branch firing
      // silently prevented the accept branch from ever running, discarding
      // an input sample the module had already told the producer it
      // accepted (confirmed independent-audit finding, since
      // ready_stochastic_in doesn't depend on the output side at all).
      // Two independent `if`s, not `else if`, so both can fire together.
      if (r.valid_binary_out && ready_binary_out) begin
        // slot drained this cycle with no new window ready to replace it --
        // clear valid rather than let the consumer see a "successful"
        // valid&&ready handshake against a stale repeat next cycle.
        rin.valid_binary_out = 1'b0;
      end
      if (accept_this_cycle) begin
        rin.ones_count = r.ones_count + (stochastic_in == 1'b1);
        rin.last_sample_seen = boundary_in;
      end
    end
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      r.ones_count <= '0;
      r.binary_out_d <= '0;
      r.valid_binary_out <= '0;
      r.last_sample_seen <= '0;
    end else begin
      r <= rin;
    end
  end

  assign binary_out = r.binary_out_d;
  assign valid_binary_out = rst_n && r.valid_binary_out;
  assign ready_stochastic_in = rst_n && !r.last_sample_seen;

endmodule : stochastic_to_binary
