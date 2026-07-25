---
status: accepted
date: 2026-07-25
---

# 0003. Use pixi for a reproducible, cross-platform verification toolchain

## Context and Problem Statement

This library needs Verilator (lint/simulation), Yosys and SymbiYosys
(formal verification), and a SAT/SMT solver (z3) available reproducibly on
any machine that clones this repo, rather than assuming these are
pre-installed. Nothing was installed locally at the point this decision
was made.

## Considered Options

1. Assume tools are manually installed on each machine's `PATH`.
2. YosysHQ's OSS CAD Suite prebuilt binary bundle (Yosys, SymbiYosys, and
   solvers bundled together).
3. Build everything from source.
4. `pixi` (a conda-forge-based project environment/package manager).

## Decision Outcome

Chosen option: **4, pixi**, declared in `pixi.toml`:

```toml
[dependencies]
verilator = ">=5.50,<6"
yosys = ">=0.67,<0.68"
click = ">=8.4.2,<9"
libz3 = ">=4.16.0,<5"
```

- **Option 1** was rejected outright — not reproducible or shareable across
  machines or collaborators.
- **Option 2 (OSS CAD Suite)** would have worked but wasn't chosen — it has
  no built-in dependency versioning/management the way a `pixi.toml`
  manifest does, and pixi's `conda-forge` packages already covered
  `verilator`, `yosys`, and `libz3` (which, despite the name, bundles the
  actual `z3` CLI binary at `bin/z3`, not just the library) directly.
- **Option 3** was rejected as the slowest path with the most build
  dependencies to manage.

SymbiYosys (`sby`) itself is **not** on conda-forge. It's built from source
via a `pixi` task that clones `github.com/YosysHQ/sby` and runs its
`make install PREFIX=$CONDA_PREFIX`, landing `sby` directly in the pixi
environment's `bin/` alongside the conda-forge packages.

### Consequences

- Declared platforms are `linux-64` and `osx-64` only. Adding
  `osx-arm64` (native Apple Silicon) and `linux-aarch64` was attempted and
  failed to resolve — confirmed via conda-forge's own `channeldata.json`
  that the `yosys` feedstock has no builds for either platform. This is an
  upstream packaging gap, not something fixable from this repo. Apple
  Silicon users need Rosetta 2 to run the `osx-64` build, or would need to
  build Yosys from source themselves.
- Fresh-clone setup is two steps: `pixi install` (gets
  verilator/yosys/z3/click), then `pixi run setup-sby` (one-time, builds
  `sby` from source into the environment).

### Confirmation

The full pipeline was verified end-to-end, not just installed: a minimal
`counter.sv` + `.sby` file was run through `pixi run sby -f counter.sby`,
exercising the real chain (`yosys` read/prep/smt2 generation ->
`yosys-smtbmc -s z3` -> an actual BMC run against `z3`), producing a real
counterexample trace (VCD + Verilog testbench + Yosys witness file) when
the trivial example's unconstrained-reset assumption was, correctly,
violated. This confirms the toolchain executes real formal verification,
not just that the binaries exist on `PATH`.

## Affected Files

- `pixi.toml`
- `pixi.lock`

## More Information

None.
