# ADR Retroactive Entries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `docs/adr/` Architecture Decision Record system for Microarch_Lib: an index page plus three retroactive ADRs capturing decisions already made this session (elaboration-check mechanism, `TAPS_LUT` correctness methodology, pixi toolchain choice).

**Architecture:** Four new markdown files under `docs/adr/`. No code, no build step — these are documentation artifacts. Each ADR follows the MADR-based template from `docs/design-specs/2026-07-25-adr-system-design.md`. "Testing" here means structural verification (required sections present) and factual verification (cited file paths and external facts actually check out against the repo/session record), not unit tests.

**Tech Stack:** Markdown, git.

## Global Constraints

- Template per `docs/design-specs/2026-07-25-adr-system-design.md`: YAML front matter (`status`, `date`) + `# NNNN. Title` + `## Context and Problem Statement` + `## Decision Drivers` (optional) + `## Considered Options` + `## Decision Outcome` (with `### Consequences` and `### Confirmation` subsections) + `## Affected Files` + `## More Information` (optional).
- File naming: `docs/adr/NNNN-<slug>.md`, four-digit zero-padded number.
- No `decision-makers`/`consulted`/`informed` fields (excluded per the spec — team-governance fields not needed at this project's scale).
- All facts cited in these ADRs (IEEE clause numbers, GitHub issue numbers, conda-forge platform support, empirical test results) were already verified during this session — write them down accurately, do not re-derive or soften them into vague claims.

---

## File Structure

- Create: `docs/adr/0001-elaboration-check-mechanism.md`
- Create: `docs/adr/0002-taps-lut-correctness-methodology.md`
- Create: `docs/adr/0003-pixi-toolchain.md`
- Create: `docs/adr/README.md` (index — written last since it references the final filenames/titles of the other three)

---

### Task 1: ADR 0001 — Elaboration check mechanism

**Files:**
- Create: `docs/adr/0001-elaboration-check-mechanism.md`

**Interfaces:**
- Consumes: nothing (first ADR).
- Produces: nothing other tasks depend on structurally, but Task 4 (README index) will reference this file's exact title and number.

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0001-elaboration-check-mechanism.md` with exactly this content:

```markdown
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
```

- [ ] **Step 2: Verify required sections are present**

Run: `grep -c '^## ' docs/adr/0001-elaboration-check-mechanism.md`
Expected: `6` (Context and Problem Statement, Decision Drivers, Considered
Options, Decision Outcome, Affected Files, More Information — verified
against the actual file's heading count).

- [ ] **Step 3: Verify cited file paths actually exist**

Run: `ls common/rtl/ma_assert.svh common/rtl/ma_assert_std.svh common/rtl/ma_assert_dummy.svh blocks/stocastic/rtl/galois_lfsr.sv`
Expected: all four paths listed with no "No such file" errors.

- [ ] **Step 4: Commit**

```bash
git add docs/adr/0001-elaboration-check-mechanism.md
git commit -m "docs: add ADR 0001 (elaboration check mechanism)"
```

---

### Task 2: ADR 0002 — TAPS_LUT correctness methodology

**Files:**
- Create: `docs/adr/0002-taps-lut-correctness-methodology.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks depend on structurally; Task 4 references this file's title/number.

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0002-taps-lut-correctness-methodology.md` with exactly this content:

```markdown
---
status: accepted
date: 2026-07-25
---

# 0002. `TAPS_LUT` correctness is established by algebraic primitivity checking, not by trusting the source table

## Context and Problem Statement

`galois_lfsr.sv`'s `TAPS_LUT` is a 65-entry table (indices 0-64, one entry
per supported `WIDTH`) of 64-bit tap-mask constants used to build a
parameterized Galois LFSR. A wrong entry doesn't cause a compile error, a
lint warning, or even a functional simulation failure in the ordinary
sense — it just produces an LFSR whose output cycle is shorter than the
maximal `2^WIDTH - 1`, which is silently wrong unless someone specifically
checks the cycle length. This is exactly the kind of bug that matters more
heading toward tapeout than in an FPGA iteration loop, where it would be
caught eventually.

## Decision Drivers

- The check needs to cover the full supported range, `WIDTH` 2 through 64 —
  spot-checking a handful of widths and assuming the rest are fine is not
  good enough once one spot-check already turned up a wrong entry.
- Brute-force simulating every possible state is only tractable for small
  widths; `2^64` states cannot be enumerated.

## Considered Options

1. Trust the original table as received, no verification.
2. Brute-force simulate the LFSR for each width and count unique states
   until a repeat, comparing against the expected `2^WIDTH - 1`.
3. Algebraic primitivity check: represent one LFSR step as a `WIDTH x WIDTH`
   matrix `M` over GF(2), and test whether `M`'s multiplicative order is
   exactly `2^WIDTH - 1` (i.e. `M` is primitive) via matrix exponentiation
   by repeated squaring, checking `M^(2^WIDTH-1) == I` and
   `M^((2^WIDTH-1)/p) != I` for every prime factor `p` of `2^WIDTH-1`.

## Decision Outcome

Chosen option: **3, algebraic primitivity checking**, because it is the
only one of the three that is both rigorous and tractable across the full
`WIDTH` range. Before trusting it, it was cross-validated against every
width already confirmed by brute-force simulation (widths 4, 5, 6, 7, 8, 10
confirmed correct; widths 3, 12, 16 confirmed wrong) — the algebraic check
reproduced every one of those results exactly, which is what justified
trusting it for the untested widths.

Running it across all 65 entries found **28 of 63 checked widths (2 through
64) had non-primitive masks** — far worse than the initial 3-of-9 sample
suggested. Valid replacement masks were found for all 28 via search (small
widths: deterministic scan in increasing order; large widths: randomized
search), each replacement independently re-verified with the same
primitivity check before being written into the table.

**Sparsity note:** the replacement search initially found *a* valid
primitive mask per width without optimizing for tap count. This matters
because every set bit in a tap mask is a real XOR gate in the feedback
network — every other (already-correct) entry in the table uses 2-4 taps,
while some randomly-found replacements needed 25-29. This has no timing
impact in this design specifically (see Consequences), but has a real,
avoidable area/power/FPGA-utilization cost. Future replacement searches
should bias toward low Hamming-weight candidates (trying 2-tap, then
3-tap, etc. before falling back to denser masks) rather than accepting the
first primitive candidate found.

### Consequences

- More taps means more area and more dynamic power (each tap is one XOR
  gate), scaling with however many instances of this LFSR end up
  instantiated in a larger design.
- More taps does **not** meaningfully affect critical-path timing in this
  specific implementation: the feedback bit (`q[0]`) is broadcast in
  parallel to every tap position (`q[i+1] ^ (q[0] & mask[i])`), so the
  logic depth from `q[0]` to any bit's next-state input is exactly one XOR
  gate regardless of tap count. The only secondary cost of more taps is
  increased fanout on `q[0]`, handled by ordinary synthesis buffering.
- On the target FPGA, LUT/slice utilization is the more direct proxy for
  "tap count cost" than gate count is; stochastic-computing designs are
  already utilization-hungry, so this compounds if the LFSR is replicated
  across many parallel SC streams.

### Confirmation

The algebraic check's correctness was established by exact agreement with
every previously brute-force-simulated width before being trusted further
(see Decision Outcome). After applying all 28 corrections to the table, 7
of the corrected widths (2, 3, 12, 13, 14, 16, 19) were additionally
confirmed by building and running the actual RTL (not just the Python
model) through Verilator, each reaching exactly `2^WIDTH - 1` unique states
before repeating — including a full 524,287-state run at `WIDTH=19`.

## Affected Files

- `blocks/stocastic/rtl/galois_lfsr.sv` (`TAPS_LUT` localparam, 28 of 65
  entries corrected)

## More Information

None.
```

- [ ] **Step 2: Verify required sections are present**

Run: `grep -c '^## ' docs/adr/0002-taps-lut-correctness-methodology.md`
Expected: `6` (Context and Problem Statement, Decision Drivers, Considered
Options, Decision Outcome, Affected Files, More Information — verified
against the actual file's heading count).

- [ ] **Step 3: Verify cited file paths and facts**

Run: `ls blocks/stocastic/rtl/galois_lfsr.sv`
Expected: path listed, no error.

Run: `grep -c "corrected: was" blocks/stocastic/rtl/galois_lfsr.sv`
Expected: `0` (those comments were intentionally removed earlier this
session — if this returns nonzero, the ADR's description of the table's
current state doesn't match reality; re-check before committing).

- [ ] **Step 4: Commit**

```bash
git add docs/adr/0002-taps-lut-correctness-methodology.md
git commit -m "docs: add ADR 0002 (TAPS_LUT correctness methodology)"
```

---

### Task 3: ADR 0003 — pixi for the toolchain

**Files:**
- Create: `docs/adr/0003-pixi-toolchain.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks depend on structurally; Task 4 references this file's title/number.

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0003-pixi-toolchain.md` with exactly this content:

```markdown
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
```

- [ ] **Step 2: Verify required sections are present**

Run: `grep -c '^## ' docs/adr/0003-pixi-toolchain.md`
Expected: `5` (this ADR omits the optional "Decision Drivers" section: Context
and Problem Statement, Considered Options, Decision Outcome, Affected Files,
More Information — verified against the actual file's heading count).

- [ ] **Step 3: Verify cited file paths exist**

Run: `ls pixi.toml pixi.lock`
Expected: both paths listed, no error.

- [ ] **Step 4: Commit**

```bash
git add docs/adr/0003-pixi-toolchain.md
git commit -m "docs: add ADR 0003 (pixi toolchain)"
```

---

### Task 4: ADR index

**Files:**
- Create: `docs/adr/README.md`

**Interfaces:**
- Consumes: final titles of ADR 0001, 0002, 0003 (written in Tasks 1-3).
- Produces: nothing further consumes this.

- [ ] **Step 1: Write the index**

Create `docs/adr/README.md` with exactly this content:

```markdown
# Architecture Decision Records

Index of design decisions for Microarch_Lib. Each record captures the
context, the alternatives considered, what was chosen and why, and how the
decision was verified — so a decision can be understood later without
asking whoever wrote it.

Template: `docs/design-specs/2026-07-25-adr-system-design.md`.

| # | Title | Status |
|---|-------|--------|
| [0001](0001-elaboration-check-mechanism.md) | Elaboration-time parameter checks use the bare `$error` form, not an `initial`+`assert` macro | Accepted |
| [0002](0002-taps-lut-correctness-methodology.md) | `TAPS_LUT` correctness is established by algebraic primitivity checking, not by trusting the source table | Accepted |
| [0003](0003-pixi-toolchain.md) | Use pixi for a reproducible, cross-platform verification toolchain | Accepted |
```

- [ ] **Step 2: Verify all links resolve**

Run: `for f in docs/adr/0001-elaboration-check-mechanism.md docs/adr/0002-taps-lut-correctness-methodology.md docs/adr/0003-pixi-toolchain.md; do test -f "$f" && echo "OK: $f" || echo "MISSING: $f"; done`
Expected: three `OK:` lines, no `MISSING:` lines.

- [ ] **Step 3: Commit**

```bash
git add docs/adr/README.md
git commit -m "docs: add ADR index"
```

---

## Self-Review Notes

- **Spec coverage:** All four files from the spec's "Affected Files" list
  (`docs/adr/README.md` + three ADRs) have a task each. Template fields
  (status/date front matter, Context and Problem Statement, Decision
  Drivers, Considered Options, Decision Outcome with Consequences +
  Confirmation, Affected Files) are present in all three ADRs; the
  spec-excluded `decision-makers`/`consulted`/`informed` fields are
  correctly absent from all three.
- **Placeholder scan:** No TBD/TODO markers; every ADR's content is written
  out in full in its task rather than referenced from elsewhere.
- **Type/naming consistency:** ADR numbers (0001/0002/0003) and exact
  titles match between each ADR's own `# NNNN. Title` heading and the
  README index's table — checked by direct comparison while writing this
  plan.
