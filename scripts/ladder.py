"""正确性阶梯：用**已知精确值**检验搜索引擎。

这些 Ramsey 数的精确值都已确定，因此对应的 (s,t)-染色**一定存在**：

    R(3,3)=6  -> n=5 必可解      R(3,4)=9  -> n=8 必可解
    R(3,5)=14 -> n=13 必可解     R(3,6)=18 -> n=17 必可解
    R(3,7)=23 -> n=22 必可解     R(4,4)=18 -> n=17 必可解
    R(4,5)=25 -> n=24 必可解

如果引擎在这些"必有解"的实例上都找不到代价 0，那它在 R(5,5) 上的任何
结果都没有意义。这是本项目最重要的工程门槛。
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.search import (                      # noqa: E402
    SAConfig, TabuConfig, run_operator,
)
from marsa.verifier import verify              # noqa: E402

LADDER = [
    (3, 3, 5), (3, 4, 8), (3, 5, 13), (3, 6, 17), (3, 7, 22),
    (4, 4, 17), (4, 5, 24),
]


def make_cfg(op: str, s, t, n, steps, seed):
    if op == "sa":
        return SAConfig(n=n, s=s, t=t, steps=steps, seed=seed,
                        report_every=0, keep_elites=0)
    return TabuConfig(n=n, s=s, t=t, steps=steps, seed=seed,
                      report_every=0, keep_elites=0)


def main(steps: int, seeds: list[int], ops: list[str]) -> None:
    for op in ops:
        print("=" * 82)
        print(f"已知精确值阶梯  算子={op}  steps={steps:,}  seeds={seeds}")
        print("=" * 82)
        print(f"{'实例':<16}{'n':>4}{'最优代价':>10}{'验证':>12}{'用时':>9}  说明")
        print("-" * 82)
        n_solved = 0
        for s, t, n in LADDER:
            best = None
            dt_all = 0.0
            verified = False
            for seed in seeds:
                t0 = time.perf_counter()
                res = run_operator(op, make_cfg(op, s, t, n, steps, seed))
                dt_all += time.perf_counter() - t0
                c = res.best_cost
                if best is None or c < best:
                    best = c
                if c == 0:
                    good, _ = verify(n, res.best_red, s, t)
                    verified = verified or good
            tag = "解出" if best == 0 else "未解出"
            vtag = ("verify=OK" if verified else "verify=-") if best == 0 else "-"
            n_solved += int(best == 0)
            print(f"({s},{t}){'':<10}{n:>4}{best:>10}{vtag:>12}"
                  f"{dt_all / len(seeds):>8.1f}s  {tag}")
        print("-" * 82)
        print(f"[{op}] 解出 {n_solved}/{len(LADDER)} 个必有解的实例")
        if n_solved < len(LADDER):
            print(f"[{op}] !! 未通过门槛")
        else:
            print(f"[{op}] 通过门槛")
        print()


if __name__ == "__main__":
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    op = sys.argv[2] if len(sys.argv) > 2 else "sa"
    seeds = [1, 2, 3]
    main(steps, seeds, [op])
