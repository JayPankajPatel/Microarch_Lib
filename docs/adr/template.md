<!--
Template for a new Architecture Decision Record in this repo.

Base format: MADR (Markdown Architecture Decision Records) --
https://adr.github.io/madr/ -- with one addition ("Affected Files", not
part of stock MADR, added because traceability from a decision to the
exact code it governs matters in a hardware repo) and one deliberate
omission (the optional `decision-makers`/`consulted`/`informed` front
matter fields -- team-governance metadata not needed at this project's
scale; add back if that changes).

To use: copy this file to `docs/adr/NNNN-<slug>.md` using the next
sequential four-digit number (check docs/adr/README.md for the last one
used), fill in every section, delete this comment block, then add a row
to the table in docs/adr/README.md.
-->
---
status: proposed
date: YYYY-MM-DD
---

# NNNN. <Short title: the problem and the chosen solution>

## Context and Problem Statement

<What problem or question prompted this decision. Enough detail that
someone unfamiliar with the moment this was written could understand why
it mattered.>

## Decision Drivers

<Optional. Forces, constraints, or concerns that shaped the decision --
skip this section entirely if there's nothing non-obvious to say.>

## Considered Options

1. <Option 1>
2. <Option 2>
3. <...>

## Decision Outcome

Chosen option: **<N, name>**, because <justification>.

<For each rejected option, explain specifically why it lost -- "wasn't as
good" is not an acceptable reason; name the concrete failure mode, missing
tool support, wrong semantics, etc.>

### Consequences

<Positive and negative downstream effects of the choice, including any
residual risk or known limitation that wasn't fixed.>

### Confirmation

<How this was actually verified -- a command that was run and its real
output, a test that passed, a cross-check against an independent source.
Not just an assertion that it's correct.>

## Affected Files

- `path/to/file.sv`
- `path/to/other_file.svh`

## More Information

<Optional. Links, related ADRs, follow-up items.>
