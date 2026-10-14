<!--
{
  "name": "ramsey_verify_construction",
  "handler": "ramsey_verify_construction",
  "description": "Decide by exact computation whether a given 2-colouring (graph6) is a valid (s,t)-construction, i.e. whether it proves R(s,t) > n. Uses an implementation independent of the search engine. This is a deterministic check, not an LLM review.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "n": {"type": "integer", "description": "Number of vertices in the construction."},
      "s": {"type": "integer", "description": "Red clique size to forbid (e.g. 5 for R(5,5))."},
      "t": {"type": "integer", "description": "Blue clique size to forbid (e.g. 5 for R(5,5))."},
      "graph6": {"type": "string", "description": "The red graph in graph6 format. The blue graph is its complement. Obtain this from ramsey_search or ramsey_enumerate_family, or construct it externally."},
      "project_slug": {"type": "string", "description": "Optional project scope for traceability."}
    },
    "required": ["n", "s", "t", "graph6"]
  }
}
-->

# Tool: ramsey_verify_construction

## Usage Hint
- Use this tool **before** treating any claimed Ramsey-style construction as established.
- Use it whenever a figure, a search run, or your own reasoning produces a concrete graph that is supposed to prove `R(s,t) > n`.
- Use it to settle the question by computation. **Do not** try to verify such a claim by reading the graph or by reasoning about it, and **do not** send it to `verify_correctness_computation` — that tool reviews proof prose with an LLM and cannot enumerate cliques.

## Why this tool exists
A claim like "this 43-vertex graph contains no K_5 and its complement contains no K_5" is a **computational** assertion. It is decided by exhaustive checking, not by review. The checker used here shares no code path with the search engine that produced the graph, so a bug in the searcher cannot silently validate itself.

## Returned fields
- `passed`: true only if the construction is valid.
- `overall_verdict`: `verified` | `refuted` | `invalid_input`.
- `violations`: exact count of monochromatic cliques (0 for a valid construction).
- `witness_clique`: when refuted, the specific vertex set that violates the claim.
- `conclusion`: a plain-language statement of what was decided.

## Interpretation
- `verified` ⇒ `R(s,t) > n` follows **immediately** from the definition. This is a rigorous lower-bound improvement.
- `refuted` ⇒ the construction proves nothing; inspect `witness_clique` and repair.
- `invalid_input` ⇒ the graph6 string was malformed or its vertex count disagrees with `n`.

## Notes
- Supported for `n <= 62` (graph6 limit).
- This tool never guesses and never returns "inconclusive". A verdict always exists.
