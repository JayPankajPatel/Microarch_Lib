# Architecture Decision Records

Index of design decisions for Microarch_Lib. Each record captures the
context, the alternatives considered, what was chosen and why, and how the
decision was verified — so a decision can be understood later without
asking whoever wrote it.

To add a new one: copy `template.md` (base format is [MADR](https://adr.github.io/madr/), plus an `Affected Files` field this repo adds — see the comment at the top of the template for details). Background on why this system exists: `docs/design-specs/2026-07-25-adr-system-design.md`.

| # | Title | Status |
|---|-------|--------|
| [0001](0001-elaboration-check-mechanism.md) | Elaboration-time parameter checks use the bare `$error` form, not an `initial`+`assert` macro | Accepted |
| [0002](0002-taps-lut-correctness-methodology.md) | `TAPS_LUT` correctness is established by algebraic primitivity checking, not by trusting the source table | Accepted |
| [0003](0003-pixi-toolchain.md) | Use pixi for a reproducible, cross-platform verification toolchain | Accepted |
| [0004](0004-precommit-lint-scope-svh-headers.md) | Pre-commit lint hook globs only `blocks/*/rtl/*.sv`; `.svh` headers are covered transitively, not directly | Accepted |
| [0005](0005-taps-lut-sparse-vs-dense-ppa.md) | `TAPS_LUT` uses the sparse (low Hamming-weight) replacement masks, confirmed by real LibreLane+sky130 PPA numbers | Accepted |
| [0006](0006-galois-lfsr-tap-mirroring.md) | `galois_lfsr.sv`'s distributed-tap recurrence reads `TAPS_LUT` mirrored (`TAPS_LUT[WIDTH][WIDTH-1-i]`, not `[i]`) | Accepted |
| [0007](0007-gaisler-two-process-fsm-style.md) | FSM-shaped RTL uses the Gaisler two-process style (`r`/`rin` struct, single `always_comb` + single `always_ff`) | Accepted |
| [0008](0008-taps-lut-yosys-frontend-encoding.md) | `TAPS_LUT` is encoded as a constant function, not a `localparam` array, so it parses under Yosys's native frontend | Accepted |
| [0009](0009-formal-checker-inline-not-bind.md) | The `galois_lfsr` `no_lockup` formal property is an inline `` `ifdef FORMAL `` assertion, not a `bind`-ed checker module | Accepted |
| [0010](0010-formal-sby-invocation-robustness.md) | `.sby` files use repo-root-relative `[files]` paths and a dedicated `pixi run formal` task that redirects all run output to `/build/` | Accepted |
| [0011](0011-ma-macro-naming-elabor-vs-sva.md) | Verification macros are named `MA_<KIND>_ELABOR`/`MA_<KIND>_SVA`, not left unprefixed or named after their OpenTitan ancestor | Accepted |
