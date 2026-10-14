<!--
{
  "name": "ramsey_search",
  "handler": "ramsey_search",
  "description": "Run one bounded local-search attempt at a Ramsey-style construction. Returns the best violation count found and, when the search reports success, the concrete graph6 after independent verification. Search output is never trusted without that verification.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "n": {"type": "integer", "description": "Number of vertices to attempt."},
      "s": {"type": "integer", "description": "Red clique size to avoid (default 5)."},
      "t": {"type": "integer", "description": "Blue clique size to avoid (default 5)."},
      "operator": {"type": "string", "enum": ["sa", "tabu", "tabu_focus", "tabu_sample", "tabu_violation"], "description": "Which search operator to use. tabu_focus is the strongest general default; tabu_violation is competitive on larger n."},
      "budget_seconds": {"type": "number", "description": "Wall-clock budget for this attempt (0.1 to 600). Fixed budget is what makes different attempts comparable."},
      "seed": {"type": "integer", "description": "Random seed. Run several seeds before drawing conclusions: on these instances a single seed can differ from another by nearly 2x."}
    },
    "required": ["n"]
  }
}
-->

# Tool: ramsey_search

## Usage Hint
- Use this tool to make **progress measurements**: how low can the violation count be pushed at a given `n` within a fixed budget.
- Use it when you need a candidate construction to hand to `ramsey_verify_construction`.
- Use it when comparing two search strategies on equal footing (same `n`, same `budget_seconds`, several `seed` values).

## What it does
Runs a local search that repeatedly flips edge colours to reduce the number of monochromatic cliques. Two facts matter:

1. **The budget is wall-clock, not step count.** Different operators have per-step costs that differ by two orders of magnitude, so a step budget would silently favour the cheap operator.
2. **A claimed success is re-checked.** If the search reports zero violations, this tool immediately re-verifies the graph with the independent checker. `passed` is true only if that check agrees.

## Returned fields
- `violations`: best violation count reached (0 means a valid construction was found).
- `init_violations`: violation count of the random starting point.
- `graph6`: present only when a solution was found; feed it to `ramsey_verify_construction`.
- `independent_verification`: whether the checker confirmed the search's claim.
- `steps`, `elapsed_seconds`: effort actually spent.
- `conclusion`: plain-language reading of the outcome.

## Interpretation
- `overall_verdict = "solved"` ⇒ a valid construction exists at this `n`; `R(s,t) > n` follows once `ramsey_verify_construction` confirms it.
- `overall_verdict = "unsolved"` ⇒ **only** that this budget was insufficient. It is **not** evidence that no construction exists.
- `overall_verdict = "verification_failed"` ⇒ the search misreported. Treat that operator's output as unreliable and report the discrepancy.

## Notes
- Prefer several seeds and compare the mean, not the single best result.
- For small `n`, `ramsey_enumerate_family` gives a decision instead of a best effort; prefer it there.
