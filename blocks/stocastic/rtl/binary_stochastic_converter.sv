`include "ma_assert.svh"
module binary_stochastic_converter #(
    parameter int WIDTH = 4,
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
    input logic clk,
    input logic [WIDTH-1:0] binary_in,
    input logic rst_n,
    input logic valid_binary_in,
    input logic ready_stochastic_out,
    output logic ready_binary_in,
    output logic valid_stochastic_out,
    output logic stochastic_out,
    output logic last_cycle
);
  `MA_ASSERT_ELABOR(ValidBinarytoStocasticCheck, WIDTH inside {[2 : 64]})  // 2 to 64 inclusive
  localparam int n = WIDTH;
  // Burst is 2^N-1 bits, not 2^N: one full clean galois_lfsr period (per
  // ADR 0005/0006, the LFSR's all-zero state is unreachable, so its real
  // period is 2^N-1, not 2^N). Matches stochastic_to_binary's MAX_CYCLES
  // window size on the decode side -- see GitHub issue #2, which this
  // fixes: out_counter previously ran 0..2^N-1 inclusive (2^N distinct
  // values), one more than a clean LFSR period, so the last bit of every
  // burst duplicated the first bit's LFSR state (pigeonhole) and each
  // burst left the LFSR one extra state past a clean period, corrupting
  // both intra-burst independence and burst-to-burst phase alignment.
  localparam [$clog2((1 << n))-1:0] target_cycle_count = (1 << ((n))) - 2;
  logic [n-1:0] random_number;
  /* verilator lint_off ASCRANGE */
  logic [$clog2((1 << n))-1:0] out_counter;
  logic en;
  // out_counter is shared across bursts (never reset by rst_n mid-run) and
  // is compared against target_cycle_count as an absolute value each cycle
  // -- it must be explicitly cleared at the cycle a burst actually retires,
  // or the next burst inherits whatever residual value was left over.
  // Previously this was masked by target_cycle_count+1 always being a power
  // of 2 (target_cycle_count == 2^n-1), so out_counter's own natural
  // bit-width wraparound happened to land back on 0 for free every burst;
  // that stopped holding once target_cycle_count became 2^n-2 (fixing
  // GitHub issue #2), which is why this clear is now required, not optional.
  logic burst_complete;

  typedef struct packed {
    logic [n-1:0] binary_in_d;
    logic ready_binary_in;
    logic valid_stochastic_out;
    logic busy;
  } state_t;

  state_t r, rin;

  counter #(
      // UPTO sizes counter's output port via $clog2(UPTO) -- it wants the
      // number of distinct states out_counter ranges over (0..target_cycle_
      // count inclusive), not target_cycle_count itself. These coincided
      // when target_cycle_count was 2^n-1 ($clog2(2^n-1) == $clog2(2^n) ==
      // n for all n), which is why the pre-existing off-by-one here was
      // invisible; target_cycle_count == 2^n-2 breaks that coincidence
      // exactly at n=2 (2^n-2 == 2, a power of 2, so $clog2 underestimates
      // by one bit) -- confirmed via verilator WIDTHTRUNC at the default
      // WIDTH=2 elaboration.
      .UPTO(target_cycle_count + 1)
  ) counter (
      .clk(clk),
      .en(en),
      .clr(burst_complete),
      .rst_n(rst_n),
      .out(out_counter)
  );
  galois_lfsr #(
      .WIDTH(WIDTH),
      .INIT_SEED(INIT_SEED)
  ) RNG (
      .clk(clk),
      .en(en),
      .rst_n(rst_n),
      .out(random_number)
  );

  always_comb begin
    rin = r;  // default: hold every field unless overridden below

    if (!r.busy) begin
      // Starting a burst depends only on this module's own state and its
      // own input (valid_binary_in) -- never on ready_stochastic_out.
      // ready_stochastic_out gates whether an *already-presented* bit gets
      // consumed (mid-burst advance/completion, below), not whether a new
      // burst is allowed to begin. Gating the accept itself on
      // ready_stochastic_out being already high is the same "VALID
      // implicitly waits for READY" AMBA violation stochastic_to_binary's
      // completion branch had (see docs/adr/0013's confirmation section and
      // the original decoder fix this session) -- it's just inert as long
      // as every consumer's readiness happens to be independent of this
      // encoder's own valid. Composing two encoders into
      // stochastic_multiplier's join (whose ready_stochastic_in_a depends
      // on valid_stochastic_in_b, and vice versa) turns that latent
      // violation into a real mutual-startup deadlock: neither encoder's
      // accept condition can ever fire, because each is waiting on a
      // ready signal that only becomes true once the OTHER encoder is
      // already valid. See docs/adr/0016.
      if (valid_binary_in) begin
        rin.binary_in_d = binary_in;
        rin.busy = 1'b1;
        rin.ready_binary_in = 1'b0;
        rin.valid_stochastic_out = 1'b1;
      end
    end else begin
      if (burst_complete) begin
        // last bit is being consumed this cycle
        rin.ready_binary_in = 1'b1;
        rin.valid_stochastic_out = 1'b0;
        rin.busy = 1'b0;
      end else begin
        rin.ready_binary_in = 1'b0;
        rin.valid_stochastic_out = 1'b1;
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      r.binary_in_d <= '0;
      r.ready_binary_in <= '1;
      r.valid_stochastic_out <= '0;
      r.busy <= '0;
    end else begin
      r <= rin;
    end
  end

  assign burst_complete = r.busy && (out_counter == target_cycle_count) && ready_stochastic_out;
  // last_cycle must track burst_complete exactly, not merely out_counter's
  // value -- during a downstream stall at the burst boundary, out_counter
  // holds at target_cycle_count for the whole stall while the burst hasn't
  // actually retired (counter isn't cleared, LFSR hasn't advanced past this
  // bit). A version of this signal that only checked out_counter would
  // assert for that entire stall instead of the one real retiring cycle --
  // exactly the kind of "true by coincidence, not by construction" gap
  // docs/adr/0013 exists to eliminate. No current consumer, but this is the
  // public "last bit of the burst" signal future chain-mode wiring would use.
  assign last_cycle = burst_complete;
  assign en = (r.busy && ready_stochastic_out);
  assign ready_binary_in = r.ready_binary_in;
  assign valid_stochastic_out = r.valid_stochastic_out;
  assign stochastic_out = ((random_number < r.binary_in_d) ? 1'b1 : 1'b0);
endmodule : binary_stochastic_converter
