// AXI4-Stream (IHI 0051B) protocol checker. Verification-only: attach with
// `bind` from a block's verif/formal/ bind file, never instantiate from RTL.
// See docs/adr/0025.
//
// Ports are the raw channel signals, not a req/resp struct, so the same
// checker binds to struct fields (s_req.tvalid, s_req.payload, ...) or to
// flat ports (s_axis_tvalid, s_axis_tdata, ...) alike.
//
// DUT_IS_TX: 1 when the bound block drives tvalid/payload on this channel
// (its m_ side) -- the transmitter rules are asserted. 0 when its
// environment drives them (its s_ side) -- the same rules are assumed.
// AXI-Stream places no mandatory rules on tready ([IHI0051B] 2.2: a Receiver
// may wait for TVALID, and may assert and deassert TREADY without TVALID).
// [DUI0534B] Table 4-10 has no TREADY error rule other than
// AXI4STREAM_ERRS_TREADY_X (simulation-only X-check);
// AXI4STREAM_RECS_TREADY_MAX_WAIT is a recommendation, not implemented here.
// So nothing switches the other way.
//
// Expects every trace to start in reset; that assumption belongs to the
// block's formal environment, not to this checker.
//
// References:
//   [IHI0051B] Arm IHI 0050B, AMBA AXI-Stream Protocol Specification
//              (ID040921), Chapter 2 "Interface Signals".
//   [DUI0534B] ARM DUI 0534B, AMBA 4 AXI4, AXI4-Lite, and AXI4-Stream
//              Protocol Assertions User Guide, Table 4-10 "Streaming
//              channel assertion rules". Rule names below are ARM's.
//              Its own page references (e.g. "Reset on Page 2-11") point to
//              the AXI4-Stream v1.0 spec, IHI 0051A; this file cites
//              IHI 0051B section numbers only.
//   [CUMMINGS] C. E. Cummings, "SystemVerilog Assertions - Bindfiles & Best
//              Known Practices for Simple SVA Usage", SNUG 2016 Silicon
//              Valley, Guideline #10 ("Use |-> ##1 implications and not |=>
//              implications") -- the style of the SVA forms quoted in the
//              comments below.

`include "ma_sva.svh"

module ma_axis_checker #(
    parameter type payload_t = logic,
    parameter bit  DUT_IS_TX = 1'b1
) (
    input logic     clk,
    input logic     rst_n,
    input logic     tvalid,
    input logic     tready,
    input payload_t payload
);

  // Yosys's slang frontend lowers only boolean property bodies plus $past
  // (measured on Yosys 0.67, docs/adr/0024 correction note);
  // it rejects |->, |=>, ##N and $stable ("unsupported SVA feature"). Each
  // rule is therefore written as its boolean equivalent:
  //   (a) |-> ##1 b   ==   !$past(rst_n && a) || b
  // The rst_n inside $past reproduces disable iff's semantics (IEEE 1800-2017
  // 16.12: "If the disable condition is true at anytime between the start of
  // the attempt ... and the end of the evaluation attempt ... the overall
  // evaluation of the property results in disabled"): an attempt that
  // started during reset is cancelled, so the check must not look back
  // into a reset cycle (where state is not yet defined).
  //   $stable(x)      ==   x == $past(x)
  // See docs/adr/0025.
  // 0 only at step 0, where $past has no history (rules without disable iff).
  // verilator lint_off PROCASSINIT
  logic f_past_valid = 1'b0;  // initializer = formal initial state
  // verilator lint_on PROCASSINIT
  always @(posedge clk) f_past_valid <= 1'b1;

  logic stalled;  // tvalid offered, not accepted
  assign stalled = tvalid && !tready;

  if (DUT_IS_TX) begin : g_tx_rules
    // [IHI0051B] 2.2.1: the valid data bytes and control information "must
    // remain unchanged once TVALID has been asserted"; with the 2.2 handshake
    // rule, that holds until the transfer. [DUI0534B] Table 4-10: the
    // AXI4STREAM_ERRM_*_STABLE rules (TDATA/TSTRB/TKEEP/TLAST/TID/TDEST/TUSER)
    // for whichever fields payload_t carries -- one rule here for the whole
    // payload. Comparing the whole payload, including null/position bytes,
    // is deliberately stricter than "valid data bytes".
    // (tvalid && !tready) |-> ##1 $stable(payload)
    `MA_ASSERT_SVA(stable_data_check_tvalid_before_ready,
                   !$past(rst_n && stalled) || (payload == $past(payload)), clk, !rst_n)
    // [IHI0051B] 2.2: "Once TVALID is asserted, it must remain asserted until
    // the handshake occurs." [DUI0534B] Table 4-10 AXI4STREAM_ERRM_TVALID_STABLE.
    // (tvalid && !tready) |-> ##1 tvalid
    `MA_ASSERT_SVA(stable_tvalid_check,
                   !$past(rst_n && stalled) || tvalid, clk, !rst_n)
    // [IHI0051B] 2.8.2 Reset and Figure 2-4 "Exit from reset": TVALID may
    // first be driven HIGH at the ACLK edge after the one where ARESETn is
    // sampled HIGH. [DUI0534B] Table 4-10 AXI4STREAM_ERRM_TVALID_RESET:
    // "TVALID is LOW for the first cycle after ARESETn goes HIGH".
    // (rst_n && !$past(rst_n)) |-> !tvalid -- no disable iff: the cycle it
    // checks follows a reset cycle.
    // NOT checked: TVALID LOW *during* reset, although [IHI0051B] 2.8.2 says
    // "During reset, TVALID must be driven LOW." [DUI0534B] Table 4-10 has no
    // rule for it either; checking it fails correct sync-reset blocks whose
    // TVALID register is undefined before the first reset edge (docs/adr/0025).
    // With DUT_IS_TX=0 the environment is likewise free to drive TVALID
    // during reset.
    `MA_ASSERT_SVA(tvalid_low_first_cycle_after_reset,
                   !f_past_valid || !rst_n || $past(rst_n) || !tvalid, clk, 1'b0)
  end else begin : g_tx_rules
    `MA_ASSUME_SVA(stable_data_check_tvalid_before_ready,
                   !$past(rst_n && stalled) || (payload == $past(payload)), clk, !rst_n)
    `MA_ASSUME_SVA(stable_tvalid_check,
                   !$past(rst_n && stalled) || tvalid, clk, !rst_n)
    `MA_ASSUME_SVA(tvalid_low_first_cycle_after_reset,
                   !f_past_valid || !rst_n || $past(rst_n) || !tvalid, clk, 1'b0)
  end

  // Reachability of the handshake orderings in [IHI0051B] 2.2: "Either
  // TVALID or TREADY can be asserted first, or both can be asserted in the
  // same ACLK cycle." valid_before_ready = 2.2.1 / Figure 2-1,
  // ready_before_valid = 2.2.2 / Figure 2-2, valid_and_ready_together =
  // 2.2.3 / Figure 2-3. back_to_back (consecutive transfers) is this
  // library's addition, not a spec figure. Each two-cycle sequence
  // "(before) ##1 (handshake)" is written as "$past(before) && handshake".
  logic handshake;
  assign handshake = tvalid && tready;
  `MA_COVER_SVA(handshake_reachable, handshake, clk, !rst_n)
  `MA_COVER_SVA(valid_before_ready, $past(rst_n && tvalid && !tready) && handshake, clk, !rst_n)
  `MA_COVER_SVA(ready_before_valid, $past(rst_n && !tvalid && tready) && handshake, clk, !rst_n)
  `MA_COVER_SVA(valid_and_ready_together, $past(rst_n && !tvalid && !tready) && handshake, clk, !rst_n)
  `MA_COVER_SVA(back_to_back, $past(rst_n && handshake) && handshake, clk, !rst_n)

endmodule : ma_axis_checker
