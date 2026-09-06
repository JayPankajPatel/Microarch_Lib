COCOTB_TOPLEVEL     ?= top
COCOTB_TEST_MODULES ?= test_b_mult_s_integration

include ../common.mk

# top.sv is a test-only integration wrapper (chains two encoders' outputs
# through the multiplier into the decoder) -- it isn't a product block
# under blocks/stocastic/rtl/, so bender's flist doesn't pick it up.
# Append it after common.mk's bender-derived VERILOG_SOURCES.
VERILOG_SOURCES += $(shell pwd)/top.sv
