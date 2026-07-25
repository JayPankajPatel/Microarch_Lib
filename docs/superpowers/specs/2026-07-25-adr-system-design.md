# Design: ADR System for Microarch_Lib

## Context

`Microarch_Lib` is a hardware IP library headed toward both ASIC tapeout and a custom FPGA fabric project (a stochastic-computing MAC unit). Design decisions made during development (e.g. why the elaboration-check macros are structured the way they are, why `TAPS_LUT` values were corrected) currently exist only as conversation history and code comments. The user wants **traceability**: the ability for themselves (if away) or a colleague to understand *why* a module is built the way it is without having to ask the original author directly. This pattern is also intended to potentially be reused across the user's other projects, but the scope of this design is Microarch_Lib only.

## Decision

Adopt **Architecture Decision Records (ADRs)**, using the **MADR (Markdown ADR) template** as the base, stored self-contained inside the `Microarch_Lib` repo.

### Location & structure

- `docs/adr/` at the repo root.
- Files numbered sequentially: `docs/adr/0001-<slug>.md`, `0002-<slug>.md`, etc.
- `docs/adr/README.md` acts as an index: one line per ADR (number, title, one-line summary, status), newest or all entries listed for quick scanning before opening any single record.
- This mirrors the `index.md` pattern already used in the user's personal `~/wiki/` (Karpathy-style "Open Knowledge" wiki) for stylistic consistency, but is **fully self-contained** — no dependency on `~/wiki/` being present, in sync, or even installed. `Microarch_Lib` is already a git repo, so this location travels correctly across machines via normal clone/pull.
- Cross-links out to `~/wiki/` (e.g. for general/reusable FPGA-fabric or stochastic-computing knowledge that isn't specific to this repo) are **soft references only** — plain text mentions or paths, never a hard dependency the ADRs need to resolve correctly.

### Per-record template (MADR-based, with one addition)

```markdown
---
status: accepted
date: YYYY-MM-DD
---

# NNNN. <Short title: problem + solution>

## Context and Problem Statement

<What problem or question prompted this decision>

## Decision Drivers (optional)

<Forces/concerns that shaped the decision, if non-obvious>

## Considered Options

- Option 1
- Option 2
- ...

## Decision Outcome

Chosen option: "...", because <justification>.

### Consequences

<Positive and negative downstream effects>

### Confirmation

<How this was actually verified -- e.g. "Verilator lint clean + GF(2) primitivity
check across all 65 widths, cross-validated against brute-force simulation">

## Affected Files

- `path/to/file.sv`
- `path/to/other_file.svh`

## More Information (optional)
```

Deliberately **excluded** from stock MADR: the `decision-makers` / `consulted` / `informed` YAML fields. Those are aimed at multi-stakeholder team governance and are YAGNI for the current solo-project scale — can be added later without restructuring anything if that changes.

### Scope: retroactive ADRs

Write ADRs now for decisions already made this session, so the log starts complete rather than picking up mid-history:

1. **Elaboration-check mechanism** — why `common/rtl/ma_assert.svh`/`ma_assert_std.svh`/`ma_assert_dummy.svh` use the bare `$error` conditional-generate form (IEEE 1800-2017 §20.11) rather than OpenTitan's `` `ASSERT_INIT `` (`initial`+`assert`) pattern, including the Xcelium race-condition bug (lowRISC/opentitan#9017) that motivated avoiding the `initial`-block approach, and the `` `ifdef ``-based tool dispatch (`SYNTHESIS`/`YOSYS` → dummy macros) with the Verilator-support finding that narrowed which branches actually need it.
2. **`TAPS_LUT` correctness methodology** — why table correctness is established via GF(2) algebraic primitivity checking (transition-matrix exponentiation) rather than trusting a reference table, including the finding that 28 of 65 entries were wrong and the sparse-vs-dense tap tradeoff (area/power/FPGA utilization) that governs how replacements are chosen.
3. **Toolchain: pixi for cross-platform reproducibility** — why `pixi` (verilator/yosys/libz3/click via conda-forge, `sby` built from source via a pixi task since SymbiYosys isn't packaged) was chosen, including the platform gaps found (no `osx-arm64`/`linux-aarch64` yosys builds).

Going forward, new non-obvious design decisions get an ADR at the time they're made, not batched up later.

## Consequences

- **Positive:** Decisions are traceable without depending on conversation history or the original author's availability. New blocks inherit the same pattern from day one. The format is a recognized standard (MADR), not a bespoke one, so it's portable to the user's other projects later.
- **Negative:** Adds a small amount of overhead per non-trivial decision (writing the record). Retroactive ADRs require reconstructing rationale from this session rather than writing it in the moment — mitigated by doing it immediately, while the reasoning is fresh.
- **Out of scope for this design:** per-block `README.md` usage docs (how to instantiate a block, parameter meanings) — left as an open question, not blocking this system's adoption. Syncing/merging the user's laptop and desktop `~/wiki/` copies — explicitly deferred by the user, unrelated to this repo.

## Affected Files

- New: `docs/adr/README.md`
- New: `docs/adr/0001-elaboration-check-mechanism.md`
- New: `docs/adr/0002-taps-lut-correctness-methodology.md`
- New: `docs/adr/0003-pixi-toolchain.md`
