---
name: symmetric-family-exhaustion
description: Decide a structured family of colourings completely instead of searching it. Use when a family has few free parameters, so the whole family can be enumerated and the answer becomes a decision rather than a best effort.
compatibility: Requires the deterministic ramsey_* tools (marsa engine).
allowed-tools: ramsey_enumerate_family ramsey_verify_construction query_memory search_knowledge record_failed_path read_runtime_file
metadata:
  title: Symmetric Family Exhaustion
  category: installed
  tags: research,ramsey,exhaustive,structure,decision
  skill-standard: agentskills.io/v1
---

# Symmetric Family Exhaustion

## Usage Hint
- Use this skill when you are about to **search** for a construction and the construction would live in a structured family (circulant, Cayley, biquadratic, or any family described by few parameters).
- Use it when a search inside a family has stalled and you need to know whether a solution exists there **at all**, before spending more budget.
- Use it when you want to permanently close off a line of attack.
- Do **not** use it for arbitrary unstructured colourings. The general space has `C(n,2)` free bits and cannot be enumerated; there `ramsey_search` is the right tool.
- Do **not** present a family exclusion as a general impossibility. It says nothing about colourings outside the family.

## Summary
A heuristically searched family can only ever tell you "I did not find one". An enumerated family tells you "there is none" — and that is a durable mathematical fact. Whenever the parameter count is small enough to enumerate, enumeration strictly dominates searching: it is faster, it cannot miss a needle, and its negative answer ends the line of inquiry.

The reason this is practical rather than absurd: imposing structure collapses the space.

| object | free parameters at n = 43 |
|---|---|
| arbitrary 2-colouring | `C(43,2)` = 903 bits |
| circulant colouring | `floor(43/2)` = **21 bits** |

2^21 ≈ 2.1 million members — routinely enumerable.

## Execution Steps
1. **Choose the family deliberately and state what it excludes.** Say which colourings are in it and which are not. Remember the negative result applies only inside the stated family.
2. **Count the free parameters before doing anything.** If the family is parameterised by `k` bits, the space has `2^k` members. If that exceeds roughly `10^7`, enumeration is not the right move yet — consider a smaller `n`, a narrower family, or hand the task to `ramsey_search`.
3. **Call `ramsey_enumerate_family`.** It checks every member and returns either `exists` (with a witness and its connection set) or `none_exist` (with the space size that was fully checked).
4. **Confirm any witness with `ramsey_verify_construction`.** The enumerator's internal check and the verifier are separate code paths; agreement between them is what makes the result trustworthy.
5. **Record the outcome as research state, either way.**
   - `exists` ⇒ a verified lower-bound witness. Preserve `graph6` and the connection set.
   - `none_exist` ⇒ call `record_failed_path` with the family name and the space size, so a later session does not re-attempt it.
6. **Check prior exclusions first.** Call `query_memory` for previously excluded families before designing a new attack; repeating a closed family is pure waste.

## Tool Calls
- `ramsey_enumerate_family`: the enumeration itself; returns a decision plus witness.
- `ramsey_verify_construction`: independent confirmation of a witness.
- `query_memory`: recover which families were already excluded.
- `record_failed_path`: persist a family exclusion durably.
- `search_knowledge`: check whether a family's status is already recorded.

## Output Contract
- State the family, its parameter count `k`, and the space size `2^k` that was actually checked. An exclusion without a stated scope is unusable.
- Report exactly one of: `exists` (with witness) or `none_exist` (scoped to the family).
- Never write "no construction exists" when you mean "this family contains none".

## Notes
- **Existence inside a restricted family is not monotone in `n`.** Deleting a vertex from a structured colouring destroys the structure, so a solution at `n` does **not** imply one at `n-1`. Concretely, the circulant family has solutions at `n = 38` but none at `n = 39`, and again solutions at `n = 40` and `n = 41`. Do not extrapolate across `n` in either direction; enumerate each `n` separately.
- Two anchors are known for the circulant family and are useful for sanity-checking the engine: it has solutions at `n = 38`, and it has **none** at `n = 43` and none at `n = 46`. The `n = 46` negative agrees with the proved theorem `R(5,5) <= 46`.
- The `n = 43` negative is informative in itself: it means the well-known 43-vertex construction is **not** circulant, so a more general family is required at that size.
- If a family is excluded at the target `n`, the productive move is to **generalise the family** (e.g. from cyclic to non-cyclic Cayley groups), not to search the same family harder.
