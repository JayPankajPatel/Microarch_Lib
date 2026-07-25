---
status: accepted
date: 2026-07-25
---

# 0001. Elaboration-time parameter checks use the bare `$error` form, not an `initial`+`assert` macro

## Context and Problem Statement

Every block in this library needs a reusable way to validate elaboration-time
parameters (e.g. `galois_lfsr`'s `WIDTH` must be in `[2:64]`) and abort
elaboration with a clear message if a bad value is used, before any
simulation or synthesis proceeds. The check needs to work consistently
across VCS, Xcelium, Verilator, and (eventually) Yosys, and be reusable by
every block without hand-rolling the check each time.

## Decision Drivers

- Must be correct and safe by construction — a silently-skipped check on a
  tapeout-bound library is a real liability, not just an inconvenience.
- Must actually work across the tool stack this library targets, not just
  the tool happening to be open at the time.
- Prefer the simplest mechanism that satisfies the above, not the most
  "clever" one.

## Considered Options

1. SVA concurrent assertions (`assert property (@(posedge clk) ...)`)
2. The `checker`/`endchecker` construct (IEEE 1800 Clause 17)
3. OpenTitan's `` `ASSERT_INIT `` macro pattern (`initial` block + immediate
   assertion + `$error`)
4. Bare `$error` as an elaboration system task (IEEE 1800-2017 §20.11),
   called directly via a conditional-generate `if`, no `initial` block

## Decision Outcome

Chosen option: **4, bare `$error` via conditional-generate**, implemented as
a `` `MA_ASSERT_INIT `` macro in `common/rtl/ma_assert_std.svh`:

```systemverilog
`define MA_ASSERT_INIT(__name, __prop) \
  if (!(__prop)) \
    $error("%s:%0d: [%s] check failed", `__FILE__, `__LINE__, `MA_STRINGIFY(__name));
```

- **Option 1 (SVA)** was rejected first: `assert property` is a temporal
  construct requiring a clock edge to ever evaluate. A constant parameter
  has no clock relationship, so wrapping a parameter check in
  `@(posedge clk)` is semantically wrong, not just stylistically unusual.
- **Option 2 (`checker`)** is the LRM's own first-class construct for this
  (Clause 17, not bolted onto SVA), but tool support disqualifies it today:
  Verilator only merged basic `checker` support in April 2025
  (github.com/verilator/verilator#4066, closed as "completed" with "very
  basic functionality"), and Yosys's own documentation states it only
  supports "checkers without a port list that do not need to be
  instantiated" — the parameterized, instantiable form this library would
  need is unsupported there.
- **Option 3 (OpenTitan's `` `ASSERT_INIT ``)** is real, taped-out-silicon
  precedent, but it wraps the check in an `initial` block with an immediate
  assertion. OpenTitan hit a real bug from exactly this shape:
  github.com/lowRISC/opentitan#9017, "ASSERT_INIT doesn't work for
  Xcelium" — a genuine IEEE 1800 §4.8 race condition between the `initial`
  block's immediate assertion and a competing continuous assignment
  settling at time 0, present on Xcelium but not VCS, fixed with a `#0`/
  `#1ps` delay. The thread confirms this only bites checks that read an
  actual signal/net value, not pure parameter-vs-parameter or
  parameter-vs-constant checks — but since option 4 sidesteps the whole bug
  class structurally (see below), there's no reason to accept even that
  narrower risk.
- **Option 4 (chosen)** is the LRM's own canonical form for this exact use
  case — IEEE 1800-2017 §20.11's worked Example 1 is a module-parameter
  range check using precisely this shape, no `initial` block, no
  `generate`/`endgenerate` wrapper needed at module scope. Because it never
  touches an `initial` block or reads a signal — it only ever compares
  elaboration-time constants — it is structurally immune to the
  OpenTitan#9017 race-condition class, not just narrowly outside its
  observed trigger conditions.

Tool dispatch (`common/rtl/ma_assert.svh`) routes to
`common/rtl/ma_assert_dummy.svh` (no-op macro bodies, same names) under
`` `ifdef SYNTHESIS `` and `` `ifdef YOSYS ``, and to
`common/rtl/ma_assert_std.svh` (the real macro above) otherwise:

- `SYNTHESIS` is stripped by design — these checks produce no synthesizable
  logic and serve no purpose once parameters are validated in simulation;
  feeding them into synthesis is at best wasted work.
- `YOSYS` is stripped conservatively — not because the bare `$error` form is
  known to fail there, but because it hasn't been verified there (Yosys
  wasn't installed at the time this decision was made). Revisit once
  verified; the initial assumption that Verilator also needed this
  treatment was tested and found unnecessary (see Confirmation below), so
  the same may turn out to be true for Yosys.

### Consequences

- Every block includes one header (`` `include "ma_assert.svh" ``) and calls
  one macro per check, instead of hand-rolling `` `ifdef ``/`` `initial ``
  logic per block.
- The mechanism is simpler than OpenTitan's own pattern (no `initial`
  block, no assertion statement, no `#0`/`#1ps` defensive delay needed) —
  not a compromise made for simplicity's sake, but a direct consequence of
  matching the LRM's own recommended form.
- `YOSYS` dispatch is conservative pending verification; this should be
  revisited once Yosys is available to test against (see ADR 0003 for
  toolchain status).

### Confirmation

Verified empirically, not just by reading the LRM: the LRM's Example 1 form
was compiled and run through Verilator 4.038 (no special flags) with both a
deliberately out-of-range parameter (correctly aborted with
`%Warning-USERERROR` pointing at the exact line/instance, nonzero exit) and
an in-range one (clean pass, exit 0). The same result was reproduced later
via the pixi-installed Verilator 5.050. This directly falsified the
original assumption that Verilator needed the same dummy-macro fallback as
`SYNTHESIS`/`YOSYS` for this construct — that branch was narrowed
accordingly.

## Affected Files

- `common/rtl/ma_assert.svh`
- `common/rtl/ma_assert_std.svh`
- `common/rtl/ma_assert_dummy.svh`
- `blocks/stocastic/rtl/galois_lfsr.sv` (first consumer)

## More Information

- IEEE Std 1800-2017, §20.11 "Elaboration system tasks" and its Example 1.
- github.com/lowRISC/opentitan#9017
- github.com/verilator/verilator#4066
