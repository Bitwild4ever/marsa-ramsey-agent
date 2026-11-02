<!--
{
  "name": "cayley_enumerate",
  "handler": "cayley_enumerate",
  "description": "Exhaustively enumerate inverse-closed connection sets of an abelian Cayley group Z_a1 x Z_a2 ... and decide whether a valid (s,t)-colouring exists. This generalizes circulant enumeration (which only covers Z_n) to non-cyclic abelian groups.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "n": {
        "type": "integer",
        "description": "Number of vertices (the group order)."
      },
      "factors": {
        "type": "array",
        "items": {
          "type": "integer"
        },
        "description": "Prime-power decomposition of the group, e.g. [11,4] for Z_11 x Z_4, or [44] for Z_44."
      },
      "s": {
        "type": "integer",
        "description": "Red clique size (default 5)."
      },
      "t": {
        "type": "integer",
        "description": "Blue clique size (default 5)."
      },
      "limit": {
        "type": "integer",
        "description": "Skip if the space exceeds this many members."
      },
      "stop_at_first": {
        "type": "boolean",
        "description": "Stop at the first solution (default true). Set false to count all solutions."
      }
    },
    "required": []
  }
}
-->

# Tool: cayley_enumerate

Exhaustively enumerate inverse-closed connection sets of an abelian Cayley group Z_a1 x Z_a2 ... and decide whether a valid (s,t)-colouring exists. This generalizes circulant enumeration (which only covers Z_n) to non-cyclic abelian groups.

## Provenance
- 这个工具是 agent 自己在运行中写出来并注册的。
- 来源项目：`ramsey_agent_run`
- 注册前已通过它自己的测试；测试不通过则不会被注册。

## Usage Hint
**This tool is slow**: measured ~8,000 masks/s, about 250x slower than the engine. A space of 2^23 takes roughly 20 minutes. Always pass limit to guard against accidentally launching a huge space. For large spaces use the sharded driver rather than a single call. Validated against 5 anchors: Z_30 (5,5) exists; Z_33 (4,6) exactly 10 solutions; Z_34 (4,6) none; Z_28 (5,5) count matches the engine; abelian_groups(44) correct. Returns a dict with solutions_found, checked, elapsed_seconds, witness_connection_set.
