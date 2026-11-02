<!--
{
  "name": "ramsey_grow",
  "handler": "ramsey_grow",
  "description": "Register a tool you wrote into permanent capability so future runs can call it natively instead of rewriting it. Also lists registered tools and scans the workspace for unregistered scripts. Registration is REFUSED unless the tool has a passing test.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "action": {"type": "string", "description": "One of: register, list, unregister, harvest."},
      "name": {"type": "string", "description": "Tool name (lowercase, 3-48 chars). Required for register/unregister."},
      "source": {"type": "string", "description": "Path to the implementation .py, usually relative to workspace/."},
      "test": {"type": "string", "description": "Path to its test file. REQUIRED for register; registration fails without it."},
      "entry": {"type": "string", "description": "Entry function name in the implementation, default 'run'."},
      "description": {"type": "string", "description": "One-line description shown to future runs."},
      "parameters": {"type": "object", "description": "JSON-Schema properties dict describing the tool's own arguments."},
      "hints": {"type": "string", "description": "Markdown usage hints for the next run."},
      "timeout": {"type": "integer", "description": "Test timeout in seconds, default 120."}
    },
    "required": ["action"]
  }
}
-->

# Tool: ramsey_grow

## Why this tool exists
You write useful code during a run. Historically that code stayed in `workspace/` and was
**invisible to every later run** — the agent wrote 11 scripts and got zero capability gain,
because the next run started from scratch. This tool closes that loop.

After `register`, the tool becomes a **native tool** available in every future run, with its
own name, so you never rewrite it again. That is what "self-extension" means concretely.

## The one hard rule
**No test -> no registration.**

Registration requires a `test` path, and that test must exit 0. This is not a formality.
An unverified self-written tool is worse than no tool: it produces plausible wrong answers
and those answers propagate into every later run, where they are very hard to trace back.

So the workflow is: **write the tool, write its test, make the test pass, then register.**

A good test compares your implementation against something you already trust — for example
your enumerator against `ramsey_enumerate_family` on instances where that tool is a known
anchor (`n=38` must be `exists`; `n=43/44/45/46` must be `none_exist` for circulant `(5,5)`).
A unit test that only checks "it runs without crashing" is not enough.

## Actions

| action | what it does | required args |
|---|---|---|
| `harvest` | scan `workspace/` and report which `.py` files are unregistered, and whether each has a test | — |
| `register` | validate and register one tool | `name`, `source`, `test` |
| `list` | show currently registered tools | — |
| `unregister` | remove a tool | `name` |

Start with `harvest` to see what you already wrote this run.

## What makes a good registration
- `entry`: point at a single, stable function. Give it plain arguments (`n`, `s`, `t`, `limit`),
  not framework objects, so future runs can call it without knowing this run's context.
- `description`: write it for a reader who has no memory of this run. Say what it computes
  and when to use it instead of the built-in tools.
- `parameters`: describe your own arguments as JSON-Schema properties.
- `hints`: record what you learned — its cost, its limits, when it beats the built-ins.

## Reporting
When you register something, say so explicitly in your report: which tool, what it does, and
that it is now available to future runs. That is the evidence that capability is accumulating
rather than resetting.
