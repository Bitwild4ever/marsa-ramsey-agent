"""组合选择器测试（阶段 1 的判决组件，必须先把逻辑验对）。"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.selector import PortfolioSelector      # noqa: E402

passed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def test_explores_untried_first():
    sel = PortfolioSelector()
    rng = random.Random(0)
    arms = ["a", "b", "c"]
    picked = []
    for _ in range(3):
        p, _ = sel.choose("bk", arms, rng)
        picked.append(p)
        sel.observe("bk", p, 0.0)      # 契约：choose 之后必须 observe，否则不计次数
    assert sorted(picked) == arms, f"应先各试一遍，实得 {picked}"
    ok("UCB1 优先探索未尝试过的算子（各试一遍后才开始利用）")


def test_converges_to_best():
    sel = PortfolioSelector()
    rng = random.Random(1)
    arms = ["bad", "mid", "best"]
    truth = {"bad": 0.1, "mid": 0.4, "best": 0.9}
    picks = {a: 0 for a in arms}
    for _ in range(400):
        p, _ = sel.choose("bk", arms, rng)
        picks[p] += 1
        sel.observe("bk", p, truth[p])
    assert picks["best"] > picks["bad"] and picks["best"] > picks["mid"], picks
    assert sel.greedy("bk", arms) == "best"
    ok(f"UCB1 收敛到最优算子：{picks}，greedy 选出 {sel.greedy('bk', arms)}")


def test_buckets_are_independent():
    sel = PortfolioSelector()
    rng = random.Random(2)
    arms = ["x", "y"]
    for _ in range(50):
        p, _ = sel.choose("B1", arms, rng)
        sel.observe("B1", p, 1.0 if p == "x" else 0.0)
    for _ in range(50):
        p, _ = sel.choose("B2", arms, rng)
        sel.observe("B2", p, 1.0 if p == "y" else 0.0)
    assert sel.greedy("B1", arms) == "x"
    assert sel.greedy("B2", arms) == "y"
    ok("不同桶互相独立学习（B1 选 x，B2 选 y）")


def test_unknown_bucket_and_arm():
    sel = PortfolioSelector()
    rng = random.Random(3)
    assert sel.greedy("never-seen", ["a", "b"]) is None, "未知桶应返回 None"
    # 桶内只有部分算子的经验时，应只在这些算子里选
    sel.observe("bk", "a", 0.5)
    sel.observe("bk", "b", 0.9)
    assert sel.greedy("bk", ["a", "b", "c"]) == "b"
    assert sel.greedy("bk", ["c"]) is None, "只应在有经验的算子里选"
    ok("未知桶返回 None；桶内只按已有经验的算子决策")


def test_reproducible():
    def run(seed):
        sel = PortfolioSelector()
        rng = random.Random(seed)
        arms = ["a", "b", "c"]
        seq = []
        for i in range(30):
            p, _ = sel.choose("bk", arms, rng)
            seq.append(p)
            sel.observe("bk", p, (i % 7) / 7)
        return seq, sel.greedy("bk", arms)
    s1, g1 = run(11)
    s2, g2 = run(11)
    assert s1 == s2 and g1 == g2, "同种子必须完全可复现"
    ok("同种子下选择序列与 greedy 结果完全可复现")


if __name__ == "__main__":
    print("=" * 68)
    print("MARSA 组合选择器测试")
    print("=" * 68)
    test_explores_untried_first()
    test_converges_to_best()
    test_buckets_are_independent()
    test_unknown_bucket_and_arm()
    test_reproducible()
    print("\n" + "=" * 68)
    print(f"全部通过：{passed} 项测试")
    print("=" * 68)
