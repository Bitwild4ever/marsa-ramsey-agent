"""规划器：决定每个 episode 用什么算子、多少步、怎么用记忆。

这是智能体的"高层决策"部分。**关键设计：规划器是可插拔的。**

  * ScriptedPlanner —— 离线规则，不需要任何 API，保证实验完全可复现；
  * LLMPlanner      —— 调用大模型做规划，失败或超时时自动降级到 ScriptedPlanner。

之所以把 LLM 放在规划层而不是搜索层：LLM 做原始组合搜索不可靠，但擅长
"看统计 → 选策略"。这个分工是刻意的架构选择，也让整个项目在没有任何
API key 的情况下依然能完整跑通（可复现性优先）。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict
from typing import Callable, Protocol

from .memory import RETRIEVAL_MODES


@dataclass
class Plan:
    operator: str = "sa"
    steps: int = 100_000
    memory_mode: str = "none"
    retrieve_k: int = 3
    perturb_strength: int = 40
    rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlanContext:
    """规划器能看到的全部信息。"""
    n: int
    s: int
    t: int
    episode: int
    best_cost: int
    history: list[dict]          # 以往 episode 的摘要
    memory_size: int

    def summarize(self) -> str:
        """给 LLM 看的紧凑统计摘要。"""
        if not self.history:
            return (f"任务: (s,t)=({self.s},{self.t}), n={self.n}。"
                    f"尚无历史 episode。记忆库为空。")
        by_op: dict[str, list[int]] = {}
        for h in self.history:
            by_op.setdefault(h.get("operator", "?"), []).append(h.get("cost", 0))
        lines = [f"任务: (s,t)=({self.s},{self.t}), n={self.n}。"
                 f"已完成 {len(self.history)} 个 episode，"
                 f"当前最优代价 {self.best_cost}，记忆库 {self.memory_size} 条。",
                 "各算子历史最优代价："]
        for op, costs in by_op.items():
            lines.append(f"  - {op}: 共 {len(costs)} 次，"
                         f"最好 {min(costs)}，最近 {costs[-1]}")
        mem_stats: dict[str, list[int]] = {}
        for h in self.history:
            mem_stats.setdefault(h.get("memory_mode", "?"), []).append(
                h.get("cost", 0))
        lines.append("各记忆策略历史最优代价：")
        for m, costs in mem_stats.items():
            lines.append(f"  - {m}: 共 {len(costs)} 次，最好 {min(costs)}")
        return "\n".join(lines)


class Planner(Protocol):
    name: str

    def plan(self, ctx: PlanContext) -> Plan: ...


# --------------------------------------------------------------------------
# 离线脚本化规划器
# --------------------------------------------------------------------------

class ScriptedPlanner:
    """把**实测得到的结论**编码成规则，作为不需要任何 API 的基线规划器。

    规则来源（scripts/bench_candidates.py、scripts/bench_operators.py 实测）：

      * 候选表禁忌（focus，每步只评估 128 条候选边）在所有规模上一致最优：
        n=36 时最优代价 1（全量禁忌 9、退火 13）；
        n=43 时 163（全量 195、退火 203）；
        n=46 时 334（全量 417、退火 396）。
        原因是它同时拿到了高步频（约 7~8 倍提速）和足够好的单步质量。
      * 退火唯一的长处是步频与 n 无关，但在同等时间内始终不如禁忌。

    注意：这条规则是**测出来之后**才写进来的，不是先验假设。
    最初"n 小用禁忌、n 大用退火"的假设已被实测推翻。
    """

    name = "scripted"

    def __init__(self, tabu_max_n: int = 30):
        self.tabu_max_n = tabu_max_n

    def plan(self, ctx: PlanContext) -> Plan:
        op = "tabu_focus"
        steps = 10 ** 9 if ctx.n > self.tabu_max_n else 20_000

        if ctx.memory_size < 3:
            mode, k = "none", 0
            why = "记忆库样本不足，先冷启动积累 elite"
        else:
            mode, k = "submodular", min(4, max(2, ctx.memory_size // 4))
            why = "记忆库已有 elite，用次模检索取回多样历史解做热启动"

        recent = [h.get("cost", 10 ** 9) for h in ctx.history[-4:]]
        perturb = 40
        if len(recent) >= 3 and len(set(recent)) == 1:
            perturb = 80
            why += "；近期无改进，加大扰动强度"

        return Plan(operator=op, steps=steps, memory_mode=mode,
                    retrieve_k=k, perturb_strength=perturb,
                    rationale=f"[scripted] 采用实测最优算子 {op}；{why}")


# --------------------------------------------------------------------------
# LLM 规划器（可插拔）
# --------------------------------------------------------------------------

PLANNER_PROMPT = """你是一个组合优化搜索的规划器。你的职责是选择搜索算子与参数。

已知实测事实：
- 算子 "sa"（模拟退火）：每步只评估 1 条边，步频约 6e4~2e5 步/秒，与 n 基本无关。
- 算子 "tabu"（禁忌搜索，全量候选）：每步评估全部 C(n,2) 条边，n 大时步频骤降
  （n=46 时约 100 步/秒）。
- 算子 "tabu_focus"（候选表禁忌，每步只评估 128 条候选边）：实测在 n=36/43/46 上
  最优代价分别为 1/163/334，全面优于 sa 的 13/203/396 与全量 tabu 的 9/195/417；
  主要优势是同时取得约 7~8 倍步频与足够好的单步质量。
- 记忆策略 "none" 冷启动；"submodular" 用次模最大化取回多样历史解做热启动。

当前状态：
{summary}

请只输出一个 JSON 对象（不要任何其他文字），字段：
{{"operator": "sa"|"tabu"|"tabu_focus", "steps": 整数,
 "memory_mode": "none"|"random"|"nearest"|"submodular",
 "retrieve_k": 整数, "perturb_strength": 整数, "rationale": "一句话理由"}}
"""


class LLMPlanner:
    """用大模型做规划。

    `complete` 是一个 (prompt) -> str 的可调用对象，由调用方注入具体的模型
    provider（OpenAI / DeepSeek / 本地模型皆可），因此本模块不绑定任何厂商。
    任何异常（无 key、超时、返回不可解析）都会**自动降级**到 ScriptedPlanner，
    保证实验不会因为 API 问题而中断。
    """

    name = "llm"

    def __init__(self, complete: Callable[[str], str] | None = None,
                 fallback: Planner | None = None):
        self.complete = complete
        self.fallback = fallback or ScriptedPlanner()
        self.stats = {"llm_calls": 0, "llm_ok": 0, "llm_fallback": 0}

    def plan(self, ctx: PlanContext) -> Plan:
        if self.complete is None:
            self.stats["llm_fallback"] += 1
            p = self.fallback.plan(ctx)
            p.rationale = "[llm降级->scripted] " + p.rationale
            return p
        self.stats["llm_calls"] += 1
        try:
            raw = self.complete(PLANNER_PROMPT.format(summary=ctx.summarize()))
            data = _extract_json(raw)
            p = Plan(
                operator=data.get("operator", "sa"),
                steps=int(data.get("steps", 100_000)),
                memory_mode=data.get("memory_mode", "none"),
                retrieve_k=int(data.get("retrieve_k", 3)),
                perturb_strength=int(data.get("perturb_strength", 40)),
                rationale="[llm] " + str(data.get("rationale", ""))[:200],
            )
            # 合法性校验：LLM 也可能给出无效配置
            if p.operator not in ("sa", "tabu", "tabu_focus", "tabu_sample"):
                raise ValueError(f"非法算子 {p.operator}")
            if p.memory_mode not in RETRIEVAL_MODES:
                raise ValueError(f"非法记忆策略 {p.memory_mode}")
            p.steps = max(1_000, min(p.steps, 5_000_000))
            p.retrieve_k = max(0, min(p.retrieve_k, 16))
            p.perturb_strength = max(0, min(p.perturb_strength, 500))
            self.stats["llm_ok"] += 1
            return p
        except Exception as exc:                    # noqa: BLE001
            self.stats["llm_fallback"] += 1
            p = self.fallback.plan(ctx)
            p.rationale = f"[llm失败({type(exc).__name__})->scripted] " + p.rationale
            return p


def _extract_json(raw: str) -> dict:
    """从模型输出里抠出第一个 JSON 对象。"""
    if raw is None:
        raise ValueError("空回复")
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("回复中没有 JSON 对象")
    return json.loads(raw[start:end + 1])


# --------------------------------------------------------------------------
# 自适应规划器：用"策略记忆"选择算子（本项目的正面结论所在）
# --------------------------------------------------------------------------

class AdaptivePlanner:
    """用 UCB1 在"规模分桶"内选择算子，从自己的运行经验里学习规律。

    这是把记忆放在**策略层**而不是解层的直接结果：消融实验证明解层记忆
    会锚定在平庸盆地，而算子适用性随规模变化是一条稳定、可学的规律。
    """

    name = "adaptive"

    def __init__(self, operators: tuple[str, ...] = ("sa", "tabu", "tabu_focus"),
                 seconds: float = 1.5, boundary: int = 30,
                 memory_path: str | None = None, explore_c: float = 1.0,
                 seed: int = 0):
        from .strategy import StrategyMemory      # 延迟导入，避免循环依赖
        self.memory = StrategyMemory(memory_path, boundary=boundary,
                                     explore_c=explore_c)
        self.operators = tuple(operators)
        self.seconds = seconds
        self._rng = random.Random(seed)

    def plan(self, ctx: PlanContext) -> Plan:
        op, why = self.memory.choose(ctx.n, self.operators, self._rng)
        return Plan(operator=op, steps=10 ** 9, memory_mode="none",
                    retrieve_k=0, perturb_strength=0, rationale=why)

    def observe(self, *, n: int, s: int, t: int, operator: str,
                seconds: float, steps: int, init_cost: int,
                best_cost: int) -> float:
        """把一次 episode 的结果反馈进策略记忆（智能体的"经验"）。"""
        return self.memory.add(n, s, t, operator, seconds, steps,
                              init_cost, best_cost)
