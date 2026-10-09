"""候选表策略对比：能否把禁忌搜索的每步成本从 O(n^2) 降下来？

背景：禁忌搜索是 best-improvement，每步要评估全部 C(n,2) 条边，
步频随 n 迅速下降（n=46 时仅约 100 步/秒），成为扩展瓶颈。

三种候选表策略（同一墙钟预算下对比）：
    full    评估全部边（原版）
    sample  每步随机抽 m 条边
    focus   上一次移动两端点的关联边（活跃区）+ 随机补充
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.search import TabuConfig, run_tabu        # noqa: E402
from marsa.verifier import verify                    # noqa: E402


def run_one(n: int, s: int, t: int, mode: str, size: int, budget: float,
            seed: int = 1):
    cfg = TabuConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                     seed=seed, report_every=0, keep_elites=0,
                     candidate_mode=mode, candidate_size=size)
    t0 = time.perf_counter()
    res = run_tabu(cfg)
    dt = time.perf_counter() - t0
    ok = None
    if res.best_cost == 0:
        good, _ = verify(n, res.best_red, s, t)
        ok = "verify=OK" if good else "verify=FAIL"
    return res, dt, ok


def main() -> None:
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    combos = [("full", 0), ("sample", 32), ("sample", 128),
              ("focus", 64), ("focus", 128)]
    print("=" * 92)
    print(f"候选表策略对比  (s,t)=(5,5)  每个配置墙钟预算 {budget}s  seed=1")
    print("=" * 92)
    for n in (36, 43, 46):
        base_edges = n * (n - 1) // 2
        print(f"\nn={n}  (全部边数 C(n,2)={base_edges})")
        print(f"  {'策略':>14}{'候选/步':>10}{'步数':>10}{'步/秒':>10}"
              f"{'最优代价':>10}{'提速':>9}  验证")
        ref_rate = None
        for mode, size in combos:
            res, dt, ok = run_one(n, 5, 5, mode, size, budget)
            rate = res.steps_done / dt
            cand_per_step = base_edges if mode == "full" else size
            if mode == "full":
                ref_rate = rate
            speed = f"{rate / ref_rate:.1f}x" if ref_rate else "-"
            tag = (f"cand={cand_per_step}" if mode != "full" else "全部")
            print(f"  {mode + '/' + str(size) if mode != 'full' else 'full':>14}"
                  f"{tag:>10}{res.steps_done:>10,}{rate:>10,.0f}"
                  f"{res.best_cost:>10}{speed:>9}  {ok or ''}")
    print("\n" + "=" * 92)
    print("判读：要在同等时间内把代价压得更低，既要步频高，也要单步选得准。")


if __name__ == "__main__":
    main()
