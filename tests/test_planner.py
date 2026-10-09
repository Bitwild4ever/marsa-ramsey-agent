"""规划器与策略记忆测试。

作业要求里明确写了"LLM 规划器"，所以必须证明 **LLM 这条路径真的能跑**，
而不只是"失败时能降级"。这里注入一个假的模型接口（mock）来完整走通：

  1. 模型返回合法 JSON  -> 配置被正确解析并生效
  2. 模型返回垃圾文本    -> 自动降级到脚本化规划器，不抛异常
  3. 模型抛异常          -> 同样降级
  4. 模型给非法算子/非法记忆策略 -> 被校验拦下并降级
  5. 自适应规划器：UCB1 能从经验里学到该选哪个算子
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.planner import (                                     # noqa: E402
    AdaptivePlanner, LLMPlanner, PlanContext, ScriptedPlanner,
)
from marsa.strategy import StrategyMemory, size_bucket          # noqa: E402

passed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def ctx(n=43, mem=10, hist=None):
    return PlanContext(n=n, s=5, t=5, episode=0, best_cost=200,
                       history=hist or [], memory_size=mem)


def mock_returning(text):
    def _c(prompt):
        assert "JSON" in prompt or "json" in prompt, "提示词里应包含 JSON 格式要求"
        return text
    return _c


def test_llm_valid_json():
    raw = ('好的，我的建议是：\n{"operator": "tabu_focus", "steps": 80000, '
           '"memory_mode": "submodular", "retrieve_k": 3, '
           '"perturb_strength": 60, "rationale": "大 n 用候选表禁忌"}')
    p = LLMPlanner(complete=mock_returning(raw))
    plan = p.plan(ctx())
    assert plan.operator == "tabu_focus", plan.operator
    assert plan.steps == 80000
    assert plan.memory_mode == "submodular"
    assert plan.retrieve_k == 3 and plan.perturb_strength == 60
    assert plan.rationale.startswith("[llm]")
    assert p.stats["llm_ok"] == 1 and p.stats["llm_fallback"] == 0
    # 模型常常会包一层解释文字，必须能从中抠出 JSON
    ok("LLM 返回夹带解释文字的 JSON -> 正确解析（算子/步数/记忆策略全部生效）")


def test_llm_fallbacks():
    cases = [
        ("返回垃圾文本", mock_returning("我觉得应该用模拟退火吧，随便跑跑。")),
        ("抛异常", lambda prompt: (_ for _ in ()).throw(RuntimeError("超时"))),
        ("返回 None", lambda prompt: None),
        ("非法算子", mock_returning('{"operator": "quantum_anneal", "steps": 1000}')),
        ("非法记忆策略", mock_returning(
            '{"operator": "sa", "steps": 1000, "memory_mode": "telepathy"}')),
    ]
    for name, complete in cases:
        p = LLMPlanner(complete=complete)
        plan = p.plan(ctx(n=36))
        # 降级后必须是脚本化规划器的合法输出
        assert plan.operator in ("sa", "tabu", "tabu_focus", "tabu_sample",
                                 "tabu_violation"), plan.operator
        assert plan.memory_mode in ("none", "random", "nearest", "submodular")
        assert plan.steps > 0
        assert "降级" in plan.rationale or "失败" in plan.rationale, plan.rationale
    ok(f"{len(cases)} 种异常输入（垃圾文本/异常/None/非法算子/非法策略）全部安全降级")

    # 完全没有注入模型接口时也必须能跑
    p = LLMPlanner(complete=None)
    plan = p.plan(ctx())
    assert plan.operator in ("sa", "tabu", "tabu_focus", "tabu_sample",
                             "tabu_violation")
    assert p.stats["llm_fallback"] == 1
    ok("未注入模型接口时自动降级，系统仍可完整运行（保证离线可复现）")


def test_llm_clamps():
    """模型给出越界参数时必须被夹到合法范围，不能让它把实验搞崩。"""
    raw = ('{"operator": "sa", "steps": 99999999999, "memory_mode": "none", '
           '"retrieve_k": 9999, "perturb_strength": -5}')
    plan = LLMPlanner(complete=mock_returning(raw)).plan(ctx())
    assert plan.steps <= 5_000_000, plan.steps
    assert 0 <= plan.retrieve_k <= 16, plan.retrieve_k
    assert 0 <= plan.perturb_strength <= 500, plan.perturb_strength
    ok(f"越界参数被夹紧（steps={plan.steps}, k={plan.retrieve_k}, "
       f"perturb={plan.perturb_strength}）")


def test_scripted_uses_measured_operator():
    p = ScriptedPlanner()
    for n in (18, 30, 43, 50):
        plan = p.plan(ctx(n=n))
        assert plan.operator == "tabu_focus", (
            f"n={n} 应使用实测最优算子 tabu_focus，实得 {plan.operator}")
    ok("脚本化规划器在所有规模上采用实测最优算子 tabu_focus")


def test_ucb_learns():
    """UCB1 应当从经验中学到：收益高的算子被选得更多。"""
    mem = StrategyMemory(path=None, boundary=30)
    rng = random.Random(0)
    ops = ("sa", "tabu", "tabu_focus")
    picks = {o: 0 for o in ops}
    # 固定 n=43（large 桶）。人造收益：tabu_focus 总是最好
    rewards = {"sa": 0.05, "tabu": 0.20, "tabu_focus": 0.50}
    for step in range(300):
        op, _why = mem.choose(43, ops, rng)
        picks[op] += 1
        r = rewards[op]
        # 记录到策略记忆里（模拟 agent 的 observe 回调）
        mem.add(n=43, s=5, t=5, operator=op, seconds=1.0, steps=1000,
                init_cost=1000, best_cost=int(1000 * (1 - r)))
    assert picks["tabu_focus"] > picks["sa"], picks
    assert picks["tabu_focus"] >= max(picks["sa"], picks["tabu"]), picks
    assert mem.arms["large"]["tabu_focus"].mean_reward > \
        mem.arms["large"]["sa"].mean_reward
    ok(f"UCB1 学会偏好高收益算子：{picks}（tabu_focus 被选最多）")

    # 分桶必须真的分开：小 n 与大 n 各自独立统计
    mem.add(n=20, s=5, t=5, operator="sa", seconds=1.0, steps=1000,
            init_cost=1000, best_cost=0)
    assert size_bucket(20) == "small" and size_bucket(43) == "large"
    assert "small" in mem.arms and "large" in mem.arms
    assert mem.arms["small"]["sa"].pulls == 1
    ok("策略记忆按规模分桶独立统计（small / large 互不干扰）")


def test_adaptive_planner_end_to_end():
    """自适应规划器 + observe 回调：跑几轮后应稳定选到更好的算子。"""
    p = AdaptivePlanner(operators=("sa", "tabu_focus"), seconds=1.0,
                        memory_path=None, seed=1)
    order = []
    for _ in range(12):
        plan = p.plan(ctx(n=43))
        order.append(plan.operator)
        p.observe(n=43, s=5, t=5, operator=plan.operator, seconds=1.0,
                  steps=1000, init_cost=1000,
                  best_cost=200 if plan.operator == "tabu_focus" else 900)
    tail = order[-6:]
    assert tail.count("tabu_focus") >= 5, f"后期未收敛到更优算子: {order}"
    ok(f"自适应规划器经 observe 反馈后收敛到更优算子（前 12 次选择: {order}）")


if __name__ == "__main__":
    print("=" * 72)
    print("MARSA 规划器与策略记忆测试")
    print("=" * 72)
    test_llm_valid_json()
    test_llm_fallbacks()
    test_llm_clamps()
    test_scripted_uses_measured_operator()
    test_ucb_learns()
    test_adaptive_planner_end_to_end()
    print("\n" + "=" * 72)
    print(f"全部通过：{passed} 项测试")
    print("=" * 72)
