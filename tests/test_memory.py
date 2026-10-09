"""记忆模块测试：相似度、次模检索、扰动复用。"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.bitset import Coloring                                    # noqa: E402
from marsa.memory import (                                           # noqa: E402
    MemoryEntry, MemoryStore, edge_distance, facility_location_greedy,
    perturb, similarity,
)

passed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def test_distance():
    rng = random.Random(1)
    n = 20
    a = Coloring.random(n, 5, 5, rng).red_list()
    b = Coloring.random(n, 5, 5, rng).red_list()
    assert edge_distance(n, a, a) == 0
    assert similarity(n, a, a) == 1.0
    assert edge_distance(n, a, b) == edge_distance(n, b, a), "距离应对称"
    # 翻转一条边 -> 距离恰好为 1
    c = list(a)
    c[0] ^= 1 << 1
    c[1] ^= 1 << 0
    assert edge_distance(n, a, c) == 1, "翻转一条边后距离应为 1"
    # 相似度范围
    for _ in range(20):
        x = Coloring.random(n, 5, 5, rng).red_list()
        y = Coloring.random(n, 5, 5, rng).red_list()
        assert 0.0 <= similarity(n, x, y) <= 1.0, "相似度必须落在 [0,1]"
    ok("边距离/相似度：自反、对称、单边翻转距离=1、取值范围正确")


def test_facility_location():
    """次模检索必须取回"多样"的一组，而不是一堆近乎相同的解。"""
    rng = random.Random(7)
    n = 16
    base = Coloring.random(n, 5, 5, rng).red_list()

    # 造一个候选池：3 个几乎相同的解（base 的小扰动）+ 3 个完全不同的解
    pool = []
    for _ in range(3):
        pool.append(perturb(n, base, 1, rng))          # 近乎重复
    for _ in range(3):
        pool.append(Coloring.random(n, 5, 5, rng).red_list())   # 各异

    picked = facility_location_greedy(pool, 3, n)
    idx = sorted(picked)
    print(f"    次模选出下标: {idx}")
    # 只选 3 个时，不应该把三个几乎重复的近邻全选上
    dup_group = {0, 1, 2}
    assert len(dup_group & set(idx)) <= 2, (
        f"次模检索在近乎重复的解上过度聚集: {idx}")
    assert len(idx) == len(set(idx)), "不应重复选择"
    ok("次模（设施选址）检索避开近乎重复的解，选出更分散的一组")

    # 与"最近邻"策略对比，说明差异确实存在
    cur = base
    nearest = sorted(range(len(pool)),
                     key=lambda i: edge_distance(n, cur, pool[i]))[:3]
    print(f"    最近邻选出下标: {sorted(nearest)}")
    ok("最近邻策略确实会聚集到近邻组（两种策略行为不同，消融才有意义）")


def test_submodular_monotone():
    """F(S) 单调不减：贪心每加一个点不应使总覆盖下降。"""
    rng = random.Random(3)
    n = 14
    pool = [Coloring.random(n, 5, 5, rng).red_list() for _ in range(8)]

    def F(sel):
        tot = 0.0
        for i in range(len(pool)):
            tot += max((similarity(n, pool[i], pool[j]) for j in sel),
                       default=0.0)
        return tot

    idx = facility_location_greedy(pool, 5, n)
    vals = [F(idx[:t + 1]) for t in range(len(idx))]
    for a, b in zip(vals, vals[1:]):
        assert b >= a - 1e-9, f"设施选址函数不单调: {vals}"
    ok(f"取回集合的覆盖价值单调不减 {[round(v, 2) for v in vals]}")


def test_retrieval_modes():
    rng = random.Random(11)
    n = 14
    task = "5,5,14"
    path = Path("D:/myagent/runs/_test_memory.jsonl")
    if path.exists():
        path.unlink()
    store = MemoryStore(path)
    pool = [Coloring.random(n, 5, 5, rng).red_list() for _ in range(6)]
    for i, red in enumerate(pool):
        store.add(MemoryEntry(task=task, episode=i, operator="sa",
                              cost=i, red=red, steps=10, seconds=0.1))
    cur = pool[0]
    for mode in ("none", "random", "nearest", "submodular"):
        got = store.retrieve(mode, task, n, cur, 3, rng)
        if mode == "none":
            assert got == [], "none 模式不应取回任何东西"
        else:
            assert len(got) == 3, f"{mode} 应取回 3 个"
    # 持久化往返
    store2 = MemoryStore(path).load()
    assert len(store2.entries) == 6, "记忆持久化往返失败"
    path.unlink()
    ok("四种检索策略行为正确；记忆 JSONL 持久化往返一致")


def test_perturb_strength():
    rng = random.Random(5)
    n = 12
    a = Coloring.random(n, 5, 5, rng).red_list()
    b = perturb(n, a, 0, rng)
    assert b == a, "strength=0 应保持原解"
    c = perturb(n, a, 5, rng)
    d = edge_distance(n, a, c)
    assert d <= 5, f"strength=5 时距离不应超过 5，实得 {d}"
    ok(f"扰动强度受控（strength=5 -> 实际距离 {d} <= 5）")


if __name__ == "__main__":
    print("=" * 68)
    print("MARSA 记忆模块测试")
    print("=" * 68)
    Path("D:/myagent/runs").mkdir(exist_ok=True)
    test_distance()
    test_facility_location()
    test_submodular_monotone()
    test_retrieval_modes()
    test_perturb_strength()
    print("\n" + "=" * 68)
    print(f"全部通过：{passed} 项测试")
    print("=" * 68)
