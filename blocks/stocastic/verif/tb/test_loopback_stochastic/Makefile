COCOTB_TOPLEVEL     ?= loopback_top
COCOTB_TEST_MODULES ?= test_loopback_stochastic

COMPILE_ARGS += -GWIDTH=4

include ../common.mk

# loopback_top.sv is a test-only integration wrapper (chains the encoder's
# stochastic_out into the decoder's stochastic_in) -- it isn't a product
# block under blocks/stocastic/rtl/, so bender's flist doesn't pick it up.
# Append it after common.mk's bender-derived VERILOG_SOURCES.
VERILOG_SOURCES += $(shell pwd)/loopback_top.sv
