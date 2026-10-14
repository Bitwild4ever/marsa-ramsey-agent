---
name: ramsey-construction-search
description: Attack a Ramsey-type lower bound R(s,t) > n by searching for or exhausting constructions, and settle every claim by exact computation rather than review.
compatibility: Requires the deterministic ramsey_* tools (marsa engine).
allowed-tools: ramsey_search ramsey_verify_construction ramsey_violations ramsey_enumerate_family query_memory record_failed_path search_knowledge
metadata:
  title: Ramsey Construction Search
  category: installed
  tags: research,ramsey,combinatorics,construction,exhaustive
  skill-standard: agentskills.io/v1
---

# Ramsey Construction Search

## Usage Hint
- Use this skill when the target is a **lower bound** of the form "there exists a 2-colouring of `K_n` with no red `K_s` and no blue `K_t`", i.e. a proof that `R(s,t) > n`.
- Use it when you have a concrete graph, a search run, or an enumeration result that is supposed to establish such a bound.
- Do **not** use this skill for upper bounds. Proving `R(s,t) <= n` is a different (much harder, non-constructive) task; a search failure is not an upper-bound proof.
- Do **not** try to confirm a construction by reading it, and do **not** send it to `verify_correctness_computation`. That tool reviews proof prose with an LLM; it cannot enumerate cliques. A construction claim is decided by `ramsey_verify_construction`.

## Summary
A construction proves a lower bound exactly when it is valid, and validity is a finite check. So the workflow is: **produce candidates cheaply, then decide them exactly.** Never let a heuristic search's own claim stand as a result.

## Execution Steps
1. **Fix the target.** State `(s, t, n)` and what counts as success: a valid colouring at `n` proves `R(s,t) > n`.
2. **Prefer a decision over a search when the space allows it.** If the candidate family is structured and small (a circulant family at `n <= 46` has only `floor(n/2)` free bits), call `ramsey_enumerate_family`. A `none_exist` answer closes that family permanently; a `exists` answer gives a witness. Do not spend search budget inside a family you can decide.
3. **Otherwise search, with a fixed wall-clock budget.** Call `ramsey_search` with an explicit `budget_seconds`. Use several `seed` values and compare **means**, not the single best run; on these instances two seeds of the same configuration can differ by nearly 2x.
4. **Verify anything that looks like a result.** If `ramsey_search` returns `solved`, feed its `graph6` to `ramsey_verify_construction`. Only `passed = true` there establishes the bound. Quote the tool's verdict, not your own reading of the graph.
5. **Measure partial progress with `ramsey_violations`.** A falling violation count is real progress. But treat small values (1-5) as "not solved": eliminating the last few violations is qualitatively harder than reducing a large count, so do not extrapolate.
6. **Record negative outcomes as first-class research.** A family ruled out by `ramsey_enumerate_family`, or a budget that stayed unsolved, is a durable result. Store it with `record_failed_path` so the same route is not re-attempted in a later session.
7. **Check prior work first.** Call `query_memory` and `search_knowledge` for previously excluded families and previously found constructions before starting a new attack.

## Tool Calls
- `ramsey_enumerate_family`: decide a structured family exhaustively. Preferred whenever the space is small enough.
- `ramsey_search`: bounded heuristic attempt; returns a candidate, never a verdict.
- `ramsey_verify_construction`: the deciding check; independent implementation.
- `ramsey_violations`: exact obstruction count for cheap comparison and progress tracking.
- `query_memory`, `search_knowledge`: recover previously excluded families and known constructions.
- `record_failed_path`: persist an excluded family or an exhausted budget as a durable negative result.

## Output Contract
- State the bound and the exact verdict that supports it: `ramsey_verify_construction` returned `verified`, so `R(s,t) > n`.
- Distinguish three statuses explicitly and never blur them:
  - **proved**: a construction was independently verified, or a family was exhaustively decided.
  - **partial**: violation count reduced, with the number reported.
  - **inconclusive**: budget exhausted. Say only that; it is not evidence against existence.
- When a negative result is obtained, name the family and the space size that was checked, so the scope of what is excluded is unambiguous.

## Notes
- Two independent results are available as anchors to sanity-check the engine: the circulant family has solutions at `n = 38` but none at `n = 46`, the latter consistent with the known theorem `R(5,5) <= 46`.
- A `none_exist` result concerns one family only. The general problem stays open; never present a family exclusion as a general impossibility.
