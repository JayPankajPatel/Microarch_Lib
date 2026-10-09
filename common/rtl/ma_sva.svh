// Concurrent SVA property wrappers. Always defined -- no tool dispatch.
// Include only from verification files (checkers, bind files), never from
// synthesizable RTL; verification sources are kept out of synthesis by file
// list, not by `ifdef. See docs/adr/0025.
//
// __reset is the disable condition (pass !rst_n for active-low reset, or
// 1'b0 for a rule that must also hold during reset).

`ifndef MA_SVA_SVH
`define MA_SVA_SVH

`define MA_ASSUME_SVA(__name, __expr, __clock, __reset) \
__name: assume property ( \
    @(posedge __clock) disable iff (__reset) (__expr) \
);

`define MA_ASSERT_SVA(__name, __expr, __clock, __reset) \
__name: assert property ( \
    @(posedge __clock) disable iff (__reset) (__expr) \
);

`define MA_COVER_SVA(__name, __expr, __clock, __reset) \
__name: cover property ( \
    @(posedge __clock) disable iff (__reset) (__expr) \
);

// Formal environment: assume every trace starts in reset.
// __rst_asserted is the condition meaning "reset is active" -- pass !rst_n
// for an active-low reset, rst for an active-high one. Declares
// ma_f_past_valid, which is 0 only at the first step (where $past has no
// history); properties in the same scope may use it as a $past guard.
// The initializer is the formal initial state (formal-only idiom), hence
// the PROCASSINIT waiver. Use at most once per module scope.
`define MA_ASSUME_RESET_AT_START(__clock, __rst_asserted) \
/* verilator lint_off PROCASSINIT */ \
logic ma_f_past_valid = 1'b0; \
/* verilator lint_on PROCASSINIT */ \
always @(posedge __clock) ma_f_past_valid <= 1'b1; \
always @(posedge __clock) if (!ma_f_past_valid) assume (__rst_asserted);

`endif // MA_SVA_SVH
