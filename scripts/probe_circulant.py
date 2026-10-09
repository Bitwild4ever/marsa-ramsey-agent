"""探测循环图族是否有产出：它到底能不能给出合法的 (s,t)-染色？

这是阶段 2 的**先决问题**。如果循环图族在中等 n 上根本没有合法染色，
那这个方向就直接死掉，不必投入；如果有，才值得往 n=45 推进
（那是一个逻辑上真能终结 R(5,5) 的目标）。

任何代价 0 的结果都用独立验证器复核。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.symmetric import (                                    # noqa: E402
    circulant_size, search_circulant, verify_bits,
)

RUNS = Path("D:/myagent/runs")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--nmin", type=int, default=28)
    ap.add_argument("--nmax", type=int, default=43)
    ap.add_argument("--s", type=int, default=5)
    ap.add_argument("--t", type=int, default=5)
    ap.add_argument("--tag", default="circulant_probe")
    args = ap.parse_args()

    print("=" * 88)
    print(f"循环图族探测  (s,t)=({args.s},{args.t})  预算={args.seconds}s/次  "
          f"seeds={args.seeds}")
    print("=" * 88)
    print(f"{'n':>4}{'自由比特':>10}{'空间大小':>14}{'最优违反度':>12}"
          f"{'平均':>8}{'解出':>6}{'验证':>12}{'评估次数':>12}")
    print("-" * 88)

    rows = []
    t_all = time.perf_counter()
    for n in range(args.nmin, args.nmax + 1):
        k = circulant_size(n)
        costs, evals, vok = [], [], False
        for seed in range(args.seeds):
            r = search_circulant(n, args.s, args.t, args.seconds, seed=seed)
            costs.append(r["cost"])
            evals.append(r["evals"])
            if r["cost"] == 0:
                good, _ = verify_bits(n, args.s, args.t, r["bits"])
                if good:
                    vok = True
        best = min(costs)
        vt = "verify=OK" if vok else ("-" if best > 0 else "FAIL")
        print(f"{n:>4}{k:>10}{2 ** k:>14,}{best:>12}"
              f"{statistics.mean(costs):>8.1f}"
              f"{'是' if best == 0 else '否':>6}{vt:>12}"
              f"{int(statistics.mean(evals)):>12,}")
        rows.append({"n": n, "bits": k, "best": best,
                     "mean": round(statistics.mean(costs), 2),
                     "solved": best == 0, "verified": vok,
                     "evals": int(statistics.mean(evals))})

    solved = [r["n"] for r in rows if r["solved"] and r["verified"]]
    print("-" * 88)
    if solved:
        print(f"循环图族能给出合法 (s,t)-染色的最大 n = {max(solved)}")
        print(f"  全部解出的 n: {solved}")
        print("  结论：族有产出，值得往 n=44/45 推进（n=45 成功即 R(5,5)=46）")
    else:
        print("循环图族在探测范围内**没有**给出任何合法染色")
        print("  结论：这个方向很可能死路，应换其他对称族（Cayley/双循环/覆盖构造）")
    print(f"\n总用时 {time.perf_counter() - t_all:.1f}s")
    out = RUNS / f"{args.tag}.json"
    out.write_text(json.dumps({"config": vars(args), "rows": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存: {out}")


if __name__ == "__main__":
    main()
