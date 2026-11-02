"""校验 agent 自建的 Cayley 群枚举器 —— 用已知锚点，而不是"能跑就行"。

锚点来源
--------
- 循环群 Z_n **就是**循环图族，可以用引擎 `marsa` 的完整刻画来校验；
- (4,6) 的循环族剖面来自本项目对 R(4,6) 的穷举（n=33 有 10 解，n=34/35 无解）；
- Z_46 上不可能有 (5,5) 染色（R(5,5) <= 46 已证），但 2^23 太慢，不适合放进测试。

**锚点的空间必须小**：这个枚举器只有约 5k masks/s，选大锚点会让测试跑不完。
设计测试时"结论确定"和"跑得完"要同时满足。
"""

import sys
import time

sys.path.insert(0, r"D:\myagent")
try:
    from impl import abelian_groups, enumerate_group
except ImportError:                                    # 在 workspace 里直接跑
    from cayley_exhaust import abelian_groups, enumerate_group

passed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


t0 = time.perf_counter()

# ---------------------------------------------------------------------------
# 锚点 1：Z_30 (5,5) 必须有解（空间 2^15）
#   引擎结论：循环图族在 n=30 上有 200 个合法 (5,5)-染色
# ---------------------------------------------------------------------------
r30 = enumerate_group(30, (30,), 5, 5, stop_at_first=True)
assert r30["solutions_found"], f"Z_30 应找到解，实得 {r30}"
assert not r30.get("skipped"), f"Z_30 不应被跳过：{r30}"
ok("Z_30 (5,5) 有解（与引擎判定一致）")

# ---------------------------------------------------------------------------
# 锚点 2：Z_33 (4,6) 的合法解计数必须等于 10（空间 2^16）
#   这个数字来自本项目对 R(4,6) 循环族的完整穷举
# ---------------------------------------------------------------------------
r33 = enumerate_group(33, (33,), 4, 6, stop_at_first=False)
assert r33["solutions_found"] == 10, \
    f"Z_33 (4,6) 应有 10 解，实得 {r33['solutions_found']}"
ok("Z_33 (4,6) 恰好 10 解（与 R(4,6) 穷举结果一致）")

# ---------------------------------------------------------------------------
# 锚点 3：Z_34 (4,6) 必须无解（空间 2^17）
#   反向自检：上一项证明它**找得到**解，这一项证明它**不是恒真**
# ---------------------------------------------------------------------------
r34 = enumerate_group(34, (34,), 4, 6, stop_at_first=True)
assert r34["solutions_found"] == 0, \
    f"Z_34 (4,6) 应无解，实得 {r34}"
ok("Z_34 (4,6) 无解（反向自检：判定函数不是恒真）")

# ---------------------------------------------------------------------------
# 锚点 4：与引擎的逐位穷举计数完全一致（空间 2^14）
#   这是两条独立实现的交叉比对
# ---------------------------------------------------------------------------
from marsa.symmetric import FastChecker, circulant_size       # noqa: E402

n = 28
mine = enumerate_group(n, (n,), 5, 5, stop_at_first=False)
fc = FastChecker(n, 5, 5)
ref = sum(1 for b in range(1 << circulant_size(n)) if fc.is_valid(b))
assert mine["solutions_found"] == ref, (
    f"Z_{n} 计数不一致：枚举器 {mine['solutions_found']} vs 引擎 {ref}")
ok(f"Z_{n} (5,5) 计数 = {ref}，与引擎逐位穷举完全一致")

# ---------------------------------------------------------------------------
# 锚点 5：群结构枚举本身要正确
#   注意 abelian_groups 返回的是**素幂分解**，例如 44 = 2^2 * 11 给出
#   (11, 4) 与 (11, 2, 2)。其中 (11,4) 因 11 与 4 互素而 ≅ Z_44（循环），
#   (11,2,2) 因含两个 2 而是非循环的。所以不能断言 "== (44,)"。
# ---------------------------------------------------------------------------
groups44 = abelian_groups(44)
assert groups44, "abelian_groups(44) 不应为空"
for g in groups44:
    prod = 1
    for f in g:
        prod *= f
    assert prod == 44, f"群分解 {g} 的乘积应为 44，实得 {prod}"

from math import gcd                                            # noqa: E402

cyclic = [g for g in groups44
          if all(gcd(a, b) == 1 for i, a in enumerate(g)
                 for b in g[i + 1:])]
assert len(cyclic) == 1, f"44 阶阿贝尔群中应恰有一个循环群，实得 {cyclic}"
ok(f"abelian_groups(44) 给出 {len(groups44)} 种群结构，其中恰一个循环群 {cyclic[0]}")

elapsed = time.perf_counter() - t0
checked = r30.get("checked", 0) + r34.get("checked", 0)
print()
print(f"全部通过：{passed} 项锚点校验")
print(f"耗时 {elapsed:.1f}s，检查约 {checked:,} 个候选")
if elapsed > 0 and checked:
    print(f"实测速度 ≈ {checked / elapsed:,.0f} masks/s")
    print("注意：引擎是约 200 万 masks/s，本枚举器慢约两个数量级；"
          "大空间必须分片。")
print("结论：该枚举器在循环族上与独立实现的引擎一致，可用于非循环群。")
