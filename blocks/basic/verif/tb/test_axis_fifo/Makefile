SIM                  ?= verilator
TOPLEVEL_LANG        ?= verilog
COCOTB_TOPLEVEL      ?= axis_fifo
COCOTB_TEST_MODULES  ?= test_axis_fifo

# Keep this first practice block independent of Bender while the basic-block
# source layout is being reorganized.
VERILOG_SOURCES := $(abspath ../../../rtl/axis_fifo.sv)
COMPILE_ARGS += -sv

GIT_TOP := $(shell git rev-parse --show-toplevel)
export PYTHONPATH := $(GIT_TOP)/common/verif:$(PYTHONPATH)
EXTRA_ARGS += --trace --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim
