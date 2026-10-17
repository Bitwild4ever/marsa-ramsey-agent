"""测试 ramsey_compare 工具的判定规则是否真的会拒绝过度概括。

重点：
1. 两个算子表现相当时，工具必须返回 inconclusive，且 winner 为 None。
2. 一个算子明显更好时，返回 clear_winner。
3. 某算子已解出时，返回 solved。
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.ops import compare                                # noqa: E402

passed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def test_tie_detected():
    """n=44 上 tabu_focus 与 tabu_violation 在种子噪声内打平 —— 必须判无定论。"""
    r = compare(["tabu_focus", "tabu_violation"], n=44, s=5, t=5,
                budget=3.0, seeds=3, seed_base=100)
    print(f"    margin={r['margin']}  noise_floor={r['noise_floor']}  "
          f"verdict={r['verdict']}")
    assert r["verdict"] == "inconclusive_within_noise", (
        f"打平的情况下应判无定论，实得 {r['verdict']}")
    assert r["winner"] is None, "无定论时 winner 必须为 None"
    assert "无定论" in r["conclusion"], "结论必须明说无定论"
    ok("两个算子表现相当时，工具拒绝给出胜者并标记为无定论")


def test_clear_winner_detected():
    """把明显较弱的 sa 与 tabu_focus 比（大 n 上差距远超噪声）—— 应判 clear_winner。"""
    r = compare(["sa", "tabu_focus"], n=43, s=5, t=5,
                budget=3.0, seeds=3, seed_base=200)
    print(f"    best={r['best']}  margin={r['margin']}  "
          f"noise={r['noise_floor']}  verdict={r['verdict']}")
    assert r["verdict"] == "clear_winner", (
        f"差距应远超噪声，实得 {r['verdict']}")
    assert r["winner"] == "tabu_focus", r["winner"]
    ok("一个算子明显更好时，工具正确给出 clear_winner")


def test_solved_detected():
    """n=30 上多种算子都能解出 —— 应判 solved 并列出解出的算子。"""
    r = compare(["tabu_focus", "tabu_violation"], n=30, s=5, t=5,
                budget=1.0, seeds=2, seed_base=300)
    assert r["verdict"] == "solved", f"应判 solved，实得 {r['verdict']}"
    assert r["winner"] in r["solved_operators"]
    ok(f"已解出的情况正确识别（winner={r['winner']}，"
       f"解出算子={r['solved_operators']}）")


def test_invalid_inputs():
    r = compare(["tabu_focus"], n=30)
    assert r["status"] == "error", "单个算子应报错"
    r2 = compare(["tabu_focus", "nope"], n=30)
    assert r2["status"] == "error", "未知算子应报错"
    ok("参数校验正确（单算子 / 未知算子都报错）")


def test_conclusion_never_overclaims():
    """不论 verdict 如何，非 solved 的结论都必须自带免责说明。"""
    r = compare(["tabu_focus", "tabu_violation"], n=38, s=5, t=5,
                budget=2.0, seeds=3, seed_base=400)
    c = r["conclusion"]
    if r["verdict"] != "solved":
        assert ("不是任何存在性结论" in c) or ("不得宣称" in c), (
            f"非 solved 的结论必须自带免责说明：{c}")
    else:
        # solved 分支确实断言了下界 —— 但此时它过了独立验证器，所以是合法的
        assert r["winner"] is not None and r["solved_operators"]
    ok(f"非 solved 结论均自带免责说明（本次 verdict={r['verdict']}）")


if __name__ == "__main__":
    print("=" * 70)
    print("MARSA 统计纪律自检工具测试")
    print("=" * 70)
    test_tie_detected()
    test_clear_winner_detected()
    test_solved_detected()
    test_invalid_inputs()
    test_conclusion_never_overclaims()
    print("\n" + "=" * 70)
    print(f"全部通过：{passed} 项测试")
    print("=" * 70)
