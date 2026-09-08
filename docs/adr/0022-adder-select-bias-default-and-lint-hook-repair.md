---
status: Accepted
date: 2026-09-07
---

# 0022. Adder collision-prone default + undocumented select bias, and pre-commit lint hook repair

## Context and Problem Statement

Two further findings from the same `/tmp/stochastic_blocks_reaudit.md`
independent audit that produced ADR 0021, addressed separately here since
neither is part of that ADR's encoder/decoder scope:

1. **`stochastic_adder`'s default parameters collide with the library's own
   typical encoder defaults.** `SELECT_LFSR_WIDTH` defaulted to `4` and
   `SELECT_INIT_SEED` to `WIDTH'(1)` — identical to `galois_lfsr`'s own
   module default and to the WIDTH/seed pair most operand encoders in this
   library use unless told otherwise. A standalone `stochastic_adder`
   instantiation that overrides neither parameter silently reproduces the
   exact failure mode its own header comment warns against (select
   correlated with an operand, per ADR 0015/0018), while the header comment
   claimed the defaults already "default away from galois_lfsr's own
   default" — which was not actually true of the shipped code. Only the
   integration test wrapper (`test_b_add_s_integration/top.sv`) overrode
   `SELECT_LFSR_WIDTH` to `5` and enforced `SELECT_LFSR_WIDTH != WIDTH` via
   its own elaboration check (ADR 0018) — a standalone user of the module
   itself had no such protection.

2. **The select bit's 50/50 split is only approximate, and nothing said
   so or explained why the existing statistical test's 0.05 tolerance was
   the right number.** A maximal-length `W`-bit LFSR is a balanced
   m-sequence: any single output bit is `1` for exactly `2^(W-1)` of the
   sequence's `2^W-1` states and `0` for the remaining `2^(W-1)-1` — an
   odd period makes an exact even split mathematically impossible from a
   single bit, for any width or seed. At `WIDTH=4` this is a ~0.033 bias
   (8/15 vs. 1/2); the existing `scaled_sum_statistical_property` test's
   `0.05` tolerance happened to clear it, but nothing said this was a
   real, permanent structural bias being tolerated rather than an
   arbitrary safety margin around pure sampling noise.

3. **The documented pre-commit lint gate (`.githooks/pre-commit`) could not
   actually lint this library.** It ran `verilator --lint-only` on each
   staged file in isolation, with no dependencies provided. Any multi-file
   module (`binary_stochastic_converter` needing `counter` and
   `galois_lfsr`; `stochastic_adder` needing `galois_lfsr`) fails with a
   missing-module error regardless of whether the file's own content is
   correct. `pixi.toml` already had a `lint` task that resolves the full
   Bender-derived source graph and the file's actual module name (not a
   filename guess — needed since e.g. `stochastic_binary_converter.sv`
   contains module `stochastic_to_binary`), but that task's `-Wall` was
   never actually usable as a pass/fail gate either: it fails on the
   `GENUNNAMED` warning present at every `` `MA_ASSERT_ELABOR `` call site
   repository-wide (a known, already-accepted cosmetic class throughout
   this whole project) and the `DECLFILENAME` warning at every existing
   filename/module-name mismatch — meaning a hook wired to it, unmodified,
   would fail every single commit touching any RTL file, working or not.

## Decision Outcome

**Adder default: change `SELECT_LFSR_WIDTH` to `5`.** Matches what the
integration wrapper already independently arrived at as a safe choice.
Not a complete fix — no single default is safe against every possible
caller configuration, only against the single most common one (a same-
default encoder) — so the header comment was corrected to say exactly
that, rather than falsely claim the collision was already handled.

**Select bias: document it, don't chase a fix that doesn't exist.**
Considered whether some other width or seed could get closer to exactly
0.5 — rejected, since the balanced-m-sequence property is a property of
*any* maximal-length LFSR at *any* width, not a property of a particular
choice that could be tuned away. Added the exact bias magnitude (`16/31`
at the new `WIDTH=5` default) to both the RTL header comment and the
statistical test's tolerance comment, so the `0.05` figure reads as a
derived bound (structural bias + sampling noise) instead of an
unexplained magic number. If a caller's application needs an exact, not
approximate, `(A+B)/2`, this module's single-LFSR-bit select mechanism
cannot provide that regardless of parameters — stated explicitly rather
than left to be discovered.

**Lint hook: point it at the existing `pixi run lint` task, with
`-Wno-GENUNNAMED -Wno-DECLFILENAME` added to that task itself.** Both
warning classes are pre-existing, already-accepted noise (confirmed
throughout this project's whole history — see every ADR's own lint
confirmation sections) unrelated to the correctness of new code; suppressing
them at the task level (not per-file, not via scattered `` /* verilator
lint_off */ `` comments) means `pixi run lint <file>` becomes a real,
usable pass/fail signal — clean code exits 0, a genuine defect still
exits nonzero. Verified both directions directly (see Confirmation) rather
than assumed. The alternative (leave `-Wall` as-is and have every commit
fail) was rejected as strictly worse than no hook at all — a hook that
always fails teaches everyone to reach for `--no-verify`, defeating its
purpose entirely.

### Confirmation

- `pixi run lint <file>` tested against a genuinely broken file
  (undeclared-identifier reference, injected via a scratch copy overlaid
  onto the tracked path and restored via plain file copy afterward, not
  `git checkout --`): exits `1` with the real Verilator error shown.
  Tested against currently-correct files (including
  `stochastic_binary_converter.sv`, the exact filename/module-name
  mismatch case): exits `0`.
- `.githooks/pre-commit` invoked directly (staged two real modified files,
  ran the hook script, then unstaged with `git reset` — no actual commit
  made): exits `0`, correctly linting both files including the
  filename/module-name mismatch case that a filename-guessing hook would
  have gotten wrong.
- Full repo regression (`scripts/run_regression.sh`): 31/31 passing after
  the adder default change (all cocotb signal widths are read dynamically
  from the DUT, not hardcoded to the old default, so no test needed
  updating for the width change itself — only the tolerance comment was
  updated for documentation accuracy).
- `pixi run verilator --lint-only -Wall -Icommon/rtl` clean (pre-existing
  `GENUNNAMED` class only) on both adder reset variants.

### Consequences

- `stochastic_adder`/`stochastic_adder_sync`'s default `SELECT_LFSR_WIDTH`
  changed from `4` to `5` — any code relying on the OLD default value
  specifically (not just "some default") would need updating; none exists
  in this repo (the only other instantiation, the integration wrapper,
  already explicitly passed `5`).
- This ADR does not fix the remaining audit findings not in its scope: the
  Zybo Z7 FPGA wrapper's reset gap, `binary_multiply_top`'s truncated
  observable product, most testbenches' still-fragile active-edge
  scheduling, sync variants' lack of dedicated (as opposed to
  `COCOTB_TOPLEVEL`-override-reused) regressions, and stale
  waveform/comment documentation. Recorded in
  `/tmp/stochastic_blocks_reaudit.md` (not committed) for future triage.

## Affected Files

- `blocks/stocastic/rtl/stochastic_adder.sv`
- `blocks/stocastic/rtl/stochastic_adder_sync.sv`
- `blocks/stocastic/verif/tb/test_stochastic_adder/test_stochastic_adder.py`
- `pixi.toml`
- `.githooks/pre-commit`

## More Information

Follows directly from ADR 0021's same audit source. See ADR 0018 for the
integration wrapper's own `SELECT_LFSR_WIDTH != WIDTH` elaboration check,
which this ADR's default change makes the *common* case safe by default
without replacing that check's role as the actual enforced guarantee at
the composition point that matters.
