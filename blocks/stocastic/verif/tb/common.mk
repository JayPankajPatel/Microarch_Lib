# Defaults
GIT_TOP       := $(shell git rev-parse --show-toplevel)
SIM           ?= verilator
TOPLEVEL_LANG ?= verilog

# Force bender to update dependencies once at startup
$(shell bender update > /dev/null 2>&1)

# Extract sources and include dirs from bender (flist-plus keeps them separate
# so VERILOG_INCLUDE_DIRS can drive cocotb's own +incdir+ handling below)
VERILOG_SOURCES      := $(shell bender script flist-plus --only-sources)
VERILOG_INCLUDE_DIRS := $(shell bender script flist-plus --only-includes | sed 's/^+incdir+//')

# Verilator specific flags: Treat .sv files as SystemVerilog explicitly
ifeq ($(SIM),verilator)
COMPILE_ARGS += -sv
endif

# Cocotb setup
# COCOTB_TOPLEVEL     = binary_to_stochastic
# COCOTB_TEST_MODULES = test_binary_to_stochastic
COCOTB_TOPLEVEL     ?= NONE
COCOTB_TEST_MODULES ?= NONE

# Make the shared clock/reset helpers (common/verif/ma_clkrst.py) importable
# from any block's testbench
export PYTHONPATH := $(GIT_TOP)/common/verif:$(PYTHONPATH)
# export waveform: WAVES is only wired up for icarus/dsim/riviera/questa in
# cocotb's own Makefiles; VERILATOR_TRACE is deprecated. EXTRA_ARGS gets
# appended to both the verilator compile step and the sim run, so this one
# line both instruments the design and enables the dump at runtime.
EXTRA_ARGS += --trace --trace-structs
# Let Pixi look up the local configuration binary natively
# Change width of module 
include $(shell cocotb-config --makefiles)/Makefile.sim
