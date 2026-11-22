"""策略先验的纪律测试。

重点不是"它能推荐"，而是**它在不该推荐的时候必须拒绝推荐**。
一个会自信地推荐错算子的先验表，比没有先验更糟。
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os

# 用临时目录，绝不碰真实的 growth/prior.jsonl
_tmp = tempfile.mkdtemp(prefix="marsa_prior_test_")
os.environ["MARSA_GROWTH_DIR"] = _tmp

from marsa import prior                                        # noqa: E402

passed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def _episode(n, budget, per_op, verdict="clear_winner", winner=None):
    """造一条 episode 写进临时先验表。"""
    eps = []
    for op, vals in per_op.items():
        mean = sum(vals) / len(vals)
        std = (sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)) ** 0.5 \
            if len(vals) > 1 else 0.0
        eps.append((op, vals, mean, std))
    per = {op: {"violations": v, "mean": round(m, 2), "std": round(s, 2)}
           for op, v, m, s in eps}
    prior.record_comparison({
        "n": n, "s": 5, "t": 5, "budget_seconds": budget,
        "seeds": len(next(iter(per_op.values()))),
        "seed_base": 0, "verdict": verdict, "winner": winner,
        "margin": 0, "noise_floor": 0, "per_operator": per,
    })


def test_no_data():
    r = prior.recommend(n=99, s=5, t=5, budget=3.0)
    assert r["status"] == "no_data", r
    assert r["recommended"] is None
    ok("没有数据时返回 no_data，recommended 为 None")


def test_no_cross_n_transfer():
    """在 n=40 上有强证据，n=41 仍必须 no_data。"""
    for _ in range(2):
        _episode(40, 3.0, {"a": [100, 101, 100], "b": [200, 201, 200]})
    r40 = prior.recommend(n=40, s=5, t=5, budget=3.0)
    assert r40["status"] == "recommend", r40
    r41 = prior.recommend(n=41, s=5, t=5, budget=3.0)
    assert r41["status"] == "no_data", r41
    ok("n=40 有强证据，但 n=41 仍拒绝迁移（no_data）")


def test_clear_recommendation():
    for _ in range(2):
        _episode(42, 3.0, {"a": [100, 102, 101], "b": [200, 203, 201]})
    r = prior.recommend(n=42, s=5, t=5, budget=3.0)
    assert r["status"] == "recommend", r
    assert r["recommended"] == "a", r
    assert r["independent_episodes"] >= 2
    ok(f"证据充分且一致时推荐 a（{r['episode_wins']}）")


def test_inconclusive_within_noise():
    """差距小于噪声时必须拒绝推荐。"""
    for _ in range(2):
        _episode(43, 3.0, {"a": [100, 130, 110], "b": [102, 128, 112]})
    r = prior.recommend(n=43, s=5, t=5, budget=3.0)
    assert r["status"] == "inconclusive", r
    assert r["recommended"] is None
    ok("差距落在噪声内时返回 inconclusive，不猜")


def test_single_episode_refused():
    """只有一个 episode 时，即使差距很大也不推荐（实测教训）。"""
    _episode(44, 3.0, {"a": [100, 101, 100], "b": [200, 201, 200]})
    r = prior.recommend(n=44, s=5, t=5, budget=3.0)
    assert r["status"] in ("inconsistent_across_episodes", "too_few_samples"), r
    assert r["recommended"] is None
    ok(f"单个 episode 不足以推荐（status={r['status']}）")


def test_inconsistent_across_episodes():
    """两个 episode 各自支持不同算子时，必须拒绝推荐。"""
    _episode(45, 3.0, {"a": [100, 101, 100], "b": [200, 201, 200]})
    _episode(45, 3.0, {"a": [200, 201, 200], "b": [100, 101, 100]})
    r = prior.recommend(n=45, s=5, t=5, budget=3.0)
    assert r["recommended"] is None, r
    assert r["status"] in ("inconsistent_across_episodes", "inconclusive"), r
    ok(f"跨 episode 不一致时拒绝推荐（status={r['status']}）")


def test_solved_beats_measurement():
    """有算子解出过（违反度 0）时，它必须压倒均值比较。"""
    for _ in range(2):
        _episode(46, 3.0, {"a": [50, 51, 50], "b": [0, 60, 61]})
    r = prior.recommend(n=46, s=5, t=5, budget=3.0)
    assert r["status"] == "recommend", r
    assert r["recommended"] == "b", r
    assert r.get("basis") == "solved", r
    ok("解出过的算子优先（basis=solved）")


if __name__ == "__main__":
    print("=" * 70)
    print("策略先验纪律测试")
    print("=" * 70)
    test_no_data()
    test_no_cross_n_transfer()
    test_clear_recommendation()
    test_inconclusive_within_noise()
    test_single_episode_refused()
    test_inconsistent_across_episodes()
    test_solved_beats_measurement()
    print("\n" + "=" * 70)
    print(f"全部通过：{passed} 项测试")
    print("=" * 70)
