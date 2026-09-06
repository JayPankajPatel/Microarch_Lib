# Headless Vivado batch flow: synth + implement one top module for the
# Zybo Z7-10, then dump utilization + power reports. Used identically for
# both sc_multiply_top and binary_multiply_top so the two designs' reports
# are directly comparable.
#
# Usage: vivado -mode batch -source build_and_report.tcl -tclargs <top_module> <out_dir>

set top_module [lindex $argv 0]
set out_dir    [lindex $argv 1]
set repo_root  [file normalize [file join [file dirname [info script]] .. .. .. ..]]
set fpga_dir   [file join $repo_root blocks stocastic fpga]

file mkdir $out_dir

create_project -force sc_fpga_build $out_dir/proj -part xc7z010clg400-1

# RTL sources: shared macros, shared basic blocks, the stocastic block set,
# and this directory's two top-level wrappers -- referenced directly from
# their existing locations rather than duplicated, so this build always
# tracks the same verified sources the cocotb test suite runs against.
add_files -norecurse [list \
    $repo_root/common/rtl/ma_assert.svh \
    $repo_root/common/rtl/ma_assert_std.svh \
    $repo_root/common/rtl/ma_assert_dummy.svh \
    $repo_root/blocks/basic/counter.sv \
    $repo_root/blocks/stocastic/rtl/galois_lfsr.sv \
    $repo_root/blocks/stocastic/rtl/binary_stochastic_converter.sv \
    $repo_root/blocks/stocastic/rtl/stochastic_binary_converter.sv \
    $repo_root/blocks/stocastic/rtl/stochastic_multipler.sv \
    $fpga_dir/rtl/sc_multiply_top.sv \
    $fpga_dir/rtl/binary_multiply_top.sv \
]
set_property include_dirs $repo_root/common/rtl [current_fileset]
set_property file_type SystemVerilog [get_files *.sv]

add_files -fileset constrs_1 -norecurse $fpga_dir/constraints/zybo_z7.xdc

set_property top $top_module [current_fileset]
update_compile_order -fileset sources_1

synth_design -top $top_module -part xc7z010clg400-1
report_utilization -file $out_dir/${top_module}_utilization_synth.rpt

opt_design
place_design
route_design

report_utilization -file $out_dir/${top_module}_utilization_impl.rpt
report_power -file $out_dir/${top_module}_power.rpt
report_timing_summary -file $out_dir/${top_module}_timing.rpt

write_checkpoint -force $out_dir/${top_module}.dcp

puts "DONE: $top_module reports written to $out_dir"
