"""基准集与离线评测协议。

方法论要点（这决定了结论可不可信）
----------------------------------
1. **训练集 / held-out 严格分离**。策略记忆只在训练集上积累经验；
   最终结论必须在 held-out 实例上取得，且 held-out 的实例规模不参与任何调参。
2. **固定墙钟预算**，不按步数。原因：不同算子的单步成本差两个数量级，
   按步数比较等于替退火作弊。
3. **多种子取均值**。已实测同一配置不同 seed 下最优代价能差近一倍，
   单 seed 结论不可信。
4. **任何代价 0 都必须过独立验证器**；验证失败按严重错误记录，不静默接受。
5. 结果可断点续跑（逐策略落盘），长实验不会因为中断而白跑。
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from .operators import Policy, run_policy
from .verifier import verify

RESULTS = Path("D:/myagent/runs/portfolio_results.json")


@dataclass(frozen=True)
class Instance:
    s: int
    t: int
    n: int

    @property
    def name(self) -> str:
        return f"({self.s},{self.t})@{self.n}"


# 训练集：策略记忆在这里积累经验
TRAIN_INSTANCES = (
    Instance(5, 5, 36),
    Instance(5, 5, 43),
    Instance(4, 6, 35),
)

# 扩展训练集：用于区分"记忆无用"与"记忆因训练数据太少而无用"。
# 刻意**避开**所有 held-out 实例（(5,5)@40/44、(4,6)@36、(4,5)@24），
# 否则 held-out 协议就被破坏了。
EXTENDED_TRAIN_INSTANCES = (
    Instance(5, 5, 34),
    Instance(5, 5, 36),
    Instance(5, 5, 38),
    Instance(5, 5, 42),
    Instance(5, 5, 43),
    Instance(5, 5, 45),
    Instance(4, 6, 33),
    Instance(4, 6, 35),
    Instance(4, 6, 37),
    Instance(4, 5, 21),
    Instance(4, 5, 23),
    Instance(4, 4, 16),
    Instance(4, 4, 17),
    Instance(3, 7, 22),
)

# held-out：最终结论只看这些；规模与形状都与训练集不同，且不参与任何调参
HELD_OUT_INSTANCES = (
    Instance(5, 5, 40),
    Instance(5, 5, 44),
    Instance(4, 6, 36),
    Instance(4, 5, 24),
)

# 两个预算区间：短预算偏好高步频算子，长预算偏好高单步质量算子
BUDGETS = (0.5, 3.0)

DEFAULT_SEEDS = (0, 1, 2)


@dataclass(frozen=True)
class Cell:
    inst: Instance
    budget: float

    @property
    def key(self) -> str:
        return f"{self.inst.name}|{self.budget:g}s"


def cells(instances, budgets=BUDGETS) -> list[Cell]:
    return [Cell(i, b) for i in instances for b in budgets]


# --------------------------------------------------------------------------
# 评测
# --------------------------------------------------------------------------

def load_results() -> dict:
    if RESULTS.exists():
        return json.loads(RESULTS.read_text(encoding="utf-8"))
    return {"cells": {}, "runs": {}}


def save_results(data: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")


def evaluate(policy: Policy, cell: Cell, seeds=DEFAULT_SEEDS) -> dict:
    """在单个 (实例, 预算) 单元上评测一个策略，返回多种子结果。"""
    costs, verified, elapsed = [], [], 0.0
    invalid = 0
    for sd in seeds:
        t0 = time.perf_counter()
        res = run_policy(policy, cell.inst.n, cell.inst.s, cell.inst.t,
                         cell.budget, sd)
        elapsed += time.perf_counter() - t0
        costs.append(res.best_cost)
        if res.best_cost == 0:
            good, _w = verify(cell.inst.n, res.best_red,
                              cell.inst.s, cell.inst.t)
            if not good:
                invalid += 1          # 搜索器自报成功但验证器否决 -> 严重错误
            verified.append(bool(good))
        else:
            verified.append(False)
    return {
        "policy": policy.name,
        "cell": cell.key,
        "costs": costs,
        "mean": statistics.mean(costs),
        "best": min(costs),
        "worst": max(costs),
        "solved": min(costs) == 0,
        "verified_solved": any(verified),
        "invalid_claims": invalid,
        "seconds": round(elapsed, 3),
    }


def run_grid(policies: list[Policy], cell_list: list[Cell],
             seeds=DEFAULT_SEEDS, verbose: bool = True) -> dict:
    """跑完整个 策略 × 单元 网格，逐策略落盘（可断点续跑）。"""
    data = load_results()
    for cell in cell_list:
        data["cells"].setdefault(cell.key, {
            "s": cell.inst.s, "t": cell.inst.t, "n": cell.inst.n,
            "budget": cell.budget,
        })
    total = len(policies) * len(cell_list)
    done = 0
    t_start = time.perf_counter()
    for p in policies:
        for cell in cell_list:
            key = f"{p.name}|{cell.key}"
            done += 1
            if key in data["runs"]:
                continue
            rec = evaluate(p, cell, seeds)
            data["runs"][key] = rec
            save_results(data)
            if verbose:
                print(f"  [{done:>4}/{total}] {p.name:<26} {cell.key:<16} "
                      f"均值={rec['mean']:>8.1f} 最优={rec['best']:>6} "
                      f"{'解出' if rec['solved'] else ''}"
                      f"{' !!验证失败' if rec['invalid_claims'] else ''}")
    if verbose:
        print(f"  网格完成，用时 {time.perf_counter() - t_start:.1f}s")
    return data


# --------------------------------------------------------------------------
# 分析
# --------------------------------------------------------------------------

def cell_matrix(data: dict, policies: list[Policy],
                cell_list: list[Cell]) -> dict[str, dict[str, float]]:
    """返回 {cell_key: {policy_name: mean_cost}}，缺失的记为 None。"""
    out: dict[str, dict[str, float]] = {}
    for cell in cell_list:
        row = {}
        for p in policies:
            rec = data["runs"].get(f"{p.name}|{cell.key}")
            row[p.name] = rec["mean"] if rec else None
        out[cell.key] = row
    return out


def gap(cost: float, best: float) -> float:
    """相对最优单元代价的差距。best=0（已解出）时退回绝对差。"""
    if best is None or cost is None:
        return float("inf")
    return (cost - best) / max(1.0, best)


def analyze(data: dict, policies: list[Policy], cell_list: list[Cell],
            label: str) -> dict:
    """检查异构性：是否存在单一算子在所有单元上占优。"""
    names = [p.name for p in policies]
    mat = cell_matrix(data, policies, cell_list)

    per_cell_best = {}
    winners: dict[str, list[str]] = {}
    for ck, row in mat.items():
        valid = {k: v for k, v in row.items() if v is not None}
        if not valid:
            continue
        b = min(valid.values())
        per_cell_best[ck] = b
        winners[ck] = sorted(k for k, v in valid.items() if v == b)

    # 每个算子的平均相对差距（= 如果永远只用它，表现如何）
    avg_gap = {}
    for nm in names:
        gs = [gap(mat[ck][nm], per_cell_best[ck]) for ck in mat
              if mat[ck].get(nm) is not None and ck in per_cell_best]
        if gs:
            avg_gap[nm] = statistics.mean(gs)

    winner_policy = min(avg_gap, key=avg_gap.get) if avg_gap else None
    distinct_winners = sorted({w for ws in winners.values() for w in ws})

    print(f"\n{'=' * 78}")
    print(f"异构性分析 —— {label}（{len(cell_list)} 个单元，"
          f"{len(policies)} 个算子）")
    print("=" * 78)
    print(f"{'单元':<18}{'最优代价':>10}  单元内胜者")
    print("-" * 78)
    for ck in mat:
        if ck not in per_cell_best:
            continue
        b = per_cell_best[ck]
        w = winners[ck]
        shown = ", ".join(w[:3]) + (" ..." if len(w) > 3 else "")
        print(f"{ck:<18}{b:>10.1f}  {shown}")

    print("-" * 78)
    print("若永远只用某一个算子（按平均相对差距排序）：")
    for nm in sorted(avg_gap, key=avg_gap.get)[:8]:
        print(f"  {nm:<28} 平均相对差距 {avg_gap[nm] * 100:>8.2f}%")
    print("-" * 78)
    print(f"单元内出现过的不同胜者数 = {len(distinct_winners)}："
          f"{distinct_winners}")
    print(f"事后最优的固定算子（oracle best fixed）= {winner_policy}"
          f"（{avg_gap.get(winner_policy, 0) * 100:.2f}%）")
    if len(distinct_winners) <= 1 and winner_policy:
        print(">> 异构性不足：只有单一算子占优，此时策略记忆不可能取胜")
    else:
        print(">> 存在异构性：不同单元由不同算子取胜，策略记忆有取胜空间")

    return {"mat": mat, "per_cell_best": per_cell_best, "winners": winners,
            "avg_gap": avg_gap, "oracle_best_fixed": winner_policy,
            "distinct_winners": distinct_winners}
