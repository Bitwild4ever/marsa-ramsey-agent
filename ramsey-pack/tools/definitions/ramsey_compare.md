<!--
{
  "name": "ramsey_compare",
  "handler": "ramsey_compare",
  "description": "Fairly compare two or more search operators under a fixed wall-clock budget and multiple seeds, and return an authoritative verdict on whether the winner is outside seed noise. Use this instead of eyeballing single runs.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "operators": {"type": "array", "items": {"type": "string"}, "description": "Two or more operator names to compare."},
      "n": {"type": "integer", "description": "Number of vertices."},
      "s": {"type": "integer", "description": "Red clique size (default 5)."},
      "t": {"type": "integer", "description": "Blue clique size (default 5)."},
      "budget": {"type": "number", "description": "Wall-clock budget per run in seconds (0.1-120)."},
      "seeds": {"type": "integer", "description": "Number of independent seeds per operator (2-12, default 3). More seeds give a more reliable noise estimate."},
      "seed_base": {"type": "integer", "description": "Base seed value so a run is reproducible."}
    },
    "required": ["operators", "n"]
  }
}
-->

# Tool: ramsey_compare

## Usage Hint
- Use this tool **whenever** you are about to state that one search configuration is better than another.
- Use it **instead of** eyeballing a few single runs, and **instead of** reporting one lucky seed.
- Do **not** use a single `ramsey_search` call to compare operators. One run cannot support any comparative claim; the noise between two seeds of the same configuration can approach 2x.
- Do **not** change or soften the `verdict` field when you report. It is a code-enforced judgment, not a hint.

## Why this tool exists
On these instances, the optimal-violation count varies substantially between two seeds of the **same** configuration. That means a naive "I ran it three times and A was lower, therefore A is better" is usually wrong. This tool makes that judgment **once, in code**, at the moment of measurement, so it cannot be rationalised away afterward.

## The verdict you must report
The tool returns `verdict` with one of three values:

| verdict | meaning | how you must report it |
|---|---|---|
| `solved` | A valid construction was found and independently verified | You may state the bound `R(s,t) > n`. |
| `clear_winner` | The margin between best and second-best **exceeds** the noise floor | You may state the relative ranking, labelled as a measurement, never as an existence claim. |
| `inconclusive_within_noise` | The margin **does not** exceed the noise floor | **You must report no winner.** State that the comparison is inconclusive and that separating them needs more seeds or a larger budget. |

The noise floor is the larger of the two operators' standard deviations. If `winner` is `null`, there is no winner — regardless of which mean happened to be lower.

## Returned fields
- `per_operator`: for each operator, its per-seed violation list plus `mean`, `median`, `std`, `min`, `max`, `range`.
- `margin`: difference of means between best and second-best.
- `noise_floor`: the larger standard deviation of those two.
- `verdict`, `winner` (null when inconclusive), `solved_operators`.
- `conclusion`: a pre-written sentence matching the verdict; copy its claim and its caveat.

## Notes
- The budget is **wall-clock**, not steps. Operators differ by about two orders of magnitude in per-step cost; a step budget would silently favour the cheaper one and can invert the ranking.
- Cost scales with `operators × seeds × budget`. Three operators at 8s and 3 seeds is about 72s. Choose the budget deliberately.
- When the verdict is `inconclusive_within_noise`, the productive next step is more seeds — not a different conclusion.
