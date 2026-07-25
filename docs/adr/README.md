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
