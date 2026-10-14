"""独立判定器 D —— 对枚举器做**全空间**第二路扫描。

与 marsa.symmetric.FastChecker 的刻意差异（实现独立）：
  1. 掩码来源：枚举**全部** C(n,k) 个顶点子集（不假设"平移对称 ⇒ 只需含 0 的
     子集"），把每个子集的偏移掩码**去重**后得到判定基准集合；
     FastChecker 只枚举含 0 的子集。
  2. 判定形式：用 `_subset_of` / `_disjoint` 两个独立的小函数按位测试，
     不写成 `(S & M) == M` / `(S & M) == 0` 这种同型写法。
  3. 不使用集合、不按 bit_count 排序、不合并 s==t 的情形。

数学命题本身是同一个（这是必然的——它就是要判定的东西），
但上面三条使它成为一条**独立的实现路径**：任何一处实现错误
（漏掉某一类子集、去重错误、位测试写反）都会让两路的合法解计数不同。
"""
from __future__ import annotations

from itertools import combinations


def _subset_of(S: int, M: int) -> bool:
    """M 的每一位是否都包含在 S 中（即 M & ~S == 0）。"""
    while M:
        b = M & -M
        if not (S & b):
            return False
        M ^= b
    return True


def _disjoint(S: int, M: int) -> bool:
    """M 与 S 是否无公共位。"""
    while M:
        b = M & -M
        if S & b:
            return False
        M ^= b
    return True


def _masks(n: int, k: int) -> list[int]:
    """**全部** C(n,k) 个顶点子集的"所需自由偏移"掩码，去重。

    偏移 d 与 n-d 是同一组边，故取 dd = min(d, n-d)（1 <= dd <= n//2），
    位序为 dd-1。
    """
    seen: set[int] = set()
    for verts in combinations(range(n), k):
        m = 0
        for a, b in combinations(verts, 2):
            d = b - a
            dd = d if d <= n - d else n - d
            m |= 1 << (dd - 1)
        seen.add(m)
    return sorted(seen)


class DirectChecker:
    __slots__ = ("n", "s", "t", "red", "blue")

    def __init__(self, n: int, s: int, t: int):
        self.n, self.s, self.t = n, s, t
        self.red = _masks(n, s) if s >= 2 else []
        self.blue = _masks(n, t) if t >= 2 else []

    def is_valid(self, bits: int) -> bool:
        S = bits
        for M in self.red:
            if _subset_of(S, M):
                return False
        for M in self.blue:
            if _disjoint(S, M):
                return False
        return True
