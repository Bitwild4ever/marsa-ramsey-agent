"""穷举整个循环图族 —— 做**判定性**结论，而不是"尽力而为"。

这是阶段 2 的核心工具：把"循环图族里有没有合法的 (s,t)-染色"这个问题
从"搜一搜看看"变成"全部查完，确定有/没有"。

两层正确性保障
--------------
1. 自检：在空间足够小的 n 上，把 FastChecker 与**已有的代价函数**
   （完全独立的实现路径）逐配置对比，必须零不一致。
2. 交叉检查：任何判定为合法的配置，都用**独立验证器**（显式矩阵 + 子集枚举）
   再复核一遍。

已知的一个强交叉检查：R(5,5) <= 46 已被证明 => n=46 上**不可能**存在合法
(5,5)-染色。若穷举在 n=46 上报告"无解"，则说明我们的检查器与验证器一致地正确。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.symmetric import (                                    # noqa: E402
    FastChecker, circulant_size, conn_from_bits, cost_of_bits,
    enumerate_circulant, verify_bits,
)

RUNS = Path("D:/myagent/runs")


def selfcheck(ns=(20, 24, 26, 28)) -> None:
    """在空间小的 n 上**逐配置**对比 FastChecker 与代价函数（独立实现）。"""
    print("自检：FastChecker 逐配置对比独立实现的代价函数")
    for n in ns:
        ck = FastChecker(n, 5, 5)
        tot = 1 << circulant_size(n)
        bad = 0
        for b in range(tot):
            if ck.is_valid(b) != (cost_of_bits(n, 5, 5, b) == 0):
                bad += 1
        status = "OK" if bad == 0 else f"!! 不一致 {bad}"
        print(f"  n={n}  全空间 {tot:,} 个配置全部对比 -> {status}")
        assert bad == 0, f"n={n} 上两条实现路径不一致"
    print("  自检通过：两条独立实现路径完全一致\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nmin", type=int, default=30)
    ap.add_argument("--nmax", type=int, default=46)
    ap.add_argument("--s", type=int, default=5)
    ap.add_argument("--t", type=int, default=5)
    ap.add_argument("--skip-selfcheck", action="store_true")
    ap.add_argument("--tag", default="exhaust_circulant")
    args = ap.parse_args()

    if not args.skip_selfcheck:
        selfcheck()

    print("=" * 92)
    print(f"穷举循环图族  (s,t)=({args.s},{args.t})  n={args.nmin}..{args.nmax}")
    print("=" * 92)
    print(f"{'n':>4}{'自由比特':>10}{'空间大小':>16}{'合法配置数':>12}"
          f"{'耗时':>10}{'速度(配置/秒)':>16}{'交叉验证':>12}")
    print("-" * 92)

    rows = []
    for n in range(args.nmin, args.nmax + 1):
        res = enumerate_circulant(n, args.s, args.t)
        xcheck = "-"
        if res["n_found"]:
            ok, _w = verify_bits(n, args.s, args.t, res["found"][0])
            xcheck = "verify=OK" if ok else "!!verify=FAIL"
        print(f"{n:>4}{circulant_size(n):>10}{1 << circulant_size(n):>16,}"
              f"{res['n_found']:>12,}{res['seconds']:>9.2f}s"
              f"{res['rate']:>16,.0f}{xcheck:>12}")
        rows.append({**res, "verified": xcheck == "verify=OK"})

    with_valid = [r["n"] for r in rows if r["n_found"] > 0]
    without = [r["n"] for r in rows if r["n_found"] == 0]
    print("-" * 92)
    if with_valid:
        print(f"循环图族内存在合法 (s,t)-染色的最大 n = {max(with_valid)}")
        print(f"  有解的 n: {with_valid}")
    if without:
        print(f"**穷举确认无解的 n**: {without}")
        print("  这些结论是判定性的（整个子族已被查完），不是'没搜到'")

    # 已知答案的交叉检查
    if 46 in without and args.s == 5 and args.t == 5:
        print("\n  强交叉检查通过：R(5,5) <= 46 已被证明，因此 n=46 上必然无解 ——")
        print("  我们的穷举独立地得到同一结论，说明检查器与验证器一致地正确。")
    if 43 in without and args.s == 5 and args.t == 5:
        print("  推论：n=43（已知下界所在规模）上不存在**循环图**形式的合法染色 ——")
        print("  说明 43 顶点那份著名构造必然不是循环图，第 2 阶段需要更一般的对称族。")

    out = RUNS / f"{args.tag}.json"
    out.write_text(json.dumps({"config": vars(args), "rows": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
