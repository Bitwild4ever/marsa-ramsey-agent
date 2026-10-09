"""跨规模算子矩阵：把三个算子在各个 n 上的表现一次性测出来并存档。

产出 scripts/../runs/matrix.json 与报告用图表，是报告里"算子对比"那张图的来源。
所有数字都在同一墙钟预算下取得，因此可比。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.search import SAConfig, TabuConfig, run_operator    # noqa: E402

RUNS = Path("D:/myagent/runs")
OUT = Path("D:/myagent/report/figures")


def build(op: str, n: int, s: int, t: int, budget: float, seed: int):
    if op == "sa":
        return SAConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                        seed=seed, report_every=0, keep_elites=0)
    mode = "focus" if op == "tabu_focus" else "full"
    return TabuConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                      seed=seed, report_every=0, keep_elites=0,
                      candidate_mode=mode, candidate_size=128)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--s", type=int, default=5)
    ap.add_argument("--t", type=int, default=5)
    args = ap.parse_args()

    ops = ["sa", "tabu", "tabu_focus"]
    ns = [18, 24, 30, 36, 43, 46, 50]
    data: dict[str, dict[str, int]] = {op: {} for op in ops}

    print("=" * 74)
    print(f"跨规模算子矩阵  (s,t)=({args.s},{args.t})  预算={args.budget}s  "
          f"seed={args.seed}")
    print("=" * 74)
    print(f"{'n':>4}" + "".join(f"{op:>14}" for op in ops) + f"{'胜者':>12}")
    print("-" * 74)
    for n in ns:
        row = {}
        for op in ops:
            res = run_operator(op, build(op, n, args.s, args.t,
                                         args.budget, args.seed))
            row[op] = res.best_cost
        for op in ops:
            data[op][n] = row[op]
        best = min(row.values())
        winners = [op for op in ops if row[op] == best]
        print(f"{n:>4}" + "".join(f"{row[op]:>14}" for op in ops)
              + f"{'/'.join(winners):>12}")

    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "matrix.json").write_text(json.dumps(
        {"config": vars(args), "operators": ops, "n": ns, "data": data},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已保存: {RUNS / 'matrix.json'}")

    # 出图
    from marsa.charts import line_chart
    OUT.mkdir(parents=True, exist_ok=True)
    labels = {"sa": "模拟退火 (sa)",
              "tabu": "禁忌搜索 (全量候选)",
              "tabu_focus": "候选表禁忌 (focus/128)"}
    series = [{"label": labels[op], "xs": ns,
               "ys": [data[op][n] for n in ns]} for op in ops]
    p = line_chart(OUT / "operator_matrix.png", series,
                   title="三种算子的跨规模对比（(5,5)，同等墙钟预算 3s）",
                   xlabel="n（顶点数）", ylabel="最优代价（越低越好，0=已解出）",
                   y_min_zero=True)
    print("已生成:", p)


if __name__ == "__main__":
    main()
