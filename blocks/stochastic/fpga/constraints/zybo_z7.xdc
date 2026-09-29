# Zybo Z7 constraints for the SC-vs-binary multiplier area/power comparison.
# Subset of the official Digilent Zybo Z7 Rev. B master XDC (compatible with
# both Zybo Z7-10 and Zybo Z7-20), copied from
# ~/Repos/FPGA_Pedal/FPGA_Pedal/FPGA_Pedal.srcs/constrs_1/new/zybo_z7.xdc --
# only clk and led are needed for this synthesis/implementation-only
# comparison (no switches/buttons -- operands are driven internally by
# free-running counters, see sc_multiply_top.sv/binary_multiply_top.sv).

# Clock signal (125 MHz)
set_property -dict { PACKAGE_PIN K17   IOSTANDARD LVCMOS33 } [get_ports { clk }]; #IO_L12P_T1_MRCC_35 Sch=sysclk
create_clock -add -name sys_clk_pin -period 8.00 -waveform {0 4} [get_ports { clk }];

# LEDs
set_property -dict { PACKAGE_PIN M14   IOSTANDARD LVCMOS33 } [get_ports { led[0] }]; #IO_L23P_T3_35 Sch=led[0]
set_property -dict { PACKAGE_PIN M15   IOSTANDARD LVCMOS33 } [get_ports { led[1] }]; #IO_L23N_T3_35 Sch=led[1]
set_property -dict { PACKAGE_PIN G14   IOSTANDARD LVCMOS33 } [get_ports { led[2] }]; #IO_0_35 Sch=led[2]
set_property -dict { PACKAGE_PIN D18   IOSTANDARD LVCMOS33 } [get_ports { led[3] }]; #IO_L3N_T0_DQS_AD1N_35 Sch=led[3]
