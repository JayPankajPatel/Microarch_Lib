COCOTB_TOPLEVEL     ?= pio_seq_prim
COCOTB_TEST_MODULES ?= test_pio_seq_prim

# Default sim is Verilator (see common.mk); to cross-check against a
# different simulator (e.g. a VCS install available on another machine),
# override: `SIM=vcs pixi run make` (drop `pixi run` if VCS is the only
# toolchain on PATH there and pixi's own env isn't set up).
include ../common.mk
