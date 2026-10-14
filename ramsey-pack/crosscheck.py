"""交叉校验：两条**独立实现**的判定路径必须给出完全相同的合法解计数。

为什么要这个
------------
本项目所有"判定性结论"（`none_exist` / `exists`）都依赖判定函数的正确性。
一个漏判（少算了某类子集）会让"无解"变成假结论，而这种错误**不会**在
自我一致性检查里暴露出来 —— 错误的两条路径可以互相印证。

所以这里用一条**刻意不同**的实现来对照：

| | `marsa.symmetric.FastChecker` | `direct_checker.DirectChecker` |
|---|---|---|
| 掩码来源 | 只枚举含顶点 0 的子集（假定平移对称） | 枚举**全部** C(n,k) 个子集，不假设对称 |
| 判定写法 | `(S & M) == M` / `(S & M) == 0` | 独立的 `_subset_of` / `_disjoint` 位测试 |
| 优化 | 去重 + 按 bit_count 排序 + 红蓝合并 | 不做这些优化 |

同一份数学命题，三条实现差异。任何一处的实现错误都会让合法解计数不同。

再加一层**正向对照**：必须在某些 n 上真的找到解，否则"无解"可能只是
判定函数恒假的假象。

用法：
    python ramsey-pack/crosscheck.py                 # 默认几组
    python ramsey-pack/crosscheck.py --nmin 36 --nmax 41 --s 4 --t 6
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.symmetric import (                                    # noqa: E402
    FastChecker, circulant_red, circulant_size,
)
from marsa.verifier import to_graph6, verify                     # noqa: E402
from direct_checker import DirectChecker                         # noqa: E402


def crosscheck(n: int, s: int, t: int, cap: int = 40_000_000) -> dict:
    """全空间对比两条实现的合法解计数。"""
    total = 1 << circulant_size(n)
    if total > cap:
        return {"n": n, "s": s, "t": t, "skipped": True, "space": total}
    fast = FastChecker(n, s, t)
    direct = DirectChecker(n, s, t)

    t0 = time.perf_counter()
    n_fast = sum(1 for b in range(total) if fast.is_valid(b))
    t1 = time.perf_counter()
    n_direct = sum(1 for b in range(total) if direct.is_valid(b))
    t2 = time.perf_counter()

    return {
        "n": n, "s": s, "t": t, "space": total,
        "fast": n_fast, "direct": n_direct,
        "agree": n_fast == n_direct,
        "fast_seconds": round(t1 - t0, 2),
        "direct_seconds": round(t2 - t1, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nmin", type=int, default=None)
    ap.add_argument("--nmax", type=int, default=None)
    ap.add_argument("--s", type=int, default=4)
    ap.add_argument("--t", type=int, default=6)
    ap.add_argument("--cap", type=int, default=4_000_000,
                    help="单个 n 的空间上限，超过则跳过（默认 400 万，约 1 分钟内）")
    args = ap.parse_args()

    if args.nmin is not None and args.nmax is not None:
        tasks = [(n, args.s, args.t) for n in range(args.nmin, args.nmax + 1)]
    else:
        # 默认：一组混合了"有解"与"无解"的用例，含正向对照
        tasks = [(n, 4, 6) for n in (28, 30, 33, 34, 36, 38)]
        tasks += [(n, 5, 5) for n in (30, 38, 39)]

    print(f"{'n':>4}{'(s,t)':>8}{'空间':>13}{'FastChecker':>13}"
          f"{'DirectChecker':>15}{'一致':>7}{'耗时':>12}")
    print("-" * 74)
    ok = True
    positive = 0
    for n, s, t in tasks:
        r = crosscheck(n, s, t, cap=args.cap)
        if r.get("skipped"):
            print(f"{n:>4}{f'({s},{t})':>8}{r['space']:>13,}"
                  f"{'— 超过上限，跳过':>28}")
            continue
        mark = "OK" if r["agree"] else "!! 不一致"
        if not r["agree"]:
            ok = False
        if r["fast"] > 0:
            positive += 1
        print(f"{n:>4}{f'({s},{t})':>8}{r['space']:>13,}{r['fast']:>13,}"
              f"{r['direct']:>15,}{mark:>7}"
              f"{r['fast_seconds'] + r['direct_seconds']:>11.1f}s")

    print("-" * 74)
    print(f"含合法解的用例数（正向对照）：{positive}"
          f"{'  —— 判定函数不是恒假' if positive else '  !! 全部无解，正向对照缺失'}")
    # 正向用例里取一个有解的去独立验证器复核
    for n, s, t in tasks:
        fast = FastChecker(n, s, t)
        total = 1 << circulant_size(n)
        if total > args.cap:
            continue
        hit = next((b for b in range(total) if fast.is_valid(b)), None)
        if hit is not None:
            good, _w = verify(n, circulant_red(n, hit), s, t)
            print(f"独立验证器复核 n={n} 的首个解："
                  f"{'合法' if good else '不合法 !!'}")
            if not good:
                ok = False
            break
    print("\n结论：" + ("两条独立实现完全一致。" if ok else "存在不一致，必须排查。"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
