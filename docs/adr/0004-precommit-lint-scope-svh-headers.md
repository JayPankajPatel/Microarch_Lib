---
status: accepted
date: 2026-07-25
---

# 0004. Pre-commit lint hook globs only `blocks/*/rtl/*.sv`; `.svh` headers are covered transitively, not directly

## Context and Problem Statement

`.githooks/pre-commit` runs `verilator --lint-only` only on staged files
matching `blocks/*/rtl/*.sv`. It does not match `.svh` header files such as
`common/rtl/ma_assert_std.svh`, `common/rtl/ma_assert_dummy.svh`, or
`common/rtl/ma_assert.svh` (the dispatch header), even though those files
contain real macro logic (`` `MA_ASSERT_INIT ``) that could itself contain a
bug. The question is whether excluding `common/rtl/*.svh` from the glob is
an oversight — a coverage gap where header bugs slip through unlinted — or
the correct scope given how `` `include `` and `verilator --lint-only`
actually work.

## Decision Drivers

- Must be checked empirically, not assumed: does `verilator --lint-only`
  even accept a bare `.svh` file as input at all?
- A tapeout-bound library can't have silently-uncovered logic in files
  that look like they're deliberately excluded from the lint gate.
- Prefer not adding hook complexity (wrapper modules, synthetic harnesses)
  unless the current scope is actually shown to leave real logic unchecked.

## Considered Options

1. Keep the current scope (`blocks/*/rtl/*.sv` only); `.svh` content is
   covered transitively whenever a linted `.sv` file `` `include ``s it.
2. Broaden the glob to also match `common/rtl/*.svh` and run
   `verilator --lint-only` on each header file directly, standalone.
3. Broaden the glob to `common/rtl/*.svh`, but first generate a throwaway
   wrapper module per header (`` `include `` it, exercise its macros) so a
   standalone lint pass has something elaboratable to check.
4. Add a separate hook check (not `verilator --lint-only`) that verifies
   every `.svh` under `common/rtl/` is `` `include ``d by at least one `.sv`
   file that's actually in the lint glob, catching "orphaned" headers.

## Decision Outcome

Chosen option: **1, keep the current scope as-is**, because option 2 was
tested directly and does not work, and option 1 was confirmed to already
provide real coverage of header content for every header that exists today.

Empirical test, run directly against this repo's `.svh` files:

```
$ verilator --lint-only -Wall -Icommon/rtl common/rtl/ma_assert_std.svh
%Error: No top level module found
%Error: Exiting due to 1 error(s)
```

The same "No top level module found" error occurs for `ma_assert.svh` and
`ma_assert_dummy.svh` run standalone. This isn't a flag/config problem —
`verilator --lint-only` elaborates a design starting from a top-level
module, and a `.svh` header containing only `` `define `` macros has no
module to elaborate. Option 2 is therefore not a "gap" that broadening the
glob would fix; it would just make every commit touching a header fail the
hook unconditionally, regardless of whether the macro body is correct.

By contrast, linting the `.sv` file that actually `` `include ``s the
header exercises the macro-expanded content for real:

```
$ verilator --lint-only -Wall -Icommon/rtl blocks/stocastic/rtl/galois_lfsr.sv
%Warning-GENUNNAMED: blocks/stocastic/rtl/galois_lfsr.sv:14:5: Unnamed generate block 'genblk1' ...
    $error("%s:%0d: [%s] check failed", "blocks/stocastic/rtl/galois_lfsr.sv", 14, "ValidLFSRSizeCheck");
%Error: Exiting due to 1 warning(s)
```

That warning points directly at line 14 of `galois_lfsr.sv` — the exact
`$error(...)` line that `` `MA_ASSERT_INIT `` in `ma_assert_std.svh`
expands into. This confirms the header's macro body is genuinely
type-checked and elaborated as part of `galois_lfsr.sv`'s own lint pass,
via the `-Icommon/rtl` include path already present in the hook. The
current scope is therefore correct, not a gap: it doesn't attempt an
impossible standalone lint of a header, and it doesn't leave header content
actually unchecked, because every `.svh` in the repo today is reached by at
least one `.sv` file the hook does lint.

Options 3 and 4 were considered but rejected as unneeded machinery for the
current scale (three headers, all already exercised) — noted as a future
option below rather than built now.

### Consequences

- Positive: no wasted hook complexity; the hook stays a simple glob +
  `verilator --lint-only` loop, and it still catches real bugs inside
  header macros (as demonstrated by the `GENUNNAMED` warning above).
- Negative / residual risk: coverage of a `.svh` file is *implicit* and
  depends on at least one `.sv` file under `blocks/*/rtl/` actually
  `` `include ``ing it. If a header were ever added to `common/rtl/` without
  any `.sv` file including it yet (dead code, or included only from a
  testbench outside the glob), the hook would silently never touch it —
  this is a real but currently-hypothetical gap, since no such orphaned
  header exists today.
- Separately noted, not fixed here: the `` `ifdef ``-gated dummy branch
  (`common/rtl/ma_assert_dummy.svh`, used when `SYNTHESIS` or `YOSYS` is
  defined) is never exercised by the default pre-commit invocation, since
  neither macro is defined during that lint pass. This is a distinct
  ifdef-branch-coverage gap, not a `.sv`-vs-`.svh` file-scope gap, and is
  out of scope for this ADR.

### Confirmation

Verified empirically by running `verilator --lint-only` (pixi-installed,
version 5.050) directly, exactly as shown above: standalone `.svh` lint
fails with "No top level module found" for all three headers
(`ma_assert.svh`, `ma_assert_std.svh`, `ma_assert_dummy.svh`); linting
`blocks/stocastic/rtl/galois_lfsr.sv` (the hook's actual current scope)
does reach and type-check the macro-expanded header content, evidenced by
a warning whose reported line/text comes directly from inside the macro
expansion.

## Affected Files

- `.githooks/pre-commit` (scope unchanged by this decision)
- `common/rtl/ma_assert.svh`
- `common/rtl/ma_assert_std.svh`
- `common/rtl/ma_assert_dummy.svh`
- `blocks/stocastic/rtl/galois_lfsr.sv` (the `.sv` file that currently
  provides transitive coverage of `ma_assert_std.svh`)

## More Information

- If `common/rtl/` ever gains a header not yet included by any linted
  `.sv` file, revisit option 4 (an orphan-header check) rather than
  option 2/3 (they don't work / add unneeded complexity at this scale).
