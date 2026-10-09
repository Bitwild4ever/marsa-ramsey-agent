"""位掩码图运算：单色团计数与 O(n^(k-2)) 增量更新。

数学依据
--------
完全图 K_n 的红/蓝二染色。目标是**违反度**：红色 K_s 的个数 + 蓝色 K_t 的个数
（该值为 0 时就得到一个合法的 (s,t)-染色，即证 R(s,t) > n）。

对一条边 e=(u,v)，令

    A_c(e) = { w : (u,w) 与 (v,w) 同为颜色 c }

则**包含 e 的红色 K_s** 恰为 A_红(e) 中的红色 (s-2)-团个数；蓝色同理为
A_蓝(e) 中的蓝色 (t-2)-团个数。又因每个红色 K_s 含 C(s,2) 条边，故有恒等式

    sum_e  K_s^红(e)  =  C(s,2) * (#红色 K_s)
    sum_e  K_t^蓝(e)  =  C(t,2) * (#蓝色 K_t)

翻转一条边 (u,v) 时 A_红、A_蓝 都**不变**（它们只依赖 u-w、v-w 这些边），
所以违反度的变化量恰为

    Δ = [新 K_s^红(u,v) + 新 K_t^蓝(u,v)] - [旧 K_s^红(u,v) + 旧 K_t^蓝(u,v)]

每次翻转只需两次小规模团计数，而无需重新枚举 C(n,s) 个 s-子集。
对 n=46、s=t=5：(46 choose 5) = 1,370,754，增量化后每步仅约 46 次 popcount。
"""

from __future__ import annotations

from math import comb


def count_cliques(mask: int, adj: list[int], k: int) -> int:
    """统计顶点集 mask 诱导子图中（按 adj 判定）的 k-团个数。

    按顶点序号递增枚举，保证每个团被恰好计数一次。
    """
    if k <= 1:
        return mask.bit_count()
    if k == 2:                                  # 数边
        total = 0
        m = mask
        while m:
            vb = m & -m
            v = vb.bit_length() - 1
            m ^= vb
            total += (adj[v] & m).bit_count()
        return total
    total = 0
    m = mask
    while m:
        vb = m & -m
        v = vb.bit_length() - 1
        m ^= vb
        total += count_cliques(adj[v] & m, adj, k - 1)
    return total


def enumerate_cliques(mask: int, adj: list[int], k: int,
                      limit: int = 0) -> list[tuple[int, ...]]:
    """枚举 mask 诱导子图中的 k-团。按顶点递增序枚举，保证每个团只出现一次。

    limit > 0 时最多返回 limit 个，用于在违反度很大时避免枚举爆炸。
    """
    res: list[tuple[int, ...]] = []

    def rec(cur: int, chosen: list[int]) -> None:
        if limit and len(res) >= limit:
            return
        if len(chosen) == k:
            res.append(tuple(chosen))
            return
        m = cur
        while m:
            if limit and len(res) >= limit:
                return
            vb = m & -m
            v = vb.bit_length() - 1
            m ^= vb
            rec(adj[v] & m, chosen + [v])

    if k <= 0:
        return [()]
    rec(mask, [])
    return res


class Coloring:
    """K_n 的一个 2-染色，带有 (s,t) 违反度的增量维护。

    red[i] / blue[i] 是顶点 i 的红 / 蓝邻居位掩码，二者始终互补一致。
    """

    __slots__ = ("n", "s", "t", "full", "red", "blue", "den_s", "den_t", "_cost")

    def __init__(self, n: int, s: int, t: int, red: list[int] | None = None):
        self.n, self.s, self.t = n, s, t
        self.full = (1 << n) - 1
        self.den_s, self.den_t = comb(s, 2), comb(t, 2)
        if red is None:
            self.red = [0] * n
        else:
            self.red = [x & self.full & ~(1 << i) for i, x in enumerate(red)]
        self.blue = [self.full & ~self.red[i] & ~(1 << i) for i in range(n)]
        self._cost: int | None = None

    # ---------- 构造 ----------

    @classmethod
    def random(cls, n: int, s: int, t: int, rng, p: float = 0.5) -> "Coloring":
        red = [0] * n
        for i in range(n):
            for j in range(i + 1, n):
                if rng.random() < p:
                    red[i] |= 1 << j
                    red[j] |= 1 << i
        return cls(n, s, t, red)

    def copy(self) -> "Coloring":
        c = Coloring(self.n, self.s, self.t)
        c.red = list(self.red)
        c.blue = list(self.blue)
        c._cost = self._cost
        return c

    # ---------- 基本查询 ----------

    def is_red(self, i: int, j: int) -> bool:
        return bool(self.red[i] >> j & 1)

    def edges(self) -> list[tuple[int, int]]:
        return [(i, j) for i in range(self.n) for j in range(i + 1, self.n)]

    # ---------- 代价 ----------

    def violations_through(self, i: int, j: int) -> tuple[int, int]:
        """经过边 (i,j) 的 (红色 K_s 数, 蓝色 K_t 数)。"""
        if self.is_red(i, j):
            a = self.red[i] & self.red[j]
            return count_cliques(a, self.red, self.s - 2), 0
        a = self.blue[i] & self.blue[j]
        return 0, count_cliques(a, self.blue, self.t - 2)

    def total_cost(self, check_identities: bool = False) -> int:
        """违反度 = 红色 K_s 个数 + 蓝色 K_t 个数。目标为 0。"""
        acc_s = acc_t = 0
        for i in range(self.n):
            for j in range(i + 1, self.n):
                a, b = self.violations_through(i, j)
                acc_s += a
                acc_t += b
        if check_identities:
            if acc_s % self.den_s or acc_t % self.den_t:
                raise AssertionError(
                    f"恒等式被破坏: acc_s={acc_s} (mod {self.den_s}), "
                    f"acc_t={acc_t} (mod {self.den_t})")
        return acc_s // self.den_s + acc_t // self.den_t

    def cost(self) -> int:
        """带缓存的违反度。"""
        if self._cost is None:
            self._cost = self.total_cost()
        return self._cost

    def invalidate(self) -> None:
        self._cost = None

    def violation_cliques(self, i: int, j: int,
                          limit: int = 0) -> list[tuple[int, ...]]:
        """经过边 (i,j) 的**具体**单色团（返回顶点元组列表）。

        与 violations_through 只数个数不同，这里给出实际的团，用于
        "按违反团构造候选边"的策略。
        """
        if self.is_red(i, j):
            a = self.red[i] & self.red[j]
            cs = enumerate_cliques(a, self.red, self.s - 2, limit)
        else:
            a = self.blue[i] & self.blue[j]
            cs = enumerate_cliques(a, self.blue, self.t - 2, limit)
        return [tuple(sorted((i, j) + c)) for c in cs]

    def violation_edges(self, cap: int = 6000) -> list[tuple[int, int]]:
        """收集当前所有违反团所涉及的边（用于 VLNS 式候选表）。

        代价约等于一次 total_cost()，因此只应每隔若干步调用一次。
        """
        out: set[tuple[int, int]] = set()
        for i in range(self.n):
            for j in range(i + 1, self.n):
                for c in self.violation_cliques(i, j):
                    L = len(c)
                    for a in range(L):
                        for b in range(a + 1, L):
                            x, y = c[a], c[b]
                            out.add((x, y) if x < y else (y, x))
                    if len(out) > cap:
                        return sorted(out)
        return sorted(out)

    def delta_of_flip(self, i: int, j: int) -> int:
        """**不修改状态**地计算翻转边 (i,j) 会带来的违反度变化。

        因为 A_红、A_蓝 不依赖 (u,v) 自身的颜色，所以翻转后的取值可以直接算：
        翻转后边为蓝 → A_蓝 中的蓝色 (t-2)-团；翻转后为红 → A_红 中的红色 (s-2)-团。
        """
        a0, b0 = self.violations_through(i, j)
        if self.is_red(i, j):
            a = self.blue[i] & self.blue[j]
            return count_cliques(a, self.blue, self.t - 2) - (a0 + b0)
        a = self.red[i] & self.red[j]
        return count_cliques(a, self.red, self.s - 2) - (a0 + b0)

    def apply_flip(self, i: int, j: int) -> int:
        """翻转边 (i,j) 的颜色，返回违反度的**精确**变化量。"""
        a0, b0 = self.violations_through(i, j)
        bi, bj = 1 << j, 1 << i
        if self.red[i] >> j & 1:
            self.red[i] &= ~bi
            self.red[j] &= ~bj
            self.blue[i] |= bi
            self.blue[j] |= bj
        else:
            self.blue[i] &= ~bi
            self.blue[j] &= ~bj
            self.red[i] |= bi
            self.red[j] |= bj
        a1, b1 = self.violations_through(i, j)
        delta = (a1 + b1) - (a0 + b0)
        if self._cost is not None:
            self._cost += delta
        return delta

    # ---------- 导出 ----------

    def red_list(self) -> list[int]:
        return list(self.red)

    def red_edges(self) -> set[tuple[int, int]]:
        out = set()
        for i in range(self.n):
            m = self.red[i]
            while m:
                b = m & -m
                j = b.bit_length() - 1
                m ^= b
                out.add((min(i, j), max(i, j)))
        return out
