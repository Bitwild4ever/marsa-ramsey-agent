"""标定脚本：摸清模拟退火在 (5,5) 上的实际能力边界。

这决定了整个项目的迭代叙事：agent 要展示的正是"能推到多大的 n"这条曲线。
每个代价为 0 的结果都会用独立验证器复核，绝不凭搜索器自报。
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.search import SAConfig, run_sa      # noqa: E402
from marsa.verifier import verify              # noqa: E402


def probe(n: int, steps: int, seeds: list[int], s: int = 5, t: int = 5):
    rows = []
    for seed in seeds:
        t0 = time.perf_counter()
        res = run_sa(SAConfig(n=n, s=s, t=t, steps=steps, seed=seed,
                              report_every=0, keep_elites=0))
        dt = time.perf_counter() - t0
        checked = "-"
        if res.best_cost == 0:
            good, _ = verify(n, res.best_red, s, t)
            checked = "verify=OK" if good else "verify=!!FAIL!!"
        rows.append((seed, res.best_cost, res.steps_done, dt, checked))
    best = min(r[1] for r in rows)
    detail = "  ".join(f"seed{r[0]}:{r[1]}{'' if r[4] == '-' else ' ' + r[4]}"
                       for r in rows)
    print(f"  n={n:>2} (s,t)=({s},{t})  最快收敛={best:<5} {detail}  "
          f"[{rows[0][3]:.1f}s/次]")
    return best


if __name__ == "__main__":
    STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
    SEEDS = [1, 2]
    print("=" * 78)
    print(f"MARSA 能力边界标定  steps={STEPS:,}  seeds={SEEDS}")
    print("=" * 78)

    print("\n[对照组] 已知精确值，用于确认流水线正确")
    probe(24, STEPS, SEEDS, s=4, t=5)     # R(4,5)=25，故 n=24 必存在
    probe(35, STEPS, SEEDS, s=3, t=9)     # R(3,9)=36，故 n=35 必存在

    print("\n[(5,5) 主目标] 已知 43 <= R(5,5) <= 46，看能推到多大的 n")
    for n in (30, 34, 36, 38, 40, 41, 42, 43):
        probe(n, STEPS, SEEDS)

    print("\n[(4,6) 备用目标] 已知 35 <= R(4,6) <= 41")
    for n in (34, 35, 36):
        probe(n, STEPS, SEEDS, s=4, t=6)
