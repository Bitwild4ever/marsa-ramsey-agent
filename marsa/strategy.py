"""策略记忆：记住"哪种算子在什么规模上有效"，而不是记住具体解。

为什么是这个层次的记忆
----------------------
实验给出了一个明确的负面结论：把历史**解**存起来再热启动，会锚定在平庸盆地，
表现反而不如独立随机重启（见 runs/ 下的消融结果）。但另一组实测显示了一条
可靠的规律：

    n 小（<=30）：禁忌搜索单步信息量大，能解出退火解不出的"针尖型"实例；
    n 大（>30） ：禁忌每步要评估全部 C(n,2) 条边，步频骤降约 13 倍，
                  退火每步只评估 1 条边，步频与 n 基本无关，反而更强。

所以真正值得记的是**"策略在什么规模上有效"**。本模块用 UCB1 多臂老虎机
在"规模分桶"内部选择算子，让智能体从自己的运行经验里把这条规律学出来。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path


def size_bucket(n: int, boundary: int = 30) -> str:
    """把实例规模分桶，作为"情形"特征（case-based 的那一部分）。"""
    return "small" if n <= boundary else "large"


@dataclass
class StrategyRecord:
    n: int
    s: int
    t: int
    bucket: str
    operator: str
    seconds: float
    steps: int
    init_cost: int
    best_cost: int
    reward: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class ArmStats:
    pulls: int = 0
    total_reward: float = 0.0
    best_reward: float = 0.0
    best_cost: int | None = None
    total_steps: int = 0
    total_seconds: float = 0.0

    @property
    def mean_reward(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0


class StrategyMemory:
    """按"规模分桶 × 算子"维护收益统计，用 UCB1 做选择。

    收益定义为**相对改进率**：

        reward = (init_cost - best_cost) / init_cost      ∈ [0, 1]

    因为每个 episode 的时间预算相同，时间因素在算子之间相互抵消，
    这个收益就直接回答"同样的时间，哪个算子把代价压得更低"。
    """

    def __init__(self, path: str | Path | None = None,
                 boundary: int = 30, explore_c: float = 1.0):
        self.path = Path(path) if path else None
        self.boundary = boundary
        self.explore_c = explore_c
        self.arms: dict[str, dict[str, ArmStats]] = {}
        self.records: list[StrategyRecord] = []
        if self.path and self.path.exists():
            self.path.unlink()

    # ---------- 记录 ----------

    def reward_of(self, init_cost: int, best_cost: int) -> float:
        if init_cost <= 0:
            return 0.0
        r = (init_cost - best_cost) / init_cost
        return max(0.0, min(1.0, r))

    def add(self, n: int, s: int, t: int, operator: str, seconds: float,
            steps: int, init_cost: int, best_cost: int) -> float:
        b = size_bucket(n, self.boundary)
        reward = self.reward_of(init_cost, best_cost)
        arm = self.arms.setdefault(b, {}).setdefault(operator, ArmStats())
        arm.pulls += 1
        arm.total_reward += reward
        arm.total_steps += steps
        arm.total_seconds += seconds
        arm.best_reward = max(arm.best_reward, reward)
        if arm.best_cost is None or best_cost < arm.best_cost:
            arm.best_cost = best_cost
        rec = StrategyRecord(n=n, s=s, t=t, bucket=b, operator=operator,
                             seconds=round(seconds, 4), steps=steps,
                             init_cost=init_cost, best_cost=best_cost,
                             reward=round(reward, 6))
        self.records.append(rec)
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(rec.to_json() + "\n")
        return reward

    # ---------- 选择 ----------

    def choose(self, n: int, operators: tuple[str, ...],
               rng) -> tuple[str, str]:
        """UCB1 选择算子。返回 (算子, 选择理由)。"""
        b = size_bucket(n, self.boundary)
        arms = self.arms.setdefault(b, {})
        # 未试过的算子优先（按给定顺序，保证可复现）
        for op in operators:
            if op not in arms or arms[op].pulls == 0:
                return op, f"[UCB] 桶={b} 中 {op} 尚未尝试，先探索"
        total = sum(arms[op].pulls for op in operators)
        best_op, best_score, best_parts = None, -1.0, None
        for op in operators:
            a = arms[op]
            bonus = self.explore_c * math.sqrt(2.0 * math.log(total) / a.pulls)
            score = a.mean_reward + bonus
            if score > best_score:
                best_op, best_score = op, score
                best_parts = (a.mean_reward, bonus)
        assert best_op is not None
        mr, bonus = best_parts
        return best_op, (f"[UCB] 桶={b} 选 {best_op}："
                         f"平均收益 {mr:.4f} + 探索项 {bonus:.4f}")

    # ---------- 报告 ----------

    def table(self) -> str:
        lines = ["规模分桶  算子    次数   平均收益   最好收益   历史最低代价"]
        for b in sorted(self.arms):
            for op, a in sorted(self.arms[b].items()):
                lines.append(
                    f"{b:<10}{op:<8}{a.pulls:>4}{a.mean_reward:>11.4f}"
                    f"{a.best_reward:>11.4f}{str(a.best_cost):>13}")
        return "\n".join(lines)
