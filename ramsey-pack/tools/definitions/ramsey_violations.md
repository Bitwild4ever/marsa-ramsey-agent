<!--
{
  "name": "ramsey_violations",
  "handler": "ramsey_violations",
  "description": "Count exactly how many monochromatic cliques a given colouring contains: red K_s plus blue K_t. Zero means the colouring is a valid (s,t)-construction. Cheap deterministic measurement.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "n": {"type": "integer", "description": "Number of vertices."},
      "s": {"type": "integer", "description": "Red clique size (default 5 for R(5,5))."},
      "t": {"type": "integer", "description": "Blue clique size (default 5 for R(5,5))."},
      "graph6": {"type": "string", "description": "The red graph in graph6 format."}
    },
    "required": ["n", "s", "t", "graph6"]
  }
}
-->

# Tool: ramsey_violations

## Usage Hint
- Use this tool for a **cheap quantitative reading** of a candidate colouring: how far is it from valid.
- Use it to compare two candidate graphs, or to track whether a repair step actually reduced the obstruction.
- Use `ramsey_verify_construction` instead when the question is the yes/no verdict.

## What "violations" means
The count of monochromatic cliques that a valid construction must avoid:

```
violations = (# red K_s) + (# blue K_t)
```

This is the natural objective for search: it is zero exactly when the colouring is valid. It is computed exactly, and it is the same quantity the search engine minimises — so a drop in this number is genuine progress, not a change of metric.

## Returned fields
- `violations`: the exact count.
- `overall_verdict`: `zero` when valid, `nonzero` otherwise.
- `passed`: true iff `violations == 0`.

## Notes
- `violations = 0` still deserves `ramsey_verify_construction` before being treated as a result; that tool uses an independent implementation and is the one that decides.
- Small values (1-5) mean the colouring is close but not valid. Closing the last few violations is qualitatively harder than reducing a large count, so do not extrapolate from a low number to "almost solved".
