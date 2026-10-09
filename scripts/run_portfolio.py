"""阶段 1 主实验：算子组合的异构性检验 + 策略记忆 vs 最优固定算子。

用法：
    python scripts/run_portfolio.py --stage train      # 训练集网格（可断点续跑）
    python scripts/run_portfolio.py --stage heldout    # held-out 网格
    python scripts/run_portfolio.py --stage analyze    # 只做分析，不跑实验
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.benchmark import (                                   # noqa: E402
    DEFAULT_SEEDS, EXTENDED_TRAIN_INSTANCES, HELD_OUT_INSTANCES,
    TRAIN_INSTANCES, analyze, cells, load_results, run_grid,
)
from marsa.operators import default_portfolio                    # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="train",
                    choices=["train", "train_ext", "heldout", "analyze"])
    ap.add_argument("--budgets", default=None,
                    help="逗号分隔，如 0.5,3.0；默认用 benchmark 里的定义")
    ap.add_argument("--seeds", default=None, help="逗号分隔，如 0,1,2")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    policies = default_portfolio()
    budgets = ([float(x) for x in args.budgets.split(",")]
               if args.budgets else None)
    seeds = (tuple(int(x) for x in args.seeds.split(","))
             if args.seeds else DEFAULT_SEEDS)

    print(f"算子库 {len(policies)} 个；预算 {budgets or '默认'}；seeds {seeds}")

    if args.stage in ("train", "train_ext"):
        inst = (EXTENDED_TRAIN_INSTANCES if args.stage == "train_ext"
                else TRAIN_INSTANCES)
        label = "扩展训练集" if args.stage == "train_ext" else "训练集"
        cs = cells(inst, budgets) if budgets else cells(inst)
        print(f"\n【{label}网格】{len(cs)} 个单元 × {len(policies)} 个算子 "
              f"× {len(seeds)} seeds = {len(cs) * len(policies) * len(seeds)} 次运行")
        data = run_grid(policies, cs, seeds, verbose=not args.quiet)
        analyze(data, policies, cs, label)
    elif args.stage == "heldout":
        cs = (cells(HELD_OUT_INSTANCES, budgets) if budgets
              else cells(HELD_OUT_INSTANCES))
        print(f"\n【held-out 网格】{len(cs)} 个单元 × {len(policies)} 个算子 "
              f"× {len(seeds)} seeds")
        data = run_grid(policies, cs, seeds, verbose=not args.quiet)
        analyze(data, policies, cs, "held-out")
    else:
        data = load_results()
        budgets = budgets or [0.5, 3.0]
        analyze(data, policies, cells(TRAIN_INSTANCES, budgets),
                "训练集（来自缓存）")
        analyze(data, policies, cells(HELD_OUT_INSTANCES, budgets),
                "held-out（来自缓存）")


if __name__ == "__main__":
    main()
