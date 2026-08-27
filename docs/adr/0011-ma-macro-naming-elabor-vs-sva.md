---
status: Accepted
date: 2026-08-26
---

# 0011. Verification macros are named `MA_<KIND>_ELABOR`/`MA_<KIND>_SVA`, not left unprefixed or named after their OpenTitan ancestor

## Context and Problem Statement

`common/rtl/ma_assert_std.svh` originally defined two unrelated kinds of
check under confusingly similar names:

- `` `MA_ASSERT_INIT `` — the elaboration-time parameter check from
  `docs/adr/0001-elaboration-check-mechanism.md`. Despite the name, it does
  *not* use an `initial` block; ADR 0001 deliberately rejected that shape
  (OpenTitan's own `` `ASSERT_INIT ``, which does use one, hit a real
  `initial`-block race condition, lowRISC/opentitan#9017). "INIT" survived
  purely as a naming holdover from that rejected ancestor.
- `` `ASSUME ``/`` `ASSERT ``/`` `COVER `` — new concurrent SVA property
  wrappers (`` assert property (@(posedge clock) disable iff (reset) ...) ``)
  for runtime/formal checks, added without the `MA_` prefix ADR 0001
  established specifically to avoid collisions with other libraries'
  macros of the same generic names.

Two concrete problems surfaced from this in the same session:

1. `` `MA_ASSERT_INIT `` and `` `ASSERT `` were mistaken for the same thing
   mid-conversation — reasonable, since the names differ only by a suffix
   that no longer describes what either macro actually does (one is a
   static, single elaboration-time check with no clock; the other is a
   per-cycle runtime property with `clock`/`reset` arguments).
2. The unprefixed `` `ASSUME ``/`` `ASSERT ``/`` `COVER `` macros had been
   defined identically in *two* files (`ma_assert_std.svh` and a stray new
   `sva_macros.svh`) — an unguarded macro-redefinition hazard the `MA_`
   prefix convention was supposed to make unlikely by making collisions
   visibly deliberate rather than accidental.

## Considered Options

1. Keep `` `MA_ASSERT_INIT ``'s name for OpenTitan-precedent recognizability;
   leave `` `ASSUME ``/`` `ASSERT ``/`` `COVER `` unprefixed to match SVA's
   own keyword names for readability.
2. Rename only `` `MA_ASSERT_INIT ``; leave the SVA wrappers unprefixed.
3. Prefix every verification macro with `MA_`, and disambiguate check kind
   with an explicit suffix: `_ELABOR` (elaboration-time, no clock, checked
   once) vs. `_SVA` (concurrent property, checked every cycle in
   simulation/formal).

## Decision Outcome

Chosen option: **3**, implemented as `` `MA_ASSERT_ELABOR `` (was
`` `MA_ASSERT_INIT ``) and `` `MA_ASSUME_SVA ``/`` `MA_ASSERT_SVA ``/
`` `MA_COVER_SVA `` (was unprefixed), all consolidated into
`common/rtl/ma_assert_std.svh`; the duplicate `common/rtl/sva_macros.svh`
was deleted.

- **Option 1** is what actually caused both problems above — keeping
  `INIT` preserved a name that actively misleads about mechanism (no
  `initial` block, contradicting the name), and leaving the SVA macros
  unprefixed is exactly the collision shape ADR 0001 already reasoned
  through and rejected once, which is presumably why it recurred: nothing
  enforced it for macros added later.
- **Option 2** fixes the confusion between `_INIT`/plain `ASSERT` but
  leaves the SVA macros exposed to the same collision risk ADR 0001 raised
  for `` `ASSERT_INIT `` itself — no reason a fix motivated by "these two
  things look too similar and collide" should stop halfway.
- **Option 3 (chosen)** fixes both: every macro is unambiguously namespaced
  (`MA_`), and the suffix communicates the one property someone reading a
  call site most needs to know before trusting the check — whether it runs
  once at elaboration or every cycle at runtime — without having to open
  the header and read the macro body.

### Consequences

- All four macros now read `` `MA_ASSERT_ELABOR ``, `` `MA_ASSUME_SVA ``,
  `` `MA_ASSERT_SVA ``, `` `MA_COVER_SVA `` — longer names, but the
  suffix is load-bearing (see Decision Outcome), not decorative.
- `common/rtl/sva_macros.svh` no longer exists; `ma_assert_std.svh` is the
  single source for all four macros, matching `ma_assert.svh`'s existing
  tool-dispatch role for `` `MA_ASSERT_ELABOR `` (real body vs.
  `ma_assert_dummy.svh`'s no-op under `` `ifdef SYNTHESIS ``/`` `YOSYS ``).
  The `_SVA` macros deliberately have **no** dummy/no-op counterpart, and
  should not gain one: `` `MA_ASSERT_ELABOR `` needs tool-dispatch no-ops
  because it sits unguarded in the module body on the synthesizable path,
  so Yosys/synthesis sees it whether wanted or not. A concurrent
  `` assert property (...) `` statement has the opposite property — it is
  never legal to leave unguarded in synthesizable RTL, so the caller must
  already wrap every `_SVA` call in `` `ifdef FORMAL ``/`` `ifdef SIM ``
  (as `galois_lfsr.sv`'s hand-rolled `no_lockup` property already does).
  Adding a `_SVA` no-op under `` `ifdef YOSYS `` would silently strip
  formal properties the moment someone calls one — the same failure class
  as the `bind`-checker bug in `docs/adr/0009` (zero `$check` cells, no
  warning). `ma_assert.svh`'s dispatch condition was confirmed to route
  only `` `MA_ASSERT_ELABOR `` to `ma_assert_dummy.svh` today; keep it that
  way.
- `galois_lfsr.sv`'s existing `no_lockup` formal property still hand-rolls
  its `` `ifdef FORMAL ``-guarded assertion directly (predates this ADR;
  see `docs/adr/0009-formal-checker-inline-not-bind.md`) rather than using
  `` `MA_ASSERT_SVA ``. Converting it is optional follow-up, not required
  by this decision.

### Confirmation

- `grep -rn 'sva_macros\|ASSUME(\|ASSERT(\|COVER('` across
  `blocks/**/*.sv`, `common/rtl/*.svh`, `**/*.sby` before the rename found
  no call sites for the unprefixed SVA macros anywhere in the repo — the
  rename was non-breaking by construction, not just by luck.
- `grep -rn "MA_ASSERT_INIT"` across `**/*.sv`/`**/*.svh` after the rename
  returned nothing, confirming no stale references were left behind in
  current code.
- `pixi run verilator --lint-only -Wall -Icommon/rtl <file>` re-run on
  every file that calls `` `MA_ASSERT_ELABOR `` (`counter.sv`,
  `binary_stochastic_converter.sv`, `galois_lfsr.sv`,
  `stochastic_binary_converter.sv`) after the rename: no undefined-macro
  errors: only the same pre-existing `DECLFILENAME`/`GENUNNAMED`/
  `WIDTHEXPAND` warnings present before this change (confirmed by diffing
  against `git show HEAD:<path>` for the oldest one, `counter.sv`), and
  `binary_stochastic_converter.sv`'s unrelated `MODMISSING` (missing
  `-I`/file-list entries for its instantiated submodules, not this macro).

## Affected Files

- `common/rtl/ma_assert.svh`
- `common/rtl/ma_assert_std.svh`
- `common/rtl/ma_assert_dummy.svh`
- `common/rtl/sva_macros.svh` (deleted)
- `blocks/basic/counter.sv`
- `blocks/stocastic/rtl/binary_stochastic_converter.sv`
- `blocks/stocastic/rtl/galois_lfsr.sv`
- `blocks/stocastic/rtl/stochastic_binary_converter.sv`
- `CLAUDE.md`

## More Information

`docs/adr/0001-elaboration-check-mechanism.md` established the `MA_`
prefix and the bare-`$error`/no-`initial`-block mechanism this ADR's
`_ELABOR` suffix now names accurately; older ADRs (0006, 0007, 0008, 0009)
and `docs/design-specs/plans/2026-07-25-adr-retroactive-entries.md` quote
`` `MA_ASSERT_INIT `` in code blocks as historical record of the decision
at the time it was written and are intentionally left unedited rather than
retroactively updated to the new name.
