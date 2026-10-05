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

`endif // MA_SVA_SVH
