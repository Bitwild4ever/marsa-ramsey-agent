"""组合选择器：在**算子组合**上做 UCB1 决策。

这是阶段 1 的核心待检验对象。与上一版策略记忆的区别：

* 上一版：3 个算子，其中一个在所有实例与预算上占优 —— 老虎机数学上不可能取胜。
* 这一版：25 个异质算子，实测确认**不同 (规模, 预算) 单元由不同算子取胜**，
  因此"事后最优的固定算子"并不是天花板，按情形选择才可能有增益。

选择按 **情形分桶**（bucket）进行：桶 =（规模档, 预算档）。
刻意只按规模与预算分桶、**不按 (s,t) 分桶**，这样在 (s,t) 不同的 held-out
实例上必须真正泛化，而不能靠记住具体题目取胜。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class ArmStat:
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def mean(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0


class PortfolioSelector:
    """按桶维护 算子 -> 收益 统计，用 UCB1 选择。"""

    def __init__(self, explore_c: float = 1.0):
        self.explore_c = explore_c
        self.arms: dict[str, dict[str, ArmStat]] = {}

    def observe(self, bucket: str, policy: str, reward: float) -> None:
        arm = self.arms.setdefault(bucket, {}).setdefault(policy, ArmStat())
        arm.pulls += 1
        arm.total_reward += reward

    def choose(self, bucket: str, policies: list[str],
               rng: random.Random | None = None) -> tuple[str, str]:
        """UCB1 选择。未试过的算子优先（按给定顺序，保证可复现）。"""
        arms = self.arms.setdefault(bucket, {})
        for p in policies:
            a = arms.get(p)
            if a is None or a.pulls == 0:
                return p, f"未尝试 {p}，先探索"
        total = sum(arms[p].pulls for p in policies)
        best_p, best_score, best_parts = None, -1.0, None
        for p in policies:
            a = arms[p]
            bonus = self.explore_c * math.sqrt(2.0 * math.log(total) / a.pulls)
            score = a.mean + bonus
            if score > best_score:
                best_p, best_score, best_parts = p, score, (a.mean, bonus)
        assert best_p is not None
        mean, bonus = best_parts
        return best_p, f"UCB 选 {best_p}（均值 {mean:.4f} + 探索 {bonus:.4f}）"

    def greedy(self, bucket: str, policies: list[str]) -> str | None:
        """纯利用（评估阶段使用）：取该桶内历史平均收益最高的算子。"""
        arms = self.arms.get(bucket, {})
        known = [p for p in policies if arms.get(p) and arms[p].pulls > 0]
        if not known:
            return None
        return max(known, key=lambda p: (arms[p].mean, -arms[p].pulls))

    def table(self, policies: list[str]) -> str:
        lines = ["桶            算子                          次数    平均收益"]
        for b in sorted(self.arms):
            ranked = sorted(self.arms[b].items(),
                            key=lambda kv: -kv[1].mean)
            for p, a in ranked[:5]:
                lines.append(f"{b:<14}{p:<30}{a.pulls:>5}{a.mean:>12.4f}")
        return "\n".join(lines)
