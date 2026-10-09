"""策略层实验：自适应算子选择 vs 固定算子（同等墙钟预算）。

为什么用墙钟预算而不是步数预算
------------------------------
实测（scripts/bench_operators.py）表明两个算子的单步成本量级完全不同：
    sa   每步评估 1 条边       -> n=46 时约 6.3e4 步/秒
    tabu 每步评估 C(n,2) 条边  -> n=46 时约 1.1e2 步/秒
按步数比较会严重偏袒退火，所以必须按**时间**给预算，两种算子才可比。

三种策略：
    fixed-sa      全程退火
    fixed-tabu    全程禁忌
    adaptive      由策略记忆（UCB1，按规模分桶）自己选算子   <- 本方法
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.agent import AgentConfig, run_agent        # noqa: E402

TASKS = [(4, 4, 17), (4, 5, 24), (3, 7, 22), (5, 5, 30), (5, 5, 36), (5, 5, 43)]
RUNS = Path("D:/myagent/runs")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=1.2,
                    help="每个 episode 的墙钟秒数预算")
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--tag", default="suite")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    policies = [("fixed-sa", "sa", "scripted"),
                ("fixed-tabu", "tabu", "scripted"),
                ("adaptive", None, "adaptive")]

    print("=" * 88)
    print(f"策略层实验：自适应 vs 固定算子   "
          f"预算={args.budget}s/episode  episodes={args.episodes}  "
          f"seeds={args.seeds}")
    print("=" * 88)

    table: dict[str, dict[str, int]] = {}
    detail: dict[str, dict[str, list]] = {}
    t_all = time.perf_counter()

    for pname, forced_op, planner in policies:
        table[pname] = {}
        detail[pname] = {}
        for (s, t, n) in TASKS:
            key = f"({s},{t})@{n}"
            costs = []
            solved_any = False
            for seed in range(args.seeds):
                cfg = AgentConfig(
                    n=n, s=s, t=t, episodes=args.episodes, seed=seed,
                    log_path=str(RUNS / f"{args.tag}_{pname}_{s}{t}_{n}_s{seed}.jsonl"),
                    memory_path=str(RUNS / f"{args.tag}_{pname}_{s}{t}_{n}_s{seed}_mem.jsonl"),
                    strategy_path=str(RUNS / f"{args.tag}_{pname}_strategy_s{seed}.jsonl"),
                    planner=planner,
                    operator_override=forced_op,
                    seconds_override=args.budget,
                    memory_mode_override="none",
                )
                res = run_agent(cfg)
                costs.append(res.best_cost)
                solved_any = solved_any or res.solved_verified
            table[pname][key] = min(costs)
            detail[pname][key] = costs

    # ---- 报告 ----
    keys = [f"({s},{t})@{n}" for (s, t, n) in TASKS]
    print(f"\n{'实例':<16}", end="")
    for pname, _, _ in policies:
        print(f"{pname:>14}", end="")
    print(f"{'最优(任意策略)':>16}")
    print("-" * 88)
    best_overall = {}
    for key in keys:
        vals = [table[p][key] for p, _, _ in policies]
        best_overall[key] = min(vals)
        print(f"{key:<16}", end="")
        for pname, _, _ in policies:
            mark = "*" if table[pname][key] == best_overall[key] else " "
            print(f"{str(table[pname][key]) + mark:>14}", end="")
        print(f"{best_overall[key]:>16}")

    print("-" * 88)
    print("相对最优策略的平均差距（越小越好；0 表示该策略在每个实例上都是最好的）：")
    summary = {}
    for pname, _, _ in policies:
        gaps = []
        for key in keys:
            bo = best_overall[key]
            v = table[pname][key]
            gaps.append(0.0 if bo == 0 else (v - bo) / bo)
        mg = statistics.mean(gaps)
        summary[pname] = mg
        n_best = sum(1 for k in keys if table[pname][k] == best_overall[k])
        print(f"  {pname:<12} 平均相对差距={mg * 100:>7.2f}%   "
              f"取得最优的实例数={n_best}/{len(keys)}")

    # 自适应相对两个固定基线
    print("-" * 88)
    for base in ("fixed-sa", "fixed-tabu"):
        d = summary[base] - summary["adaptive"]
        verdict = "自适应更好" if d > 0 else ("持平" if d == 0 else "自适应更差")
        print(f"  adaptive vs {base}: 差距改善 {d * 100:+.2f} 个百分点 -> {verdict}")

    out = RUNS / f"{args.tag}_results.json"
    out.write_text(json.dumps({
        "config": vars(args), "table": table, "detail": detail,
        "best_overall": best_overall,
        "mean_gap": summary,
        "elapsed": time.perf_counter() - t_all,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("-" * 88)
    print(f"总用时 {time.perf_counter() - t_all:.1f}s   结果: {out}")


if __name__ == "__main__":
    main()
