"""ramsey-pack 命令行工具 —— 不调用任何大模型，四个确定性动作。

用法示例：
    python ramsey-pack/cli.py frontier
    python ramsey-pack/cli.py enumerate --n 40
    python ramsey-pack/cli.py search    --n 34 --budget 3 --operator tabu_focus
    python ramsey-pack/cli.py verify    --n 34 --graph6 "...."
    python ramsey-pack/cli.py sweep     --nmin 36 --nmax 44      # 逐 n 穷举

加 `--json` 输出完整结构化结果（供程序或 agent 解析）。
加 `--quiet` 只打印一行结论。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows 控制台默认代码页常常是 GBK，打印 ⇒ 之类的字符会抛 UnicodeEncodeError。
# 这是纯输出层问题，但会让整个命令失败，所以在最前面把标准流切到 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.ops import (                                       # noqa: E402
    OPERATORS, enumerate_family, search, verify_construction, violations,
)

FRONTIER = {
    "R(5,5)": dict(lower=43, upper=46, open_targets=[44, 45]),
    "R(4,6)": dict(lower=35, upper=41, open_targets=[36]),
}


def show(res: dict, args) -> int:
    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif getattr(args, "quiet", False):
        print(f"{res.get('status')}: {res.get('conclusion','')}")
    else:
        badge = {"exists": "[解存在]", "none_exist": "[判定无解]",
                 "solved": "[已解出]", "unsolved": "[未解出]",
                 "verified": "[验证通过]", "refuted": "[验证否决]",
                 "zero": "[合法]", "nonzero": "[不合法]",
                 "verification_failed": "[验证失败]", "error": "[错误]"}
        print(badge.get(res.get("status"), ""), res.get("conclusion", ""))
        keys = [k for k in ("n", "s", "t", "family", "free_parameters", "space",
                            "solutions", "violations", "init_violations",
                            "seconds", "steps", "operator", "seed",
                            "verified", "exhaustive")
                if k in res and res[k] is not None]
        if keys:
            print("   " + "  ".join(f"{k}={res[k]}" for k in keys))
        if res.get("graph6"):
            print(f"   graph6 = {res['graph6']}")
        if res.get("connection_set"):
            print(f"   connection_set = {res['connection_set']}")
    return 0 if res.get("ok") else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="ramsey", description="MARSA 确定性工具")
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出一行结论")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("frontier", help="打印已知边界与开放靶子")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")

    for name, helptext in (("enumerate", "穷举循环图族（判定性）"),
                           ("search", "固定预算搜索（尽力而为）")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--n", type=int, required=True)
        p.add_argument("--s", type=int, default=5)
        p.add_argument("--t", type=int, default=5)
        if name == "search":
            p.add_argument("--operator", default="tabu_focus",
                           choices=list(OPERATORS))
            p.add_argument("--budget", type=float, default=5.0)
            p.add_argument("--seed", type=int, default=0)
        p.add_argument("--json", action="store_true")
        p.add_argument("--quiet", action="store_true")

    for name in ("verify", "violations"):
        p = sub.add_parser(name, help="验证 / 统计违反度")
        p.add_argument("--n", type=int, required=True)
        p.add_argument("--s", type=int, default=5)
        p.add_argument("--t", type=int, default=5)
        p.add_argument("--graph6", required=True)
        p.add_argument("--json", action="store_true")
        p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("sweep", help="对一段 n 逐个穷举")
    p.add_argument("--nmin", type=int, required=True)
    p.add_argument("--nmax", type=int, required=True)
    p.add_argument("--s", type=int, default=5)
    p.add_argument("--t", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")

    args = ap.parse_args()

    if args.cmd == "frontier":
        if args.json:
            print(json.dumps(FRONTIER, ensure_ascii=False, indent=2))
        else:
            for name, d in FRONTIER.items():
                print(f"{name}:  {d['lower']} <= {name} <= {d['upper']}"
                      f"   开放靶子: "
                      f"{', '.join('n='+str(x) for x in d['open_targets'])}")
            print("\n注：R(5,5) >= 43 意味着 43 顶点的合法染色**存在**，"
                  "删点保持合法性，")
            print("    故 n <= 43 全部存在 —— 真正开放的只有 n = 44 和 45。")
            print("    n = 46 上必然无解（与已证明上界一致），可作工具链自检。")
        return 0

    if args.cmd == "enumerate":
        return show(enumerate_family(args.n, args.s, args.t), args)
    if args.cmd == "search":
        return show(search(args.n, args.s, args.t, args.operator,
                           args.budget, args.seed), args)
    if args.cmd == "verify":
        return show(verify_construction(args.n, args.s, args.t, args.graph6), args)
    if args.cmd == "violations":
        return show(violations(args.n, args.s, args.t, args.graph6), args)

    if args.cmd == "sweep":
        rows = []
        any_exists = None
        for n in range(args.nmin, args.nmax + 1):
            res = enumerate_family(n, args.s, args.t)
            rows.append(res)
            if res.get("solutions"):
                any_exists = max(any_exists or 0, n)
            if not args.quiet and not args.json:
                show(res, args)
            elif args.quiet:
                print(f"n={n:<3} {res.get('status'):<10} "
                      f"solutions={res.get('solutions')}")
        if args.json:
            print(json.dumps({"sweep": rows}, ensure_ascii=False, indent=2))
        elif not args.quiet:
            found = [r["n"] for r in rows if r.get("solutions")]
            none = [r["n"] for r in rows if r.get("status") == "none_exist"]
            print(f"\n汇总：有解 n = {found}")
            print(f"      判定性无解 n = {none}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
