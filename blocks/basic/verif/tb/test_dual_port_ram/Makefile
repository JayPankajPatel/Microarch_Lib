COCOTB_TOPLEVEL     ?= dual_port_ram
COCOTB_TEST_MODULES ?= test_dual_port_ram

# dual_port_ram has zero-default parameters (rejected at elaboration), so the
# testbench must set them; the Python side reads the same values.
DATA_WIDTH ?= 8
DEPTH      ?= 16
COMPILE_ARGS += -GDATA_WIDTH=$(DATA_WIDTH) -GDEPTH=$(DEPTH)
export DATA_WIDTH DEPTH

include ../common.mk
