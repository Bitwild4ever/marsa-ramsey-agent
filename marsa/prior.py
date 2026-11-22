"""策略先验 —— 把每次算子比较的结果变成**可查询、可累积**的知识。

为什么需要它
------------
之前每次 `ramsey_compare` 跑完，结果就随运行结束了。下一次遇到同一个
(n, s, t, budget) 单元，agent 还是从头再测一遍——**经验没有被保存**。
这就是"第 N 次和第 1 次一样笨"的具体表现。

这个模块把每次比较落成一条 episode，并在查询时跨 episode 聚合，
于是"这个单元该用哪个算子"这个问题，答案会随着数据积累而变准。

设计上必须守住的纪律
--------------------
**推荐只在统计上站得住时才给出。** 具体规则：
  * 同一单元里把各 episode 的**逐 seed 违反度**合并；
  * 最好与次好的均值差必须大于两者的标准差；
  * 否则返回 `inconclusive`，且 `recommended` 为 None。

理由和 `ramsey_compare` 完全一致：这些实例上同配置不同 seed 的差异可以接近
两倍，凭均值高低下结论几乎总会过度概括。先验表如果开始"自信地推荐错的算子"，
比没有先验更糟——它会系统性地把搜索引向差配置。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DIR = r"D:\myagent\growth"

# 同一个"单元"的定义：这三个量决定实例难度，budget 决定算力预算。
CELL_KEYS = ("n", "s", "t", "budget")


def prior_path() -> Path:
    d = Path(os.environ.get("MARSA_GROWTH_DIR", DEFAULT_DIR))
    d.mkdir(parents=True, exist_ok=True)
    return d / "prior.jsonl"


def _cell_key(n: int, s: int, t: int, budget: float) -> str:
    # budget 量化到 0.5s，避免 5.0 与 5.0001 被当成不同单元
    return f"n{n}_s{s}_t{t}_b{round(float(budget) * 2) / 2:g}"


# ===========================================================================
#  写入
# ===========================================================================

def record_comparison(result: Dict[str, Any]) -> bool:
    """把一次 ramsey_compare 的结果落成一条 episode。

    失败不抛异常：先验表写不进去不应该让一次成功的比较变成失败。
    """
    try:
        if not isinstance(result, dict):
            return False
        per = result.get("per_operator")
        if not per or not isinstance(per, dict):
            return False
        n = result.get("n")
        s = result.get("s", 5)
        t = result.get("t", 5)
        budget = result.get("budget_seconds", result.get("budget"))
        if n is None or budget is None:
            return False

        episode = {
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "cell": _cell_key(int(n), int(s), int(t), float(budget)),
            "n": int(n), "s": int(s), "t": int(t),
            "budget": float(budget),
            "seeds": result.get("seeds"),
            "seed_base": result.get("seed_base"),
            "verdict": result.get("verdict"),
            "winner": result.get("winner"),
            "margin": result.get("margin"),
            "noise_floor": result.get("noise_floor"),
            # 关键：存逐 seed 的原始计数，聚合时才能重算统计量
            "per_operator": {
                str(op): {
                    "violations": list(v.get("violations") or []),
                    "mean": v.get("mean"),
                    "std": v.get("std"),
                }
                for op, v in per.items()
            },
        }
        with prior_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(episode, ensure_ascii=False) + "\n")
        return True
    except Exception:                                            # noqa: BLE001
        return False


# ===========================================================================
#  读取与聚合
# ===========================================================================

def load_episodes() -> List[Dict[str, Any]]:
    p = prior_path()
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _episodes_for(n: int, s: int, t: int, budget: float) -> List[Dict[str, Any]]:
    key = _cell_key(n, s, t, budget)
    return [e for e in load_episodes() if e.get("cell") == key]


def _aggregate(episodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """把同一单元内所有 episode 的逐 seed 计数合并成每个算子的统计量。"""
    pooled: Dict[str, List[int]] = {}
    for e in episodes:
        for op, v in (e.get("per_operator") or {}).items():
            vals = v.get("violations") or []
            pooled.setdefault(str(op), []).extend(
                int(x) for x in vals if isinstance(x, (int, float)))

    agg: Dict[str, Dict[str, Any]] = {}
    for op, vals in pooled.items():
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        if len(vals) > 1:
            var = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
            std = var ** 0.5
        else:
            std = 0.0
        agg[op] = {
            "samples": len(vals),
            "mean": round(mean, 2),
            "std": round(std, 2),
            "min": min(vals),
            "max": max(vals),
            "solved_any": 0 in vals,
        }
    return agg


def recommend(n: int, s: int = 5, t: int = 5, budget: float = 5.0,
              min_samples: int = 3, min_episodes: int = 2) -> Dict[str, Any]:
    """基于已积累的先验，给出该单元推荐的算子。

    只有在证据足够、跨 episode 一致、且差距超过噪声时才推荐；
    否则明确返回 inconclusive。

    为什么要求 min_episodes >= 2
    ----------------------------
    实测教训：只用一个 episode（3 个 seed）判出的 `clear_winner`，
    在全新 seed 上复测时**推荐反而更差**（212.7 vs 210.0）。
    单次比较的噪声地板估计本身就不稳，所以必须要求同一个算子在
    **多个独立 episode** 里都领先，才算先验成立。
    """
    n, s, t = int(n), int(s), int(t)
    budget = float(budget)
    episodes = _episodes_for(n, s, t, budget)

    if not episodes:
        return {
            "ok": True, "status": "no_data", "recommended": None,
            "cell": _cell_key(n, s, t, budget),
            "episodes": 0, "operators": {},
            "conclusion": (
                f"先验表里没有 (n={n}, s={s}, t={t}, budget={budget:g}s) 这个单元的数据。"
                f"要么先跑一次 ramsey_compare 积累数据，要么直接测。"
                f"**不要**把其他 n 的结论套过来——不同规模的最优算子可能不同。"
            ),
        }

    agg = _aggregate(episodes)
    if len(agg) < 2:
        return {
            "ok": True, "status": "insufficient_operators", "recommended": None,
            "cell": _cell_key(n, s, t, budget), "episodes": len(episodes),
            "operators": agg,
            "conclusion": (
                f"该单元只测过 {len(agg)} 个算子，无法比较。"
            ),
        }

    ranking = sorted(agg, key=lambda o: agg[o]["mean"])
    best, second = ranking[0], ranking[1]

    # 样本太少时不下结论
    if min(agg[best]["samples"], agg[second]["samples"]) < min_samples:
        return {
            "ok": True, "status": "too_few_samples", "recommended": None,
            "cell": _cell_key(n, s, t, budget), "episodes": len(episodes),
            "operators": agg, "ranking": ranking,
            "conclusion": (
                f"样本不足（最好 {agg[best]['samples']} 个，次好 "
                f"{agg[second]['samples']} 个，要求至少 {min_samples}）。"
                f"继续积累，不要据此下结论。"
            ),
        }

    # 有算子解出过：直接推荐它（解出是压倒性证据）
    solvers = [o for o in agg if agg[o]["solved_any"]]
    if solvers:
        pick = min(solvers, key=lambda o: agg[o]["mean"])
        return {
            "ok": True, "status": "recommend", "recommended": pick,
            "cell": _cell_key(n, s, t, budget), "episodes": len(episodes),
            "operators": agg, "ranking": ranking, "basis": "solved",
            "conclusion": (
                f"推荐 {pick}：它在历史数据里解出过（违反度 0）。"
                f"这是压倒性证据，优先用它。"
            ),
        }

    margin = round(agg[second]["mean"] - agg[best]["mean"], 2)
    noise = round(max(agg[best]["std"], agg[second]["std"]), 2)

    # 跨 episode 一致性：每个 episode 各自的最低均值算子
    per_episode_winner = []
    for e in episodes:
        vals = {op: v.get("mean") for op, v in (e.get("per_operator") or {}).items()
                if v.get("mean") is not None}
        if len(vals) >= 2:
            per_episode_winner.append(min(vals, key=vals.get))
    wins = sum(1 for w in per_episode_winner if w == best)
    consistent = (len(per_episode_winner) >= min_episodes
                  and wins * 2 > len(per_episode_winner))

    detail = {
        "ok": True, "cell": _cell_key(n, s, t, budget),
        "episodes": len(episodes), "operators": agg, "ranking": ranking,
        "margin": margin, "noise_floor": noise,
        "episode_wins": {best: wins, second: len(per_episode_winner) - wins},
        "independent_episodes": len(per_episode_winner),
    }

    if margin > noise and consistent:
        return dict(detail, status="recommend", recommended=best,
                    basis="measured", conclusion=(
                        f"推荐 {best}：跨 {len(episodes)} 次独立比较、共 "
                        f"{agg[best]['samples']} 个样本，均值 {agg[best]['mean']} "
                        f"优于 {second} 的 {agg[second]['mean']}，"
                        f"差距 {margin} > 噪声地板 {noise}，"
                        f"且在 {wins}/{len(per_episode_winner)} 个独立 episode 里领先。"
                        f"这是**已测量**的推荐，不是存在性结论。"))

    if margin > noise and not consistent:
        return dict(detail, status="inconsistent_across_episodes",
                    recommended=None, conclusion=(
                        f"**无定论**：合并均值上 {best} 领先 {margin} > 噪声 {noise}，"
                        f"但只在 {wins}/{len(per_episode_winner)} 个独立 episode 里领先，"
                        f"不一致。单次比较的噪声估计不可靠，"
                        f"不能据此推荐。需要更多 episode。"))

    return dict(detail, status="inconclusive", recommended=None, conclusion=(
        f"**无定论**：{best}（均值 {agg[best]['mean']}, 标准差 "
        f"{agg[best]['std']}, {agg[best]['samples']} 样本）与 {second}"
        f"（均值 {agg[second]['mean']}, 标准差 {agg[second]['std']}, "
        f"{agg[second]['samples']} 样本）差距 {margin} ≤ 噪声地板 {noise}。"
        f"不得据此推荐；需要更多 seed 或更大预算。"))


def stats() -> Dict[str, Any]:
    """先验表总览：覆盖多少个单元、多少样本。"""
    episodes = load_episodes()
    cells: Dict[str, int] = {}
    for e in episodes:
        cells[str(e.get("cell"))] = cells.get(str(e.get("cell")), 0) + 1
    return {
        "ok": True,
        "status": "ok",
        "episodes": len(episodes),
        "cells": len(cells),
        "cell_detail": dict(sorted(cells.items())),
        "path": str(prior_path()),
        "conclusion": (
            f"先验表有 {len(episodes)} 条 episode，覆盖 {len(cells)} 个单元。"
            if episodes else
            "先验表还是空的。跑 ramsey_compare 会自动积累数据。"
        ),
    }
