---
status: Proposed
date: 2026-09-28
---

# 0023. Use valid/ready channel typedef macros for struct-based ports instead of SV interfaces

## Context and Problem Statement

When passing interfaces into synthesis toolchains, the support for interfaces is varied and weak amongst the different vendors. 

  - Vivado and slang both rejected axis_intf#(.DATA_WIDTH(...)).slave in a port list. You can't set an interface's parameters at the port (it's not legal SV).
  - IP Integrator module references can't use SV interface ports, which forced a flat wrapper.
  - Standalone lint fell back to the interface's default DATA_WIDTH = 32, producing a spurious 32→16 truncation warning, with nothing enforcing the width match.
  - A typedef inside an interface couldn't be used directly as a type, which needed the typedef s_axis.axis_payload_t workaround.
  - Open-source Yosys (the current formal flow) has limited interface support. Known from documentation and reputation rather than a failure I saw.
  - cocotb can't drive a top level with interface ports on Verilator or Icarus.

## Decision Drivers

- Reusability is a must when doing RTL, project deadlines, my personal learning and personal time are being eaten by rewriting modules. 
- Verification needs to be done every time as new wrapper RTL is written and must be tested. 
- Tool support for interfaces is limited and open source tooling, likely to support the least amount of features, has to have a seamless development process to save time and verification effort. 
- Width mismatches for connected modules must be caught early during elaboration and must have an explicit error, rather than having a silent warning that can easily be ignored inside the affected module.

## Considered Options

1. **Keep SV interfaces** and accept tool limitations
2. **Keep SV interfaces** and create a thin wrapper when synthesizing 
3. **Flat port lists only** (no bundling)
4. **Structs built from a valid/ready channel typedef macro, with type parameters.**; AMBA protocols are based on a single channel AXI-Stream, later, these macros can be extended to fit AXI and ACE protocols

## Decision Outcome
**Choose Option 4**; struct macros with type parameters

The reasoning is that the width of the channel is bound once at the top level where 
integration is happening. Structs are supported by every major simulation and synthesis tool that I have used or plan on using on the open source side. This includes 
- Vivado,
- IPI via a mechanical wrapper,
- Verilator,
- Yosys, via its built-in slang frontend (`read_slang`). The native `read_verilog -sv` frontend parses structs and packages but rejects `parameter type`; see [0024](0024-formal-frontend-read-slang.md).
- cocotb

The channel abstraction also makes supporting AXI and ACE protocols easier by allowing a composition design pattern to reuse our work. 

- 1 (interfaces as-is): illegal port-level parameterization; fails in IPI, open-source lint, Yosys and cocotb.
- 2 (interfaces + wrappers): a non-reusable, handwritten, unverified wrapper per module, kept in sync by hand.
- 3 (flat ports only): 7+ signals per stream per module, no single place defining widths, and connections written signal by signal.

### Consequences

#### Positives
  - Reuse if AXI4 or ACE are implemented later, via composition of the channel macro.
  - Widths are bound once at the integrating top and shared as a single type, so
    mismatches between blocks are prevented rather than silently defaulted. Where
    different types must meet, `MA_ASSERT_ELABOR($bits(...))` checks give an explicit
    elaboration error.
  - No new hand-written code to verify from wrappers. The IPI boundary is the exception,
    but those wrappers are cookie-cutter: a macro, template, or script produces them
    deterministically, with no hand-written logic to verify

#### Negatives 
  - The obvious one: this is much more up-front work than continuing as-is. Amortized over future blocks, the cost may or may not be negligible for my small personal projects.
  - **Not standardized**, because there is no real standard to do this, it might be harder to import or use with external dependencies. Mitigation: stay close to the de facto `pulp-platform/axi` `req_t`/`resp_t` convention.
  - Macros are harder to read and debug. Errors inside a macro expansion point at confusing line numbers, and you can't easily see the expanded code.
  - Standalone lint breaks with logic default types. Linting a module on its own hits s_req_i.tvalid on a type with no fields, so every block needs a small lint or test top that expands the
    macro.
  - Packed-struct width mismatches are legal SV. Connecting two struct types of different widths silently truncates, so critical connections need $bits elaboration checks.
  - IPI still needs a flat wrapper at the block-design boundary, though it's mechanical via an assign macro.
  - cocotb sees packed structs as plain bit vectors, so Python tests need field-slicing helpers that match the struct layout.
  - No modports: direction checking comes from the req/resp split rather than from the tool enforcing modport directions.
### Confirmation

TODO: fill in after the `delay_fx` struct conversion. Required evidence: the
converted module elaborates in Verilator, Vivado, and Yosys, and regression
output matches the interface-based version cycle for cycle. Planned as a
`pixi run check-tools` task.

Partial (2026-10-04), toy design only -- the real `ma_axis_typedef.svh`, a
package calling `` `MA_AXIS_ALL(audio, logic signed [15:0]) ``, and a leaf
with `parameter type req_t/resp_t` overridden from a top:
- Verilator 5.052 `--lint-only -Wall`: clean.
- Yosys 0.67 native `read_verilog -sv`: parse error on `parameter type`
  (`syntax error, unexpected TOK_ID`).
- Yosys 0.67 `read_slang`: elaborates; under sby, false assertions inline,
  in a checker submodule, as concurrent SVA, and via `bind` all FAIL with
  real counterexamples. Details in [0024](0024-formal-frontend-read-slang.md).
- Vivado and the `delay_fx` cycle-for-cycle comparison: not yet done.

## Affected Files

- `common/rtl/ma_axis_typedef.svh` (new, in progress)
- TODO: `delay_fx` and the stochastic blocks once converted

## More Information

- Spec: Arm IHI 0051B (AXI-Stream); see
  `docs/design-specs/axi-stream-conventions.md`.
- Reference: `pulp-platform/axi` `include/axi/typedef.svh` (Solderpad license).
- AXI4 and ACE, when needed, are planned to come from `pulp-platform/axi` as a
  Bender dependency rather than being reimplemented here.
