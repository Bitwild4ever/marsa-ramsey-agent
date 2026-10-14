---
name: ramsey-frontier-bookkeeping
description: Maintain an accurate, explicitly scoped record of what is proved, what is excluded, and what remains open for a Ramsey-type lower bound. Use to avoid both repeated work and overclaiming across a long session.
compatibility: Requires the deterministic ramsey_* tools (marsa engine).
allowed-tools: ramsey_verify_construction ramsey_enumerate_family ramsey_search ramsey_violations query_memory search_knowledge read_runtime_file record_failed_path store_conclusion add_knowledge
metadata:
  title: Ramsey Frontier Bookkeeping
  category: installed
  tags: research,ramsey,state,bookkeeping,honesty
  skill-standard: agentskills.io/v1
---

# Ramsey Frontier Bookkeeping

## Usage Hint
- Use this skill at the **start** of a research turn, to re-establish what is actually known before deciding what to do.
- Use it before claiming any bound, and before concluding that a route is exhausted.
- Use it when several turns or sessions have passed and the state may have drifted.
- Do **not** use it as a substitute for verification. It records verdicts; it does not produce them.

## Summary
Over a long run the two failure modes are symmetric: repeating work that was already settled, and quietly overstating what was achieved. Both are prevented by keeping one explicit, scoped record of the frontier.

## The frontier for R(5,5)

| item | status |
|---|---|
| proven upper bound | `R(5,5) <= 46` |
| proven lower bound | `R(5,5) >= 43` |
| **open targets** | **`n = 44` and `n = 45` only** |

The reason only two targets are open is worth internalising, because it is easy to get wrong:

- `R(5,5) >= 43` means **a valid colouring exists on 43 vertices**.
- Deleting a vertex from a valid colouring leaves a valid colouring. So one exists for **every** `n <= 43`.
- Hence producing a colouring at `n <= 43` proves nothing new. Only `n = 44` or `n = 45` would.

What each target would buy:

| target | consequence |
|---|---|
| a valid colouring at `n = 44` | `R(5,5) >= 45`, improving a lower bound unchanged since 1989 |
| a valid colouring at `n = 45` | `R(5,5) >= 46`; combined with the proved `<= 46`, this gives `R(5,5) = 46` |
| a valid colouring at `n = 46` | **impossible** — it would contradict the proved upper bound. Treat any such claim as a bug and re-verify; this makes `n = 46` a useful correctness check on the toolchain |

Backup target with a much wider gap: `R(4,6)` satisfies `35 <= R(4,6) <= 41`. A valid `(4,6)`-colouring at `n = 36` would give `R(4,6) >= 36`, and this lower bound has historically been moved by search, unlike the frozen `R(5,5)` lower bound.

## Execution Steps
1. **Re-read the state before acting.** Call `query_memory` for prior verified constructions, excluded families, and failed paths. `read_runtime_file` on the project research log when a turn has been long.
2. **Separate the two kinds of question, always.**
   - *Lower bound*: exhibit a valid colouring. This is a construction problem, and search or enumeration can settle it.
   - *Upper bound*: show **every** colouring fails. This is a proof problem. **No amount of search failure is evidence for it.**
3. **Check whether the target is even open.** Producing a construction at `n <= 43` is calibration, not progress. Say so explicitly when reporting it.
4. **When a result is obtained, verify it and record it with its exact scope.** A verified construction: its `n`, its `graph6`, and the verifying verdict. An excluded family: the family name, its parameter count, and the space size actually checked.
5. **When nothing is obtained, record that too** — the budget spent and the best violation count reached. `best violations = 5` is a measurement; it is **not** "almost done" and **not** "none exists".
6. **Promote only what deserves it.** A construction verified at a genuinely open `n` is a knowledge-layer result; a family exclusion is a scoped structural fact; an unfinished search is a note. Do not promote notes to conclusions.

## Output Contract
- Every claim carries its type: **proved** (independently verified construction, or exhaustive family decision), **measured** (best violation count), or **open** (budget exhausted).
- Every negative claim carries its scope: *which* family, *how many* members checked, *which* `n`.
- Never write "there is no construction" when the evidence is "the search did not find one". Never write "this family is impossible" when the evidence is "this family contains none".

## Notes
- Known anchors, useful for sanity-checking the toolchain: the circulant family contains valid `(5,5)`-colourings at `n = 38`, and contains none at `n = 43` or `n = 46`. The `n = 46` case matches the proved upper bound; the `n = 43` case implies the famous 43-vertex construction is not circulant.
- Distinguish "the method cannot reach it" from "it does not exist". The first is a statement about effort, and effort is usually the binding constraint.
- Because `n <= 43` is settled ground, calibration work there is cheap and useful — but must never be reported as a new result.
