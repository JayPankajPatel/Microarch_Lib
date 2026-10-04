---
status: accepted
date: 2026-10-04
---

# 0024. Formal flow reads RTL through Yosys's built-in slang frontend (`read_slang -D FORMAL`), not the native `read_verilog -sv -formal`

## Context and Problem Statement

ADR 0023 makes leaf blocks take their port types as `parameter type req_t` /
`parameter type resp_t`. Yosys's native SystemVerilog frontend cannot parse
that at all:

```
tiny.sv:1: ERROR: syntax error, unexpected TOK_ID, expecting ')' or ',' or '='
```

for a module whose only unusual feature is `parameter type T = logic`
(Yosys 0.67, `read_verilog -sv`). Structs, packages and the
`MA_AXIS_*` typedef macros parse fine natively; type parameters are the
blocker. Because it is a parse error, a concrete wrapper around the leaf
does not help -- the leaf source itself cannot be read.

Yosys 0.67 (already pinned in `pixi.toml`, `yosys = ">=0.67,<0.68"`) ships
the slang-based SystemVerilog frontend (formerly the `yosys-slang` plugin,
now "sv-elab") built in as `read_slang`. No new toolchain dependency is
needed.

ADR 0009's two native-frontend findings -- a `bind`-ed checker is silently
dropped (hollow PASS), and `assert property (@(posedge clk) ...)` does not
parse -- were the reason formal properties are written as inline immediate
assertions. Whether those constraints still hold under slang needed
re-checking.

## Decision Drivers

- ADR 0023's convention must be checkable by the formal flow, or formal
  silently stops covering every block converted to struct ports.
- A formal run that checks nothing must never report PASS (ADR 0009's
  core lesson).
- CLAUDE.md: tapeout-bound, prefer proven patterns -- so a frontend switch
  needs the same evidence standard as ADR 0009 (a deliberately false
  property must FAIL), not just "it parses."

## Considered Options

1. **`read_slang` (built into Yosys 0.67) for formal.**
2. **`sv2v` pre-pass**, then the native frontend.
3. **Change the leaf convention** (widths, or direct package import, instead
   of `parameter type`) so the native frontend can read it.

## Decision Outcome

Chosen option: **1, `read_slang -D FORMAL`**, because it parses the ADR 0023
convention with no extra tool, and every false property tested produced a
real counterexample (see Confirmation).

- 2 (`sv2v`): not installed in the pixi env and not on conda-forge
  (`pixi search sv2v`: no packages found), so it would need a from-source
  setup task like `setup-sby`; adds a translation step whose output is what actually gets
  proven, so a translation bug would be invisible.
- 3 (change the convention): gives up type-parameterized testbenches (one
  DUT instantiated at several data types in one sim), which was a stated
  reason for ADR 0023, to work around one tool's parser.

### Consequences

Behavioural differences from `read_verilog -sv -formal` that every `.sby`
must account for:

| | `read_verilog -sv -formal` | `read_slang` |
|---|---|---|
| Predefines `FORMAL` | yes | **no -- pass `-D FORMAL`** |
| Predefines `YOSYS` | yes | no |
| Predefines `SYNTHESIS` | no | **yes** |
| Parameter override | `chparam` after read | `-G NAME=VAL` on the read line; `chparam` afterwards errors (`is used with parameters but is not parametric`) |
| `initial assume (...)` | accepted | **rejected**: `reading net state during design initialization unsupported` |
| Async reset flop cell | `$adff` | `$aldff` |

- **Missing `-D FORMAL` would silently drop every inline formal block.**
  Mitigation: every `.sby` runs `select -assert-min 1 t:$check` after
  `prep`. Verified: without `-D FORMAL` this errors
  (`selection contains 0 elements, less than the minimum number 1: t:$check`).
- **Reset-at-step-0 assumption pattern changes** from `initial assume
  (!rst_n);` to a first-cycle flag:
  ```systemverilog
  logic f_past_valid = 1'b0;
  always @(posedge clk) f_past_valid <= 1'b1;
  always @(posedge clk) if (!f_past_valid) assume (!rst_n);
  ```
  `galois_lfsr.sv` and `galois_lfsr_sync.sv` were migrated.
- **`MA_ASSERT_ELABOR` behaviour in formal is unchanged.** Under slang
  `SYNTHESIS` is defined, so `ma_assert.svh` dispatches to the dummy
  header -- the same outcome as before, when the native frontend reached it
  via `YOSYS`. `ma_assert.svh` is deliberately left as-is; whether the
  real bodies now work under slang is a separate question.
- **ADR 0009's constraints are superseded for the slang flow**: `bind` and
  concurrent SVA both produce real, failing checks (Confirmation). This ADR
  does not choose a checker style; that is left to the AXI-Stream protocol
  checker work (issue #8).
- ADR 0008's `TAPS_LUT` constant-function encoding (a native-frontend
  workaround) still works under slang (`galois_lfsr` proves), so it stays.
  Whether slang would accept the original `localparam` array encoding was
  not tested.
- Residual risk: slang is the newer frontend. Only `galois_lfsr` (in the
  formal suite) and `galois_lfsr_sync` (ad hoc) have been proven under it.

### Confirmation

All runs: Yosys 0.67 (`slang revision 809d2da5`), SymbiYosys from the pixi
env, `smtbmc z3`. CI (`.github/workflows/nightly.yml`) installs from `pixi.lock`,
which locks `yosys-0.67`, so `read_slang` is available there too.

**Toy design** (the real `common/rtl/ma_axis_typedef.svh`, a package calling
`` `MA_AXIS_ALL(audio, logic signed [15:0]) ``, a leaf with
`parameter type req_t/resp_t` overridden from a top), `mode bmc`, depth 12:

| Case | Result |
|---|---|
| true inline immediate assert | PASS |
| false inline immediate assert | FAIL (`u_leaf.g1.inl_bad`) |
| true assert in a normally-instantiated checker submodule taking `parameter type req_t` | PASS |
| false assert in that submodule | FAIL (`u_leaf.g3.u_chk.sub_bad`) |
| false concurrent SVA `assert property (@(posedge clk) disable iff (!rst_n) ...)` | FAIL (`u_leaf.g4.sva_bad`) |
| false assert in a `bind`-ed checker | FAIL (`u_leaf.u_bind.bind_bad`) |

**`galois_lfsr.sby`** (in the suite), `mode prove`, depth 20:

| Task | Real property | Negated (`out == '0`, scratch copy) | LFSR flop |
|---|---|---|---|
| w4 | PASS | FAIL | `$aldff_4` |
| w16 (`INIT_SEED=69`) | PASS | FAIL | `$aldff_16` |
| w64 (`INIT_SEED=1`) | PASS | FAIL | `$aldff_64` |

The flop widths confirm the `-G` overrides take effect (three distinct
elaborations, not three runs at the default width). `$check` count is 2 per
task (the reset assume + `no_lockup`), same as the native baseline.

**`galois_lfsr_sync`** (no `.sby` in the repo; checked with a scratch `.sby`
mirroring the one above): PASS on w4/w16/w64 with the real property, FAIL
on all three with the negated one. Native baseline (original `initial
assume`) also PASS. It is not part of `pixi run run-formal`.

**Regression**, before vs. after the change (2026-10-04):

| Check | Before | After |
|---|---|---|
| `pixi run lint-all` | exit 0 | exit 0 |
| `pixi run run-formal` | `galois_lfsr.sby` PASS (native) | PASS on w4/w16/w64 (slang), 2 `$check` each |
| Mutation via the edited `.sby` script against negated RTL | -- | FAIL on w4/w16/w64 |
| `pixi run run-regression` | 10 testbenches, 33/33 pass | 10 testbenches, 33/33 pass |

`lint-all` and `run-regression` do not define `FORMAL`, so they cannot
exercise the changed blocks' formal code; they are a no-regression check
on the RTL only.

## Affected Files

- `blocks/stochastic/verif/formal/test_galois_lfsr/galois_lfsr.sby`
  (`read_slang -D FORMAL`, `-G` per task, `select -assert-min 1 t:$check`)
- `blocks/stochastic/rtl/galois_lfsr.sv`,
  `blocks/stochastic/rtl/galois_lfsr_sync.sv` (`initial assume` replaced
  with the `f_past_valid` pattern; stale bind comment replaced with a
  pointer here)
- `docs/adr/0009-formal-checker-inline-not-bind.md` (status note)
- `docs/adr/0023-struct-channel-macros-instead-of-sv-interfaces.md`
  (Yosys claim corrected)
- `CLAUDE.md` (formal layout pointer)

## More Information

- Supersedes, for the slang flow, the native-frontend constraints recorded
  in [0009](0009-formal-checker-inline-not-bind.md).
- Enables [0023](0023-struct-channel-macros-instead-of-sv-interfaces.md)
  in the formal flow.
- Open follow-ups: add a `.sby` for `galois_lfsr_sync` so it is in the
  suite; decide whether `ma_assert.svh` should use real
  `MA_ASSERT_ELABOR` bodies under slang.
