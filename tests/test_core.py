"""核心正确性测试。

本项目全部结论都建立在"违反度函数是对的"这一点上，所以这里做三重交叉验证：

  A. 快速代价（位掩码 + 团计数 + 恒等式）  ==  暴力代价（显式矩阵 + 子集枚举）
  B. 增量翻转代价  ==  翻转后整体重算的代价（逐步、长序列）
  C. 缓存代价  ==  无缓存重算；且 verify() 的合法性判定  ==  (代价 == 0)

不依赖 pytest，直接用 assert 与打印，方便在任何 Python 上运行。
"""

from __future__ import annotations

import random
import sys
import time
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.bitset import Coloring                       # noqa: E402
from marsa.search import SAConfig, run_sa                # noqa: E402
from marsa.verifier import (                            # noqa: E402
    brute_cost, parse_graph6, to_graph6, verify,
)

SHAPES = [(3, 3), (4, 4), (5, 5), (3, 5), (4, 5), (3, 4)]

passed = 0


def ok(msg: str) -> None:
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def test_fast_equals_brute() -> None:
    print("\nA. 快速代价 vs 暴力代价（随机图，多种 (s,t)）")
    rng = random.Random(20261009)
    for trial in range(40):
        n = rng.randint(7, 17)
        s, t = SHAPES[trial % len(SHAPES)]
        if s > n or t > n:
            continue
        c = Coloring.random(n, s, t, rng, p=rng.choice([0.3, 0.5, 0.7]))
        fast = c.total_cost(check_identities=True)
        slow = brute_cost(n, c.red_list(), s, t)
        assert fast == slow, f"n={n} (s,t)=({s},{t}): fast={fast} slow={slow}"
    ok(f"40 组随机图，快速代价与暴力代价完全一致（含恒等式校验）")


def test_incremental_flips() -> None:
    print("\nB. 增量翻转 vs 整体重算（长序列逐步核对）")
    rng = random.Random(42)
    total_flips = 0
    for n, (s, t) in [(14, (5, 5)), (16, (4, 5)), (18, (5, 5)), (12, (3, 3))]:
        c = Coloring.random(n, s, t, rng)
        c.cost()                                    # 预热缓存
        for _ in range(300):
            i = rng.randrange(n)
            j = rng.randrange(n)
            while j == i:
                j = rng.randrange(n)
            c.apply_flip(i, j)
            recomputed = c.total_cost()
            assert c.cost() == recomputed, (
                f"n={n} (s,t)=({s},{t}) 第 {total_flips} 次翻转后 "
                f"缓存={c.cost()} 重算={recomputed}")
            total_flips += 1
    ok(f"{total_flips} 次翻转，增量代价与整体重算逐次一致")


def test_cache_and_verify_agree() -> None:
    print("\nC. 缓存一致性 & verify() 与代价的等价性")
    rng = random.Random(7)
    legal = 0
    for _ in range(25):
        n = rng.randint(8, 15)
        s, t = SHAPES[rng.randrange(len(SHAPES))]
        if s > n or t > n:
            continue
        c = Coloring.random(n, s, t, rng)
        cost = c.cost()
        assert cost == c.total_cost(), "缓存与重算不一致"
        good, witness = verify(n, c.red_list(), s, t)
        assert good == (cost == 0), f"verify={good} 但 cost={cost}"
        if not good and witness is not None:
            k = len(witness)
            assert (k == s) or (k == t), "反例大小既不是 s 也不是 t"
        legal += int(good)
    ok(f"缓存与重算一致；verify() 判定与 (代价==0) 完全等价（其中 {legal} 个合法）")


def test_graph6_roundtrip() -> None:
    print("\nD. graph6 导入导出往返")
    rng = random.Random(99)
    for n in (10, 25, 43, 46):
        c = Coloring.random(n, 5, 5, rng)
        line = to_graph6(n, c.red_list())
        n2, red2 = parse_graph6(line)
        assert n2 == n, "n 不一致"
        assert red2 == c.red_list(), "往返后邻接表不一致"
    ok("n = 10/25/43/46 的 graph6 往返完全一致（这是导入公开已知构造的通道）")


def test_known_small_values() -> None:
    print("\nE. 已知小 Ramsey 值的结构自检")
    # R(3,3)=6：5 个顶点的 5-圈染色合法（红=5-圈，蓝=补 5-圈），6 个顶点必不合法
    c5 = Coloring(5, 3, 3)
    for i in range(5):
        c5.apply_flip(i, (i + 1) % 5)
    assert c5.cost() == 0, f"5-圈应为合法 (3,3)-染色，实得代价 {c5.cost()}"
    good, _ = verify(5, c5.red_list(), 3, 3)
    assert good
    # 同样的圈结构放到 6 个顶点上必然产生单色三角形
    c6 = Coloring(6, 3, 3)
    for i in range(5):
        c6.apply_flip(i, (i + 1) % 5)
    assert c6.cost() > 0, "6 顶点不应存在合法 (3,3)-染色"
    ok("5-圈是合法 (3,3)-染色；扩到 6 顶点必然出现单色三角形（R(3,3)=6 自检通过）")


def test_schedule_decoupled_from_steps() -> None:
    """回归测试：退火时间表必须与 steps 上限解耦。

    真实踩过的坑：按墙钟时间预算运行时 steps 被设为极大值（1e9），
    若衰减率直接用 (t1/t0)^(1/steps) 计算，则衰减率≈1，温度几乎不降，
    退火退化成随机游走，结果会差好几倍。

    判定方式：同一种子、同一名义时间表下，"时间预算模式"因为会在时间表
    结束后重新升温继续跑，做的工作**严格更多**，所以它的最优代价不应比
    "固定 15 万步模式"差。若退化 bug 复现（温度几乎不降、变成随机游走），
    时间预算模式的结果会比固定步数模式差好几倍，本断言立刻失败。
    """
    print("\nG. 回归：时间表与步数上限解耦（曾出现的退火失效 bug）")
    n, s, t = 36, 5, 5
    fixed = run_sa(SAConfig(n=n, s=s, t=t, steps=150_000, seed=7,
                            report_every=0, keep_elites=0))
    timed = run_sa(SAConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=6.0,
                            seed=7, report_every=0, keep_elites=0))
    assert timed.steps_done >= 150_000, (
        f"6 秒内未跑满 150000 步（实际 {timed.steps_done}），测试前提不成立")
    slack = max(2, int(0.2 * fixed.best_cost))
    assert timed.best_cost <= fixed.best_cost + slack, (
        f"时间预算模式明显劣于固定步数模式：timed={timed.best_cost} "
        f"fixed={fixed.best_cost}（允许松弛 {slack}）；"
        f"说明退火时间表又被 steps 上限破坏了")
    ok(f"时间预算模式（{timed.steps_done:,} 步，含重升温）不劣于固定 "
       f"{fixed.steps_done:,} 步模式：{timed.best_cost} <= {fixed.best_cost}")


def test_violation_enumeration() -> None:
    """团枚举必须与"计数"和"暴力枚举"三者一致。

    "按违反团构造候选边"这一策略完全依赖枚举的正确性，所以单独验收：
      * sum over 边 of (#经过该边的单色团) == C(s,2)*#红K_s + C(t,2)*#蓝K_t
      * 枚举出的具体团，必须真的每个都是单色完全子图
      * violation_edges 里的每条边都必须真的属于某个违反团
    """
    print("\nH. 违反团枚举（VLNS 候选表的地基）")
    rng = random.Random(31337)
    checked = 0
    for trial in range(12):
        n = rng.randint(8, 14)
        s, t = SHAPES[trial % len(SHAPES)]
        if s > n or t > n:
            continue
        c = Coloring.random(n, s, t, rng, p=rng.choice([0.35, 0.5, 0.65]))
        # 1) 枚举计数 vs 增量计数
        acc_s = acc_t = 0
        for i in range(n):
            for j in range(i + 1, n):
                cl = c.violation_cliques(i, j)
                is_red = c.is_red(i, j)
                if is_red:
                    acc_s += len(cl)
                else:
                    acc_t += len(cl)
                # 2) 每个枚举出的团必须真的是单色团
                for quad in cl:
                    assert len(quad) == (s if is_red else t), "团大小不对"
                    for a, b in combinations(quad, 2):
                        assert c.is_red(a, b) is is_red, "枚举出的团不是单色"
        a0, b0 = 0, 0
        for i in range(n):
            for j in range(i + 1, n):
                x, y = c.violations_through(i, j)
                a0 += x
                b0 += y
        assert acc_s == a0 and acc_t == b0, (
            f"枚举计数 {acc_s}/{acc_t} != 增量计数 {a0}/{b0}")
        # 3) violation_edges 的每条边都应属于某个违反团
        ve = c.violation_edges()
        if c.cost() > 0:
            assert ve, "代价 > 0 却收集不到任何违反边"
            in_clique = set()
            for i in range(n):
                for j in range(i + 1, n):
                    for quad in c.violation_cliques(i, j):
                        for a, b in combinations(quad, 2):
                            in_clique.add((min(a, b), max(a, b)))
            assert set(ve) == in_clique, "violation_edges 与逐边枚举不一致"
        checked += 1
    ok(f"{checked} 组随机图：枚举计数 == 增量计数，且每个团都确实是单色完全子图")


def test_perturbation_mechanism() -> None:
    """卡住扰动：关闭时绝不触发，开启时必须触发，且同种子完全可复现。

    扰动会清空禁忌表与候选缓存，属于容易写错的状态操作，因此单独验收。
    """
    print("\nI. 卡住扰动机制")
    from marsa.search import TabuConfig, run_tabu
    n, s, t = 30, 5, 5
    common = dict(n=n, s=s, t=t, steps=1500, seed=3, report_every=0,
                  keep_elites=0, candidate_mode="violation",
                  candidate_size=128, target_cost=-1)
    off = run_tabu(TabuConfig(**common, stall_limit=0))
    assert off.perturbations == 0, "stall_limit=0 时不应发生扰动"
    on = run_tabu(TabuConfig(**common, stall_limit=40, perturb_edges=2))
    assert on.perturbations > 0, "stall_limit=40 时应发生扰动"
    again = run_tabu(TabuConfig(**common, stall_limit=40, perturb_edges=2))
    assert (again.best_cost == on.best_cost
            and again.perturbations == on.perturbations), "同种子结果不可复现"
    # 扰动型与纯局部型应当产生不同的轨迹（否则这个维度是多余的）
    diff = (off.best_cost != on.best_cost
            or off.steps_done != on.steps_done
            or off.perturbations != on.perturbations)
    assert diff, "开启扰动后行为完全没有变化，说明该机制未生效"
    ok(f"扰动触发正确且可复现（关闭=0 次，开启={on.perturbations} 次，"
       f"最优代价 {off.best_cost} vs {on.best_cost}）")


def bench() -> None:
    print("\nF. 性能标定（这决定迭代曲线能画多密）")
    rng = random.Random(1)
    for n in (40, 43, 46):
        c = Coloring.random(n, 5, 5, rng)
        t0 = time.perf_counter()
        cost = c.total_cost()
        t1 = time.perf_counter()
        edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
        n_flips = 20000
        t2 = time.perf_counter()
        for k in range(n_flips):
            i, j = edges[rng.randrange(len(edges))]
            c.apply_flip(i, j)
        t3 = time.perf_counter()
        rate = n_flips / (t3 - t2)
        print(f"  n={n}: 整体计算代价 {cost} 用时 {t1 - t0:.3f}s | "
              f"增量翻转 {rate:,.0f} 次/秒")


if __name__ == "__main__":
    print("=" * 68)
    print("MARSA 核心正确性测试")
    print("=" * 68)
    test_fast_equals_brute()
    test_incremental_flips()
    test_cache_and_verify_agree()
    test_graph6_roundtrip()
    test_known_small_values()
    test_schedule_decoupled_from_steps()
    test_violation_enumeration()
    test_perturbation_mechanism()
    bench()
    print("\n" + "=" * 68)
    print(f"全部通过：{passed} 项测试")
    print("=" * 68)
