"""VLNS 候选表 vs 活跃区候选表：多种子对比（n 在前沿最难的区间）。

单种子的方差很大（同一配置在不同 seed 下最优代价可差近一倍），
所以这里跑多个 seed 并同时报告 均值 / 最优 / 最差，用**均值**做主要判据。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.search import TabuConfig, run_operator      # noqa: E402
from marsa.verifier import to_graph6, verify           # noqa: E402

RUNS = Path("D:/myagent/runs")

CONFIGS = [
    ("focus/128", "focus", 128),
    ("violation/128", "violation", 128),
    ("violation/256", "violation", 256),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=15.0)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--ns", default="37,38,39,40,42,43")
    ap.add_argument("--s", type=int, default=5)
    ap.add_argument("--t", type=int, default=5)
    ap.add_argument("--tag", default="vlns")
    args = ap.parse_args()
    ns = [int(x) for x in args.ns.split(",")]

    print("=" * 92)
    print(f"VLNS vs 活跃区候选表  (s,t)=({args.s},{args.t})  "
          f"预算={args.budget}s  seeds={args.seeds}")
    print("=" * 92)
    out = {"config": vars(args), "rows": []}

    for n in ns:
        print(f"\nn={n}")
        print(f"  {'候选表':<16}{'均值':>9}{'最优':>8}{'最差':>8}{'解出':>7}"
              f"{'验证':>11}")
        row = {"n": n, "configs": {}}
        for label, mode, size in CONFIGS:
            vals, solved, vok, g6 = [], False, False, ""
            for seed in range(args.seeds):
                cfg = TabuConfig(n=n, s=args.s, t=args.t, steps=10 ** 9,
                                 max_seconds=args.budget, seed=seed,
                                 report_every=0, keep_elites=0,
                                 candidate_mode=mode, candidate_size=size)
                res = run_operator("tabu", cfg)
                vals.append(res.best_cost)
                if res.best_cost == 0:
                    solved = True
                    good, _ = verify(n, res.best_red, args.s, args.t)
                    if good:
                        vok = True
                        g6 = to_graph6(n, res.best_red)
            mean = statistics.mean(vals)
            vt = "verify=OK" if vok else ("-" if not solved else "FAIL")
            print(f"  {label:<16}{mean:>9.1f}{min(vals):>8}{max(vals):>8}"
                  f"{'是' if solved else '否':>7}{vt:>11}")
            row["configs"][label] = {
                "mean": round(mean, 2), "best": min(vals), "worst": max(vals),
                "values": vals, "solved": solved, "verified": vok,
                "graph6": g6,
            }
        out["rows"].append(row)

    print("\n" + "=" * 92)
    print("按均值汇总（相对 focus/128，负值表示更优）：")
    for label, _, _ in CONFIGS[1:]:
        deltas = []
        for row in out["rows"]:
            base = row["configs"]["focus/128"]["mean"]
            cur = row["configs"][label]["mean"]
            deltas.append(0.0 if base == 0 else (cur - base) / base * 100)
        m = statistics.mean(deltas)
        verdict = "更优" if m < -2 else ("更差" if m > 2 else "无显著差异")
        print(f"  {label:<16} 平均相对变化 {m:+6.2f}%  -> {verdict}")

    RUNS.mkdir(parents=True, exist_ok=True)
    p = RUNS / f"{args.tag}_results.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已保存: {p}")


if __name__ == "__main__":
    main()
