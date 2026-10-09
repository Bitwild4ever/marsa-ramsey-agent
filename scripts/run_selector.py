"""阶段 1 的判决实验：按情形选择的组合选择器 vs 事后最优的固定算子。

协议
----
* **学习**：只在训练集单元上模拟 agent 的经验积累（UCB1，按（规模档, 预算档）分桶，
  刻意不按 (s,t) 分桶，逼迫它泛化到不同的问题形状）。
* **评估**：在 **held-out** 单元上纯利用（greedy），只看选中的那个算子的实际表现。
* **判据**：平均相对差距（相对每个单元里所有算子的最优值）。越低越好，0 = 每个单元都最优。

收益定义
--------
reward(算子在单元上的表现) = 1 - 代价 / 该单元所有算子的平均代价。

用"该单元的平均代价"作参考点，是为了让不同规模的单元对决策有可比权重
（否则 n=36 的单元收益都接近 1，会把 n=43 的信号淹没）。这个参考点
**不泄露哪个算子更好**，只做归一化。

对照基线
--------
1. **oracle 最优固定算子（held-out）**：在 held-out 上挑最好的单一算子 —— 这是
   固定策略的理论上限，赢它才算真正的"按情形选择"优势。
2. **训练集最优固定算子**：按训练集表现挑一个，再拿到 held-out 上跑 —— 这是
   现实中不用记忆会采用的做法，也是最公平的对照。
3. **全体平均**：随机挑一个算子的期望水平。
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.benchmark import (                                   # noqa: E402
    BUDGETS, DEFAULT_SEEDS, HELD_OUT_INSTANCES, TRAIN_INSTANCES,
    Cell, cells, load_results,
)
from marsa.operators import default_portfolio                    # noqa: E402
from marsa.selector import PortfolioSelector                     # noqa: E402


def bucket_of(cell: Cell) -> str:
    """情形分桶：（规模档, 预算档）。刻意不含 (s,t)，逼迫跨问题形状泛化。"""
    nb = "small" if cell.inst.n <= 38 else "large"
    bb = "short" if cell.budget <= 1.0 else "long"
    return f"{nb}|{bb}"


def expected_init_cost(n: int, s: int, t: int) -> float:
    """随机二染色的期望单色团数（仅用于说明，本脚本的收益用单元内均值归一化）。"""
    e = 0.0
    if s >= 2:
        e += comb(n, s) / (2 ** comb(s, 2))
    if t >= 2:
        e += comb(n, t) / (2 ** comb(t, 2))
    return max(1.0, e)


def build_matrix(data: dict, policies: list[str],
                 cell_list: list[Cell]) -> dict[str, dict[str, float]]:
    mat: dict[str, dict[str, float]] = {}
    for c in cell_list:
        row = {}
        for p in policies:
            rec = data["runs"].get(f"{p}|{c.key}")
            if rec:
                row[p] = rec["mean"]
        if row:
            mat[c.key] = row
    return mat


def rewards_of(mat: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for ck, row in mat.items():
        ref = statistics.mean(row.values()) or 1.0
        out[ck] = {p: 1.0 - v / ref for p, v in row.items()}
    return out


def gap_of(cost: float, best: float) -> float:
    return (cost - best) / max(1.0, best)


def avg_gap(mat: dict[str, dict[str, float]], policy: str,
            keys: list[str]) -> float:
    """算子在给定单元集合上的平均相对差距。

    网格可能是**不完整**的（长实验分批跑、断点续跑），因此缺少该算子数据的
    单元一律跳过，而不是报错。
    """
    gs = []
    for ck in keys:
        row = mat.get(ck)
        if not row or policy not in row:
            continue
        gs.append(gap_of(row[policy], min(row.values())))
    return statistics.mean(gs) if gs else float("inf")


def candidates_present(mat: dict[str, dict[str, float]],
                       keys: list[str]) -> list[str]:
    """只保留在**每个**给定单元里都有数据的算子，保证基线之间可比。"""
    if not mat:
        return []
    common = set(mat[keys[0]])
    for ck in keys[1:]:
        common &= set(mat.get(ck, {}))
    return sorted(common)


def main() -> None:
    data = load_results()
    policies = [p.name for p in default_portfolio()]
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else None
    bs = [budget] if budget else list(BUDGETS)

    train_cells = [c for c in cells(TRAIN_INSTANCES, bs)]
    held_cells = [c for c in cells(HELD_OUT_INSTANCES, bs)]
    mtr = build_matrix(data, policies, train_cells)
    mhe = build_matrix(data, policies, held_cells)
    if not mtr or not mhe:
        print("!! 训练集或 held-out 网格数据缺失，请先跑 --stage train / --stage heldout")
        print(f"   训练单元可用: {len(mtr)}/{len(train_cells)}，"
              f"held-out 可用: {len(mhe)}/{len(held_cells)}")
        return

    rew = rewards_of(mtr)
    train_keys = list(mtr)
    held_keys = list(mhe)

    # 只在"两套单元上都有完整数据"的算子里做比较，保证基线与自适应可比
    full_train = candidates_present(mtr, train_keys)
    full_held = candidates_present(mhe, held_keys)
    both = sorted(set(full_train) & set(full_held))
    if not both:
        print("!! 没有算子在训练集与 held-out 上都有完整数据，无法比较")
        print(f"   训练集完整算子 {len(full_train)} 个，"
              f"held-out 完整算子 {len(full_held)} 个")
        return

    print("=" * 84)
    print(f"组合选择器判决实验   预算档={bs}   "
          f"训练单元={len(train_keys)}  held-out 单元={len(held_keys)}")
    print(f"在两套单元上都完整的算子：{len(both)}/{len(policies)}")
    print("=" * 84)

    # ---- 学习阶段：只在训练集上积累经验 ----
    sel = PortfolioSelector(explore_c=1.0)
    rng = random.Random(20261009)
    ROUNDS = 60
    for rnd in range(ROUNDS):
        for c in train_cells:
            if c.key not in rew:
                continue
            pick, _why = sel.choose(bucket_of(c), both, rng)
            sel.observe(bucket_of(c), pick, rew[c.key][pick])
    print(f"\n学习完成：{ROUNDS} 轮 × {len(train_cells)} 个训练单元"
          f"（共 {ROUNDS * len(train_cells)} 次观测）")
    print("\n各桶学到的前 3 名（按平均收益）：")
    for b in sorted(sel.arms):
        ranked = sorted(sel.arms[b].items(), key=lambda kv: -kv[1].mean)[:3]
        cells_in = sorted({bucket_of(c) for c in train_cells if
                           bucket_of(c) == b})
        print(f"  桶 {b}  (训练单元: "
              f"{[c.key for c in train_cells if bucket_of(c) == b]})")
        for p, a in ranked:
            print(f"      {p:<30} 收益 {a.mean:>9.5f}  次数 {a.pulls}")

    # ---- 评估阶段：held-out 上纯利用 ----
    print("\n" + "-" * 84)
    print("held-out 上纯利用（greedy）的结果：")
    print(f"{'单元':<18}{'选中算子':<30}{'代价':>9}{'单元最优':>9}{'差距':>9}")
    print("-" * 84)
    adaptive_gaps = []
    skipped = 0
    for c in held_cells:
        row = mhe.get(c.key)
        if not row:
            skipped += 1
            continue
        b = bucket_of(c)
        pick = sel.greedy(b, both)
        if pick is None or pick not in row:
            # 桶内无经验就不评这个单元 —— 不用单元最优去"兜底"，那会虚高成绩
            skipped += 1
            print(f"{c.key:<18}{'(桶内无经验，跳过)':<30}")
            continue
        best = min(row.values())
        g = gap_of(row[pick], best)
        adaptive_gaps.append(g)
        print(f"{c.key:<18}{pick:<30}{row[pick]:>9.1f}{best:>9.1f}"
              f"{g * 100:>8.2f}%")

    if not adaptive_gaps:
        print("\n!! 没有任何 held-out 单元可以评估（桶内均无经验），无法判决")
        return
    adaptive = statistics.mean(adaptive_gaps)
    if skipped:
        print(f"（跳过了 {skipped} 个单元）")

    # ---- 基线 ----
    oracle_fixed = min(both, key=lambda p: avg_gap(mhe, p, held_keys))
    oracle_fixed_gap = avg_gap(mhe, oracle_fixed, held_keys)
    train_best = min(both, key=lambda p: avg_gap(mtr, p, train_keys))
    train_fixed_gap = avg_gap(mhe, train_best, held_keys)
    all_policy_gaps = [avg_gap(mhe, p, held_keys) for p in both]
    mean_all = statistics.mean(all_policy_gaps)
    median_all = statistics.median(all_policy_gaps)

    print("-" * 84)
    print(f"{'策略':<44}{'held-out 平均相对差距':>22}")
    print("-" * 84)
    print(f"{'① 按情形选择（本方法）':<40}{adaptive * 100:>20.2f}%")
    print(f"{'② oracle 最优固定算子':<40}{oracle_fixed_gap * 100:>20.2f}%"
          f"   <- 固定策略上限")
    print(f"{'   即 ' + oracle_fixed:<40}")
    print(f"{'③ 训练集最优固定算子（最公平对照）':<40}"
          f"{train_fixed_gap * 100:>20.2f}%")
    print(f"{'   即 ' + train_best:<40}")
    print(f"{'④ 全部算子平均':<40}{mean_all * 100:>20.2f}%")
    print(f"{'⑤ 全部算子中位数':<40}{median_all * 100:>20.2f}%")
    print("-" * 84)

    verdicts = []
    if adaptive < train_fixed_gap:
        d = (train_fixed_gap - adaptive) / max(1e-9, train_fixed_gap) * 100
        verdicts.append(f"优于『训练集最优固定算子』{d:.1f}%")
    else:
        verdicts.append("未优于『训练集最优固定算子』")
    if adaptive < oracle_fixed_gap:
        verdicts.append("甚至优于『oracle 最优固定算子』（说明按情形选择确有价值）")
    else:
        verdicts.append("未超过『oracle 最优固定算子』")
    print("判读：" + "；".join(verdicts))

    # ---- 稳健性：换几种度量再看一遍 ----
    # 平均相对差距会被"数值很小的单元"放大（例如 (4,5)@24 上 1.3 与 2.7 之差
    # 会算成 100% 差距）。因此必须用多种度量交叉验证结论是否稳健。
    def profile(pick_fn, label: str) -> dict:
        rel, norm, ranks, within5 = [], [], [], []
        for c in held_cells:
            row = mhe.get(c.key)
            if not row:
                continue
            pick = pick_fn(c)
            if pick is None or pick not in row:
                continue
            best = min(row.values())
            med = statistics.median(row.values()) or 1.0
            cost = row[pick]
            rel.append(gap_of(cost, best))
            norm.append((cost - best) / med)
            ordered = sorted(row.values())
            ranks.append(ordered.index(cost) + 1)
            within5.append(1.0 if cost <= best * 1.05 + 1e-9 else 0.0)
        return {
            "label": label,
            "mean_rel_gap": statistics.mean(rel) if rel else None,
            "median_rel_gap": statistics.median(rel) if rel else None,
            "mean_norm_excess": statistics.mean(norm) if norm else None,
            "mean_rank": statistics.mean(ranks) if ranks else None,
            "within5pct": statistics.mean(within5) if within5 else None,
            "n": len(rel),
        }

    prof_adaptive = profile(lambda c: sel.greedy(bucket_of(c), both),
                            "① 按情形选择")
    prof_oracle = profile(lambda c: oracle_fixed, "② oracle 最优固定")
    prof_train = profile(lambda c: train_best, "③ 训练集最优固定")
    prof_median = profile(
        lambda c: max(both, key=lambda p: -(mhe[c.key][p]
                                            - statistics.median(mhe[c.key].values()))),
        "（参考）单元中位算子")

    print("\n" + "=" * 84)
    print("稳健性检查：换 5 种度量看同一个结论（n = held-out 单元数）")
    print("=" * 84)
    hdr = (f"{'策略':<20}{'平均相对差距':>14}{'中位相对差距':>14}"
           f"{'平均超额/中位':>15}{'平均排名':>10}{'近优率(5%)':>12}")
    print(hdr)
    print("-" * 84)
    for pr in (prof_adaptive, prof_oracle, prof_train):
        def f(v, pct=False):
            if v is None:
                return "n/a"
            return f"{v * 100:.2f}%" if pct else f"{v:.2f}"
        print(f"{pr['label']:<20}{f(pr['mean_rel_gap'], True):>14}"
              f"{f(pr['median_rel_gap'], True):>14}"
              f"{f(pr['mean_norm_excess']):>15}"
              f"{f(pr['mean_rank']):>10}"
              f"{f(pr['within5pct'], True):>12}")
    print("-" * 84)
    print("说明：平均排名 1.0 = 每个单元都选中最好的算子；近优率 = 选中算子与单元最优"
          "相差 5% 以内的单元占比。")
    wins = sum(1 for k in ("mean_rel_gap", "median_rel_gap", "mean_norm_excess",
                           "mean_rank", "within5pct")
               if prof_adaptive[k] is not None and prof_oracle[k] is not None
               and ((prof_adaptive[k] < prof_oracle[k])
                    if k != "within5pct" else (prof_adaptive[k] > prof_oracle[k])))
    print(f"\n在 5 种度量中，『按情形选择』优于『oracle 最优固定』的有 {wins} 种")

    out = Path("D:/myagent/runs/selector_verdict.json")
    out.write_text(json.dumps({
        "budgets": bs,
        "adaptive_gap": adaptive,
        "oracle_fixed": {"policy": oracle_fixed, "gap": oracle_fixed_gap},
        "train_best_fixed": {"policy": train_best, "gap": train_fixed_gap},
        "mean_all": mean_all,
        "median_all": median_all,
        "learned": {b: {p: a.mean for p, a in sel.arms[b].items()}
                    for b in sel.arms},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
