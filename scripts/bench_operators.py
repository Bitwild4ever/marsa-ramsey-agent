"""算子可扩展性测速：为规划器的算子选择提供依据。

关键在于两种算子的单步成本量级不同：
  * 退火：每步只评估 1 条边  -> O(1) 次团计数
  * 禁忌(best-improvement)：每步评估全部 C(n,2) 条边 -> O(n^2) 次团计数
因此随 n 增大，禁忌会迅速变得不可用，而退火仍可维持高步频。
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.search import SAConfig, TabuConfig, run_operator   # noqa: E402


def timeit(fn, *a, **k):
    t0 = time.perf_counter()
    res = fn(*a, **k)
    return time.perf_counter() - t0, res


def main() -> None:
    print("=" * 76)
    print("算子可扩展性（(5,5)，每步成本随 n 的变化）")
    print("=" * 76)
    print(f"{'n':>4}{'算子':>8}{'步数':>10}{'用时':>10}{'步/秒':>12}{'最优代价':>10}")
    print("-" * 76)
    for n in (24, 30, 36, 43, 46):
        for op, steps in (("sa", 100_000), ("tabu", 200)):
            cfg = (SAConfig(n=n, steps=steps, seed=1, report_every=0,
                            keep_elites=0)
                   if op == "sa" else
                   TabuConfig(n=n, steps=steps, seed=1, report_every=0,
                              keep_elites=0))
            dt, res = timeit(run_operator, op, cfg)
            print(f"{n:>4}{op:>8}{res.steps_done:>10,}{dt:>9.2f}s"
                  f"{res.steps_done / dt:>12,.0f}{res.best_cost:>10}")
    print("-" * 76)
    print("结论：禁忌每步要评估全部边，n 大时步频骤降；退火每步只评估一条边，")
    print("      步频基本与 n 无关。规划器应据 n 选择算子（这正是它的职责）。")


if __name__ == "__main__":
    main()
