"""对称族（循环图）测试。

阶段 2 的全部结论都建立在"循环图表示正确"之上，因此先把它验死：
邻接必须对称无自环、连接集必须满足 S = -S、并且能用已知精确值做交叉检查。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.symmetric import (                                   # noqa: E402
    circulant_red, circulant_size, conn_from_bits, cost_of_bits,
    free_offsets, verify_bits,
)

passed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def test_adjacency_wellformed():
    for n in (5, 6, 7, 16, 30, 43):
        full = (1 << circulant_size(n)) - 1
        for bits in (0, 1, 0b101, full, full ^ 1):
            red = circulant_red(n, bits)
            for i in range(n):
                assert red[i] >> i & 1 == 0, f"不应有自环 n={n}"
                for j in range(n):
                    if red[i] >> j & 1:
                        assert red[j] >> i & 1, f"邻接不对称 n={n} bits={bits}"
    ok("各 n 下循环图邻接对称、无自环（含全 0 / 全 1 / 交替等边界）")


def test_connection_set_is_symmetric():
    for n in (5, 8, 30, 43):
        for bits in range(1 << min(circulant_size(n), 8)):
            conn = conn_from_bits(n, bits)
            assert 0 not in conn, "连接集不应包含 0"
            for d in conn:
                assert (n - d) % n in conn, f"连接集不满足 S=-S: n={n} bits={bits}"
    ok("连接集始终满足 S = -S 且不含 0")


def test_known_values():
    # R(3,3)=6：5 顶点上的 5-圈是循环图（S={1,4}），是合法 (3,3)-染色
    bits5 = 0b01
    assert sorted(conn_from_bits(5, bits5)) == [1, 4]
    assert cost_of_bits(5, 3, 3, bits5) == 0, "5-圈应为合法 (3,3)-染色"
    good, _ = verify_bits(5, 3, 3, bits5)
    assert good, "独立验证器应确认 5-圈合法"
    ok("已知值自检：5-圈（循环图 S={1,4}）是合法 (3,3)-染色，且过独立验证器")

    # 6 顶点上不存在合法 (3,3)-染色，循环图是子族，更不可能
    best6 = min(cost_of_bits(6, 3, 3, b) for b in range(1 << circulant_size(6)))
    assert best6 > 0, f"n=6 循环图族不应有合法解，实得最小违反度 {best6}"
    ok(f"已知值自检：n=6 循环图族最小违反度 = {best6} > 0（与 R(3,3)=6 一致）")

    # 4 顶点上的 4-圈是循环图，是合法 (3,3)-染色（R(3,3)=6 的子集）
    assert cost_of_bits(4, 3, 3, 0b01) == 0
    ok("4-圈亦为合法 (3,3)-染色")


def test_verify_agrees_with_cost():
    """cost==0 与独立验证器必须完全等价。"""
    checked = 0
    for n, (s, t) in [(10, (3, 4)), (14, (3, 5)), (18, (4, 4)), (24, (4, 5))]:
        full = (1 << circulant_size(n)) - 1
        for bits in range(0, full + 1, max(1, full // 40)):
            c = cost_of_bits(n, s, t, bits)
            good, _ = verify_bits(n, s, t, bits)
            assert good == (c == 0), (
                f"n={n} (s,t)={s},{t} bits={bits}: cost={c} 但 verify={good}")
            checked += 1
    ok(f"{checked} 组抽样：cost==0 与独立验证器的判定完全等价")


def test_free_offsets_size():
    for n in (30, 43, 45, 46):
        assert len(free_offsets(n)) == n // 2
    ok("自由参数数 = floor(n/2)（n=43/45/46 分别为 21/22/23）")


if __name__ == "__main__":
    print("=" * 70)
    print("MARSA 对称族（循环图）测试")
    print("=" * 70)
    test_adjacency_wellformed()
    test_connection_set_is_symmetric()
    test_known_values()
    test_verify_agrees_with_cost()
    test_free_offsets_size()
    print("\n" + "=" * 70)
    print(f"全部通过：{passed} 项测试")
    print("=" * 70)
