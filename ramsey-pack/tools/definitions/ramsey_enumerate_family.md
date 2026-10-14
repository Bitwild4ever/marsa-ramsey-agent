<!--
{
  "name": "ramsey_enumerate_family",
  "handler": "ramsey_enumerate_family",
  "description": "Exhaustively enumerate a structured family of colourings (currently the circulant family on Z_n) and decide whether any member is a valid (s,t)-construction. Produces a decision, not a best effort.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "n": {"type": "integer", "description": "Number of vertices."},
      "s": {"type": "integer", "description": "Red clique size to avoid (default 5)."},
      "t": {"type": "integer", "description": "Blue clique size to avoid (default 5)."},
      "family": {"type": "string", "enum": ["circulant"], "description": "Which structured family to enumerate. Currently only 'circulant'."}
    },
    "required": ["n", "s", "t"]
  }
}
-->

# Tool: ramsey_enumerate_family

## Usage Hint
- Use this tool when you want a **decision** about a structured family rather than an inconclusive search result.
- Use it to rule a family in or out before spending budget searching inside it.
- Use it when a search inside the family kept stalling and you need to know whether a solution exists there at all.

## Why this is stronger than searching
A circulant colouring is determined by a connection set on `Z_n`, so it has only `floor(n/2)` free binary parameters — for `n = 43` that is 21 bits, about 2.1 million members. By reducing the validity test to a few bit operations, that entire space can be **checked exhaustively in seconds**.

Consequently the answer carries a different epistemic status from `ramsey_search`:

| outcome | meaning |
|---|---|
| `exists` | a valid construction was found **and** independently verified |
| `none_exist` | **no** member of the family works — the whole family is ruled out |

`none_exist` is a decision about a family, not a failed attempt. Use it to close off a line of attack permanently.

## Returned fields
- `solutions_found`: how many members of the family are valid.
- `space_size`, `free_parameters`: the size of the space that was fully checked.
- `exhaustive`: always true for this tool.
- `example.connection_set`, `example.graph6`: a concrete witness when one exists.
- `independent_verification`: whether the checker confirmed the witness.
- `conclusion`: plain-language statement, including the negative case.

## Interpretation
- `exists` ⇒ `R(s,t) > n`, rigorously.
- `none_exist` ⇒ this family cannot prove `R(s,t) > n`. Record it as a failed path so the effort is not repeated, and move to a more general family.

## Notes
- Refuses spaces above ~40 million members rather than running unboundedly.
- A negative result here says nothing about unstructured colourings; the general problem stays open.
