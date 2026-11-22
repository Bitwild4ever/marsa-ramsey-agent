<!--
{
  "name": "ramsey_prior",
  "handler": "ramsey_prior",
  "description": "Query the accumulated strategy prior: which search operator has historically been best for a given (n, s, t, budget) cell. Saves re-measuring the same comparison. Returns 'inconclusive' with recommended=null when evidence is thin or within seed noise.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "action": {"type": "string", "description": "recommend (default) or stats."},
      "n": {"type": "integer", "description": "Number of vertices. Required for recommend."},
      "s": {"type": "integer", "description": "Red clique size (default 5)."},
      "t": {"type": "integer", "description": "Blue clique size (default 5)."},
      "budget": {"type": "number", "description": "Wall-clock budget per run in seconds that the prior should match."},
      "min_samples": {"type": "integer", "description": "Minimum pooled samples per operator before recommending (default 3)."}
    },
    "required": ["action"]
  }
}
-->

# Tool: ramsey_prior

## Why this tool exists
Every `ramsey_compare` call automatically records its result into a strategy prior table. That
table is experience: "for `n=44`, `(5,5)`, 8-second budget, `tabu_focus` has beaten `sa` across
N samples". Querying it costs one call; re-measuring costs many runs.

This is the difference between an agent that **accumulates** judgement and one that restarts
from ignorance every session.

## Actions

| action | what it does |
|---|---|
| `recommend` | for a given cell, return the historically best operator (or explicitly nothing) |
| `stats` | overview: how many episodes, how many cells covered |

## The status values you must respect

| status | meaning | what you may do |
|---|---|---|
| `recommend` | margin exceeds the noise floor, or an operator has actually solved it | use `recommended` |
| `no_data` | this cell was never measured | measure it with `ramsey_compare`, or fall back to defaults |
| `too_few_samples` | pooled samples below `min_samples` | keep measuring; do not conclude |
| `inconclusive` | difference is within seed noise | **there is no recommendation**; `recommended` is null |
| `insufficient_operators` | only one operator recorded for this cell | nothing to compare |

`recommended: null` means **no recommendation exists**. Do not read the lowest mean out of the
`operators` field and act on it — that is exactly the over-generalisation the noise floor is
there to prevent.

## What the prior is not
- It is **not** transferable across `n`. The best operator at `n=44` need not be best at `n=45`.
  The cell key includes `n`, `s`, `t` and `budget`; a query for an unmeasured cell returns
  `no_data` even if other cells are well covered.
- It is **not** an existence claim. "`tabu_focus` is the best operator here" says nothing about
  whether a colouring exists.
- It is **not** permanent truth. More data can overturn an earlier recommendation; that is the
  table working correctly, not a contradiction.

## Usage pattern
1. Before spending budget on a comparison, call `ramsey_prior(action="recommend", n=..., budget=...)`.
2. If it returns `recommend`, use that operator and say the recommendation came from prior
   evidence rather than from fresh measurement.
3. If it returns `no_data` or `too_few_samples`, run `ramsey_compare` — that call feeds the table.
4. If it returns `inconclusive`, report no winner and say more seeds are needed.
