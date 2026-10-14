---
name: search-operator-iteration
description: Improve the search strategy itself — propose, measure, and keep or discard operator variants under a fair protocol. Use when the goal is a better method rather than a better answer on one instance.
compatibility: Requires the deterministic ramsey_* tools (marsa engine).
allowed-tools: ramsey_search ramsey_violations ramsey_verify_construction query_memory record_failed_path record_solve_attempt read_runtime_file run_python_script search_knowledge
metadata:
  title: Search Operator Iteration
  category: installed
  tags: research,metaheuristics,evaluation,protocol
  skill-standard: agentskills.io/v1
---

# Search Operator Iteration

## Usage Hint
- Use this skill when the deliverable is a **better method** — a new operator, a new candidate-list rule, a new perturbation scheme — rather than a better answer on a single instance.
- Use it whenever you are about to claim that one search configuration is better than another.
- Do **not** use it to judge a single run. One run cannot support any comparative claim.
- Do **not** use step counts as a budget when comparing operators of different per-step cost.

## Summary
Measuring a method fairly is harder than inventing one, and most false claims in this area come from three specific mistakes: comparing across different budgets, trusting a single seed, and selecting on the same instances used to report. This skill fixes the protocol first, then iterates.

## Execution Steps
1. **Fix a wall-clock budget.** Give every configuration the same `budget_seconds`. This is not a detail: in this problem the per-step cost of different operators differs by about two orders of magnitude, so a step-count budget silently favours the cheaper operator and can invert the ranking.
2. **Run several seeds and compare means.** On these instances two seeds of the *same* configuration can differ by nearly 2x. Report the mean, and keep the spread. A single-seed comparison is not evidence.
3. **Separate selection from reporting.** Choose the winning configuration using one set of instances, then report its performance on **instances it was not selected on**. In this project the operator that looked best on the selection set was **not** the one that won on held-out instances — selection without a held-out set picks the wrong operator.
4. **Prefer several metrics, and don't let one dominate.** For an easy instance where the best cost is 1 and yours is 3, a "relative gap" metric reports a 100% miss on a difference of 2. Always report the median gap and a near-optimal rate alongside any mean, and check whether a single small-value instance is driving the mean.
5. **Beware degenerate selection.** If one configuration dominates on every instance, then adaptive selection among configurations **cannot** beat the best fixed choice — that is arithmetic, not a property of your method. Before concluding anything about a selection layer, verify that no single configuration dominates.
6. **Keep an improvement only if it survives the gate.** A candidate must (a) reproduce all existing checks and (b) beat the incumbent on the held-out set by more than the seed spread. Otherwise revert and record why.
7. **Record failures too.** A configuration that was worse, a hypothesis that was refuted, and a family of operators ruled out are all durable results. Use `record_failed_path`; use `record_solve_attempt` for a measured comparison that is worth keeping.

## What has actually worked here (use as priors, not as truths)
- **Shrinking the per-step candidate set** is the single largest measured win. Evaluating `C(n,2)` edges per move is what makes tabu search collapse at larger `n`; restricting each move to a small candidate set (a few hundred) raised the move rate by roughly 7-8x and lowered the best cost by 16-20% at `n = 43` and `n = 46`. Choosing *how* to build the candidate set mattered as much as its size: focusing on edges inside the currently violated cliques did better than focusing on edges near the last move, and the candidate *size* was a real hyperparameter (256 beat both 128 and 512).
- **Stall-triggered directed perturbation** (after many non-improving steps, flip a few edges taken from currently violated cliques, then clear the tabu state) improved the best tabu variant by about 7.6% at `n = 43`.
- **Re-storing past solutions and warm-starting from them made things worse**, in both a short and a long budget regime, and the mechanism was identified: the stored near-solutions were worse than what a fresh random restart reaches, so warm-starting anchored the search in a mediocre basin. Do not re-attempt solution-level memory without new evidence.

## Tool Calls
- `ramsey_search`: run one configuration at a fixed budget and seed.
- `ramsey_violations`: cheap exact reading of a candidate's quality.
- `ramsey_verify_construction`: confirm any apparent success before counting it.
- `record_solve_attempt` / `record_failed_path`: persist the comparison or the refutation.
- `run_python_script`: run a controlled sweep when many configurations must be compared.
- `query_memory`: check whether a configuration was already tried and rejected.

## Output Contract
- Report the protocol before the result: budget, number and values of seeds, selection set, held-out set.
- Report mean **and** spread. A bare best-of-N number is not a result.
- State explicitly when a comparison is inconclusive because the difference is within seed noise.
- Never report a selection-layer gain without first showing that no single configuration dominates.

## Notes
- A fairness rule from this project worth keeping: an automated gate should decide whether a candidate method is even allowed to compete. Requiring every candidate to pass the existing test suite before it is measured kept broken variants out of the comparison.
- When two configurations tie on the primary metric, prefer the one with the smaller spread; it is more likely to reproduce.
