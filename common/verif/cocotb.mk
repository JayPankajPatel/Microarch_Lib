# Shared Cocotb/Verilator configuration for Microarch_Lib testbenches.
# Block-local common.mk files include this file as compatibility shims.

GIT_TOP       := $(shell git rev-parse --show-toplevel)
SIM           ?= verilator
TOPLEVEL_LANG ?= verilog

# Refresh and resolve the full HDL source graph once per test invocation.
$(shell bender update > /dev/null 2>&1)
VERILOG_SOURCES      := $(shell bender script flist-plus --only-sources)
VERILOG_INCLUDE_DIRS := $(shell bender script flist-plus --only-includes \
    | sed 's/^+incdir+//')

# Parallelize the generated C++ build and Verilator's internal work.
# ``$(shell nproc)`` runs nproc while Make parses this file; writing
# ``$(nproc)`` would instead expand an undefined Make variable to nothing.
MAKE_JOBS ?= $(shell nproc)
MAKEFLAGS += -j$(MAKE_JOBS)

# SystemVerilog parsing and automatic Verilator parallelism.
ifeq ($(SIM),verilator)
COMPILE_ARGS += -sv -j 0
endif

COCOTB_TOPLEVEL     ?= NONE
COCOTB_TEST_MODULES ?= NONE

# Make shared verification helpers importable from every block testbench.
export PYTHONPATH := $(GIT_TOP)/common/verif:$(PYTHONPATH)

# Cocotb appends EXTRA_ARGS to the compile and simulation commands -- these
# two flags are Verilator-specific (waveform tracing) and would be rejected
# by another simulator's CLI (e.g. `SIM=vcs`), so they're gated the same way
# COMPILE_ARGS's Verilator-only flags are above.
ifeq ($(SIM),verilator)
EXTRA_ARGS += --trace --trace-structs
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
