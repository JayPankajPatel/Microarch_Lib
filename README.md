# Microarch_Lib

[![Nightly Regression](https://github.com/JayPankajPatel/Microarch_Lib/actions/workflows/nightly.yml/badge.svg)](https://github.com/JayPankajPatel/Microarch_Lib/actions/workflows/nightly.yml)

A collection of reusable SystemVerilog RTL modules for my projects, verified with
cocotb and SymbiYosys. Design decisions are recorded as ADRs in [`docs/adr/`](docs/adr/).

## Directory Structure

```
.
├── blocks/                   RTL blocks, one directory per family
│   ├── basic/                general-purpose primitives
│   │   ├── rtl/
│   │   └── verif/tb/         cocotb testbenches
│   └── stochastic/            stochastic-computing blocks
│       ├── rtl/
│       ├── docs/waveforms/   WaveDrom sources (.json) + rendered .svg
│       ├── verif/
│       │   ├── tb/           cocotb testbenches (unit + integration)
│       │   └── formal/       SymbiYosys (.sby) proofs
│       ├── fpga/             Vivado area/power comparison (tops, XDC, TCL, reports)
│       └── pnr/              LibreLane/sky130 PPA experiments (not library RTL)
├── common/
│   ├── rtl/                  shared headers (`ma_*` macros)
│   └── verif/                shared cocotb infrastructure
├── docs/
│   ├── adr/                  Architecture Decision Records (index: docs/adr/README.md)
│   └── design-specs/         repo-wide design documents and conventions
├── scripts/                  setup, regression, and helper scripts
├── Bender.yml                RTL source manifest
└── pixi.toml                 toolchain environment and tasks
```

## List of Modules

### Basic

| Name | Description |
|---|---|
| [`counter`](blocks/basic/rtl/counter.sv) | Counter with synchronous clear |
| [`counter_sync`](blocks/basic/rtl/counter_sync.sv) | Synchronous-reset variant of `counter` |
| [`axis_fifo`](blocks/basic/rtl/axis_fifo.sv) | Toy AXI-Stream FIFO for bootstrapping verification infrastructure (not for production use) |

### Stochastic Computing

| Name | Description |
|---|---|
| [`galois_lfsr`](blocks/stochastic/rtl/galois_lfsr.sv) | Galois LFSR, WIDTH 2–64, used as the random source for encoders |
| [`binary_stochastic_converter`](blocks/stochastic/rtl/binary_stochastic_converter.sv) | Binary → stochastic bitstream encoder (valid/ready) |
| [`stochastic_binary_converter`](blocks/stochastic/rtl/stochastic_binary_converter.sv) | Stochastic bitstream → binary decoder (valid/ready) |
| [`stochastic_multiplier`](blocks/stochastic/rtl/stochastic_multiplier.sv) | Stochastic multiply (AND) as a valid/ready join of two streams |
| [`stochastic_adder`](blocks/stochastic/rtl/stochastic_adder.sv) | Scaled stochastic add `(A+B)/2` via MUX with its own select LFSR |
| [`stochastic_decorrelator`](blocks/stochastic/rtl/stochastic_decorrelator.sv) | In-stream decorrelator (clean-room CORLD-D, after Asadi et al.) |

Most blocks have a `_sync` variant with synchronous reset only, for fabric
flip-flops without an async reset input (see [ADR 0020](docs/adr/0020-synchronous-reset-variants-for-fabric-targets.md)).

### Common

| Name | Description |
|---|---|
| [`ma_assert.svh`](common/rtl/ma_assert.svh) | Elaboration-time checks (`MA_ASSERT_ELABOR`) and SVA macros; stubbed out for synthesis/Yosys |
| [`ma_axis_typedef.svh`](common/rtl/ma_axis_typedef.svh) | AXI-Stream struct typedef macros (in progress, see [ADR 0023](docs/adr/0023-struct-channel-macros-instead-of-sv-interfaces.md)) |
| [`base_tb.py`](common/verif/base_tb.py) | Protocol-agnostic cocotb testbench base |
| [`axis_tb.py`](common/verif/axis_tb.py) | AXI-Stream cocotb testbench support on top of `BaseTB` |
| [`ma_clkrst.py`](common/verif/ma_clkrst.py) | Shared cocotb clock/reset helpers |

## Getting Started

```sh
scripts/setup.sh              # install dependencies
pixi run setup-hooks          # once per clone: Python pre-commit hooks
pixi run run-regression       # run every cocotb testbench + helper unit tests
pixi run run-formal           # run every SymbiYosys proof
```

All tasks (`pixi task list` prints these descriptions from `pixi.toml`):

| Task | What it does |
|---|---|
| **Setup** | |
| `setup-sby` | One-time: build SymbiYosys from source into the pixi env (not on conda-forge). |
| `setup-bender` | One-time: install Bender into `~/.cargo/bin`. |
| `setup-hooks` | One-time per clone: install the Python pre-commit hooks (ruff, ty). |
| **RTL** | |
| `lint <file.sv>` | Verilator-lint one RTL file against the full Bender source list. |
| `lint-all` | Verilator-lint every RTL source in the default (synthesis) Bender file list. |
| **Simulation** | |
| `run-regression` | Every cocotb testbench plus the `common/verif` pytest unit tests. |
| `sweep-widths <tb-dir> <width>...` | One cocotb testbench at several `WIDTH` values. |
| **Formal** | |
| `run-formal` | Every SymbiYosys proof (`blocks/*/verif/formal/*/*.sby`). |
| `formal <file.sby>` | One SymbiYosys proof; output under `build/formal/`. |
| **Python** | |
| `lint-py` | Check Python: ruff lint, ruff format check, ty. Changes nothing. |
| `fix-py` | Auto-fix Python lint and formatting with ruff, then run ty. |
| **Docs** | |
| `render-waveform <file.json> [out.svg]` | Render a WaveDrom timing diagram to SVG. |

## Dependencies

- Toolchain: [pixi](https://pixi.prefix.dev/latest/) (Verilator, Yosys, SymbiYosys, z3, cocotb)
- RTL manifest: [Bender](https://github.com/pulp-platform/bender)

## Verification IP

`common/verif/sva/ma_axis_checker.sv` is the library's own AXI4-Stream protocol
checker (assertions and handshake covers), written from the AXI-Stream
specification (Arm IHI 0051B) and cross-referenced to the rule names in ARM's
public assertions user guide (ARM DUI 0534B, Table 4-10). It runs in the
open-source formal flow (Yosys `read_slang` + SymbiYosys) and attaches to a
block with `bind` from that block's `verif/formal/` directory, so design RTL
contains no verification code. See `blocks/basic/verif/formal/test_axis_fifo/`
for an example and `docs/adr/0025` for the design.

## AI-Assisted Development

This repo is developed with an AI-assisted workflow (Claude Code; project
instructions in `CLAUDE.md`). AI is used for:

- drafting documentation, ADRs, and helper scripts
- code review and bug hunting
- running and reporting verification across tools

RTL architecture and design decisions are my own.

Every change is held to the same bar regardless of who drafted it:

- it must pass lint
- it must pass the cocotb regression
- it must pass the formal proofs in CI
- significant decisions are recorded as ADRs in `docs/adr/` with the evidence that confirmed them

## License

TBD.
