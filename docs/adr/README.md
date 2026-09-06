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
| [0012](0012-stochastic-multiplier-join-semantics.md) | `stochastic_multiplier` joins two independent valid/ready producers with `valid` never gated on `ready` | Accepted |
| [0013](0013-encoder-burst-length-and-counter-clear.md) | Fixes issue #2's burst-length mismatch; `counter` gets an explicit synchronous `clr` instead of relying on wraparound coincidence | Accepted |
| [0014](0014-stochastic-adder-mux-scaling-and-select-independence.md) | `stochastic_adder` computes `(A+B)/2` via MUX with its own internal, independently-parameterized select LFSR | Accepted |
| [0015](0015-encoder-init-seed-parameter-for-decorrelation.md) | `binary_stochastic_converter` exposes `INIT_SEED`, required to be distinct across instances sharing a consumer | Accepted |
| [0016](0016-encoder-accept-must-not-depend-on-downstream-ready.md) | Encoder's burst accept depends only on its own state and `valid_binary_in`, never on `ready_stochastic_out` -- fixes a mutual-startup deadlock when composing two encoders into one join | Accepted |
| [0017](0017-decoder-window-close-via-boundary-pulse.md) | `stochastic_to_binary` closes its window on an explicit `boundary_in` pulse from the producer, not a locally-counted length match | Accepted |
