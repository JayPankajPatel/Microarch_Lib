---
status: accepted
date: 2026-10-04
---

# 0025. Verification assertions live outside design RTL: an always-defined SVA macro header and reusable checkers in `common/`, attached to blocks by per-block `bind` files

## Context and Problem Statement

Two earlier decisions shaped where assertions live, and both rested on
constraints that no longer hold:

- **ADR 0009** put formal properties inline in the RTL under
  `` `ifdef FORMAL `` because Yosys's native frontend silently dropped
  `bind`-ed checkers and could not parse concurrent SVA. ADR 0024 moved the
  formal flow to `read_slang`, under which `bind` produces real, failing
  checks, and concurrent SVA does too -- but only with boolean property
  bodies plus `$past` (see Consequences and the correction on 0024).
- **ADR 0011** consolidated `` `MA_ASSUME_SVA ``/`` `MA_ASSERT_SVA ``/
  `` `MA_COVER_SVA `` into `common/rtl/ma_assert_std.svh`, behind
  `ma_assert.svh`'s tool dispatch, on the reasoning that callers would wrap
  every `_SVA` call in `` `ifdef FORMAL ``. But the dispatch includes
  `ma_assert_dummy.svh` *instead of* `ma_assert_std.svh` whenever
  `SYNTHESIS` or `YOSYS` is defined, and the dummy defines only
  `MA_ASSERT_ELABOR`. So the `_SVA` macros are undefined in **every** Yosys
  formal flow -- native (defines `YOSYS`) and slang (defines `SYNTHESIS`,
  ADR 0024). Measured with a module calling `` `MA_ASSERT_SVA `` inside
  `` `ifdef FORMAL ``:

  | Flow | Result |
  |---|---|
  | `read_verilog -sv -formal` | `ERROR: Unimplemented compiler directive or undefined macro` `` `MA_ASSERT_SVA `` |
  | `read_slang -D FORMAL` | `error: unknown macro or compiler directive` `` '`MA_ASSERT_SVA' `` |
  | Verilator `--lint-only -DFORMAL` | clean |

  It was never noticed because nothing in the repo calls the `_SVA` macros.

The AXI-Stream protocol checker (issue #8) is the first reusable checker:
one set of handshake/reset properties that must attach to every block with
a stream port (`delay_fx`, I2S RX/TX, async FIFO, ...) without editing any
of them.

## Decision Drivers

- Design RTL must not contain verification code; synthesizable sources and
  verification sources are separated by file list, not by `` `ifdef ``s.
- One checker, written once, attached to many blocks -- the same reuse goal
  as the ADR 0023 typedef macros.
- A missing verification piece must fail loudly, never PASS silently
  (ADR 0009's core lesson).
- Match standard DV practice: reusable protocol checkers are bound from
  outside; designer assertions about a block's own internals may stay
  inline.

## Considered Options

1. **Keep inline-per-block** (ADR 0009 style): each block hand-writes the
   AXIS properties inside its own `` `ifdef FORMAL ``.
2. **Keep the `_SVA` macros in `ma_assert.svh`'s dispatch**, but change the
   condition so they survive formal (e.g. dispatch on `FORMAL` instead of
   `SYNTHESIS`/`YOSYS`).
3. **Separate verification layer**: `_SVA` macros in their own
   always-defined header; reusable checkers (VIP) in `common/`; each block
   attaches them with a small `bind` file under its `verif/formal/`.

## Decision Outcome

Chosen option: **3, separate verification layer**, because it keeps RTL
free of verification code and lets one checker serve every block, now that
ADR 0024 makes `bind` reliable.

- **1** copies the same five AXIS properties into every block -- the reuse
  problem ADR 0023 exists to avoid -- and puts verification code in design
  files.
- **2** keeps a synthesis-oriented switch deciding whether verification
  macros exist. Under slang, formal runs *with* `SYNTHESIS` defined, so any
  condition built on "strip in synthesis" is ambiguous in exactly the flow
  that needs the macros. Checker and bind files are never in a synthesis
  file list, so they need no such switch at all.

### Consequences

- **SVA macros move to their own header**,
  `common/rtl/ma_sva.svh`, include-guarded, no tool dispatch, always
  defined. Only checker and bind files include it. Names stay as ADR 0011
  set them (`MA_<KIND>_SVA`).
- **`MA_ASSERT_ELABOR` is unchanged**: it stays in `ma_assert.svh` /
  `ma_assert_std.svh` / `ma_assert_dummy.svh` with its existing dispatch,
  because it sits on the synthesizable path where that dispatch makes sense.
- **Reusable checkers (VIP) live in `common/verif/sva/`**, e.g. `ma_axis_checker`, parameterized by type and
  told which side of the channel the bound block is on, so the same
  property is an `assert` where the block drives the signal and an
  `assume` where its environment does.
- **Per-block bind files** (`blocks/<name>/verif/formal/test_<name>/<name>_bind.sv`,
  next to the block's `.sby`)
  hold only wiring: one `bind` line per port, plus the environment
  assumption that every trace starts in reset (`f_past_valid` pattern,
  ADR 0024). That assumption is the `` `MA_ASSUME_RESET_AT_START(clk,
  rst_asserted) `` macro in `ma_sva.svh` (added 2026-10-05), usable both in
  bind files and inline under `` `ifdef FORMAL ``; it also declares
  `ma_f_past_valid` for `$past` guards. The checker states protocol rules only; the reset-at-cycle-0
  assumption belongs to the environment, not the protocol.
- **Verification-only files are kept out of synthesis by the Bender
  `formal` target**, not by `` `ifdef ``. `lint-all` uses the default file
  list, so it does not lint checkers or bind files; lint them explicitly
  (`verilator --lint-only -Wall ... --top-module <block>` with the bind file).
- **Rules that must check during reset** (e.g. TVALID low during and just
  after reset) are written without `disable iff`, or by passing `1'b0` as
  the macro's reset argument.
- **Risk: a missing bind file is silent.** `bind` inverts the dependency
  (the design never names the checker), so leaving the bind file off a
  `.sby` or testbench file list removes the checker with no error. The
  existing `select -assert-min 1 t:$check` guard (ADR 0024) does not catch
  this when the block has other checks. Mitigation: each `.sby` also asserts
  the exact number of `$check` cells inside each checker instance, by name
  (see the naming convention below). Verified to ERROR when the bind file
  is omitted.
- **Property bodies are limited to booleans plus `$past`.** Yosys's slang
  frontend rejects `|->`, `|=>`, `##N`, sequences and `$stable` (see the
  correction on ADR 0024). Checkers write each rule as its boolean
  equivalent, with two translation rules that are easy to get wrong:
  - `a |-> ##1 b` with `disable iff (!rst_n)` becomes
    `!$past(rst_n && a) || b`. The `rst_n` inside `$past` reproduces
    `disable iff`'s cancellation of an attempt that started during reset;
    without it the check looks back into a reset cycle, where sync-reset
    state is undefined, and fails on a correct DUT (observed on
    `axis_fifo`).
  - `$stable(x)` becomes `x == $past(x)`.
  - A rule with no `disable iff` is evaluated at step 0, where `$past` has
    no history and its value is unconstrained; such a rule must not depend
    on `$past` at step 0, or must be gated with an `f_past_valid` flag.
- **Bind instance naming convention:** `u_<port>_chk`, so the `.sby`
  guard can count `$check` cells per instance by name
  (`select -assert-count N t:$check */u_<port>_chk.* %i`). slang flattens
  the hierarchy into the top module and keeps hierarchical cell names such
  as `u_m_axis_chk.g_tx_rules.stable_tvalid_check`.
- **Designer assertions may stay inline.** `galois_lfsr`'s `no_lockup` is a
  one-block internal property, conventionally inline; it is not migrated.
  This ADR governs reusable/protocol checkers and any new formal setup.

- **Reset rule follows ARM's checker.** The rule was first written as
  "TVALID low in every reset cycle and the first cycle after release". That
  is stricter than ARM's own AXI4-Stream checker: ARM DUI 0534B Table 4-10,
  `AXI4STREAM_ERRM_TVALID_RESET`, checks only "TVALID is LOW for the first
  cycle after ARESETn goes HIGH". The strict form also FAILs on correct
  sync-reset blocks (`axis_fifo`: TVALID comes from a register with no
  initial value, so it is undefined in the first reset cycle, before the
  reset edge). Decided 2026-10-04 by the owner: follow ARM. The checker's
  rule is `tvalid_low_first_cycle_after_reset`,
  `(rst_n && !$past(rst_n)) |-> !tvalid`, gated at step 0 with
  `f_past_valid`.

### Confirmation

Done (2026-10-04):

- The `_SVA` macros are undefined in both Yosys formal flows and defined in
  Verilator (table above).
- `bind` under `read_slang` produces a real, failing check (ADR 0024
  Confirmation, toy design), now also on a real block (below).

Checker bound to `axis_fifo` (flat ports; one-entry register slice, sync
active-high reset), `smtbmc z3`, depth 20, run 2026-10-04:

| Run | Result |
|---|---|
| macro move: `lint-all` / `run-formal` / `run-regression` | unchanged: exit 0 / `galois_lfsr` PASS / 33 of 33 |
| elaboration | 17 `$check` cells: 3 rules + 5 covers per checker, plus the env assume |
| `cover` task | all 10 covers reached (5 per side), steps 3-5 |
| `prove`, original strict reset rule | FAIL: `u_m_axis_chk.g_tx_rules.tvalid_low_during_and_after_reset` at step 0 (trace: `rst`=1, `m_axis_tvalid`=1 from the uninitialized `r.full`) -- led to the ARM-aligned rule |
| `prove`, final checker (ARM-aligned reset rule) | PASS |
| mutation: data changes while stalled | FAIL on `stable_data_check_tvalid_before_ready` only |
| mutation: tvalid drops while stalled | FAIL on `stable_tvalid_check` only |
| mutation: tvalid high on the first edge after reset | FAIL on `tvalid_low_first_cycle_after_reset` only |
| `run-formal` after all changes | `axis_fifo.sby` PASS (prove + cover), `galois_lfsr.sby` PASS |
| bind file omitted from the read | ERROR: `selection contains 0 elements instead of the asserted 8` |
| Bender | default `flist-plus` lists neither checker nor bind file; `-t formal` lists both |
| Verilator `--lint-only -Wall` (block + checker + bind) | clean (formal-idiom `PROCASSINIT` suppressed locally in the bind file) |
| `run-regression` after all changes | 10 testbenches, 33 of 33 |

Mutation and PASS rows were run against the final checker in the repo, not a scratch copy.

## Affected Files

- `common/rtl/ma_sva.svh` (new: `MA_ASSUME_SVA`/`MA_ASSERT_SVA`/`MA_COVER_SVA`)
- `common/rtl/ma_assert_std.svh` (`_SVA` macros removed)
- `common/verif/sva/ma_axis_checker.sv` (new)
- `blocks/basic/verif/formal/test_axis_fifo/axis_fifo_bind.sv` (new)
- `blocks/basic/verif/formal/test_axis_fifo/axis_fifo.sby` (new; joins `run-formal`)
- `Bender.yml` (`formal` target)
- `docs/adr/0011-ma-macro-naming-elabor-vs-sva.md` (status note)
- `docs/adr/0024-formal-frontend-read-slang.md` (correction note)

## More Information

- Supersedes in part [0011](0011-ma-macro-naming-elabor-vs-sva.md): the
  location of the `_SVA` macros and the claim that wrapping calls in
  `` `ifdef FORMAL `` is sufficient. 0011's naming convention stands.
- Builds on [0024](0024-formal-frontend-read-slang.md) (`bind` works under
  slang; concurrent SVA only with boolean bodies plus `$past`), which already superseded
  [0009](0009-formal-checker-inline-not-bind.md)'s native-frontend limits.
- ARM's own AXI4-Stream checker (`Axi4StreamPC.sv`, BP063 r0p1) was read to
  confirm the rule semantics: its `AXI4STREAM_ERRM_TVALID_RESET` checks only
  the first edge after reset release, and its stability rules qualify both
  cycles with `ARESETn` explicitly (no `disable iff`), the same shape as this
  checker's `$past(rst_n && ...)` form. ARM's code was read only after this
  checker was written, to confirm semantics; none of it is copied here, and
  the library has no dependency on it (ARM's licence forbids
  redistribution).
- Related: [0023](0023-struct-channel-macros-instead-of-sv-interfaces.md)
  (the AXIS types the first checker is written against).
