"""前沿探测：用当前最优算子把 (5,5) 的"能解出多大的 n"边界摸清楚。

这是报告里的主结果之一：智能体在不同规模上把违反度压到什么程度。
凡是代价 0 的结果，一律用**独立验证器**复核后才计入（verify=OK）。

背景：已知 43 <= R(5,5) <= 46。若能在某个 n 上构造出合法 (s,t)-染色，
就说明 R(5,5) > n。本脚本不指望刷新世界纪录，而是量化"我们的引擎能到哪"。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.search import SAConfig, TabuConfig, run_operator   # noqa: E402
from marsa.verifier import to_graph6, verify                  # noqa: E402

RUNS = Path("D:/myagent/runs")


def build(op: str, n: int, s: int, t: int, budget: float, seed: int):
    if op == "sa":
        return SAConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                        seed=seed, report_every=0, keep_elites=0)
    return TabuConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                      seed=seed, report_every=0, keep_elites=0,
                      candidate_mode="focus", candidate_size=128)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=20.0)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--op", default="tabu_focus")
    ap.add_argument("--s", type=int, default=5)
    ap.add_argument("--t", type=int, default=5)
    ap.add_argument("--nmin", type=int, default=34)
    ap.add_argument("--nmax", type=int, default=45)
    ap.add_argument("--tag", default="frontier")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    print("=" * 88)
    print(f"前沿探测  (s,t)=({args.s},{args.t})  算子={args.op}  "
          f"预算={args.budget}s/次  seeds={args.seeds}")
    print("=" * 88)
    print(f"{'n':>4}{'最优代价':>10}{'平均代价':>10}{'解出':>6}"
          f"{'验证':>12}{'用时/次':>10}")
    print("-" * 88)

    rows = []
    t_all = time.perf_counter()
    for n in range(args.nmin, args.nmax + 1):
        costs, vok, dts, g6 = [], False, [], ""
        for seed in range(args.seeds):
            t0 = time.perf_counter()
            res = run_operator(args.op, build(args.op, n, args.s, args.t,
                                              args.budget, seed))
            dts.append(time.perf_counter() - t0)
            costs.append(res.best_cost)
            if res.best_cost == 0:
                good, _ = verify(n, res.best_red, args.s, args.t)
                if good:
                    vok = True
                    g6 = to_graph6(n, res.best_red)
        best, mean = min(costs), statistics.mean(costs)
        vt = "verify=OK" if vok else ("-" if best > 0 else "verify=FAIL")
        print(f"{n:>4}{best:>10}{mean:>10.1f}{'是' if best == 0 else '否':>6}"
              f"{vt:>12}{sum(dts) / len(dts):>9.1f}s")
        rows.append({"n": n, "best": best, "mean": mean, "solved": best == 0,
                     "verified": vok, "graph6": g6,
                     "seconds": round(sum(dts) / len(dts), 3)})

    solved_ns = [r["n"] for r in rows if r["solved"] and r["verified"]]
    print("-" * 88)
    if solved_ns:
        print(f"能构造出合法 (s,t)-染色的最大 n = {max(solved_ns)}"
              f"（即实证 R({args.s},{args.t}) > {max(solved_ns)}）")
        print(f"  全部解出的 n: {solved_ns}")
    else:
        print("本轮没有解出任何 n（可加大预算或换算子）")
    out = RUNS / f"{args.tag}_{args.s}{args.t}.json"
    out.write_text(json.dumps({"config": vars(args), "rows": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"总用时 {time.perf_counter() - t_all:.1f}s   结果: {out}")


if __name__ == "__main__":
    main()
