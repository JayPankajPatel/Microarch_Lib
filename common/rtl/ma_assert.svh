// Elaboration-time check macro dispatch. Include this before using
// `MA_ASSERT_INIT in any RTL file.

`ifndef MA_ASSERT_SV
`define MA_ASSERT_SV

// Converts an arbitrary token into a Verilog string literal.
`define MA_STRINGIFY(__x) `"__x`"

// SYNTHESIS: checks produce no synthesizable logic, so strip them entirely
// rather than feed them into synthesis.
// YOSYS: parameterized elaboration-check support is unverified there;
// stay conservative until confirmed.
// Everything else (VCS, Xcelium, Verilator) gets the real macros --
// Also, Verilator 4.038 was confirmed locally to handle the bare `$error`
// elaboration system task with no special flags.
`ifdef SYNTHESIS
 `include "ma_assert_dummy.svh"
`elsif YOSYS
 `include "ma_assert_dummy.svh"
`else
 `include "ma_assert_std.svh"
`endif

`endif // MA_ASSERT_SV
