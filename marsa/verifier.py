"""独立验证器。

**刻意与搜索器走完全不同的算法路径**：这里用显式布尔邻接矩阵 + itertools 子集枚举，
不使用位掩码团计数。目的是防止"搜索器自报成功"——任何声称找到的合法染色，
都必须由本模块复核。两条独立实现互相对照，才敢把结果写进报告。
"""

from __future__ import annotations

from itertools import combinations


def to_matrix(n: int, red: list[int]) -> list[list[bool]]:
    """位掩码红邻接表 -> 显式布尔矩阵（红=True）。"""
    m = [[False] * n for _ in range(n)]
    for i in range(n):
        x = red[i]
        j = 0
        while x:
            if x & 1:
                m[i][j] = True
            x >>= 1
            j += 1
    return m


def find_mono_clique(n: int, adj: list[list[bool]], k: int,
                     want: bool) -> tuple[int, ...] | None:
    """在 adj 中寻找一个全为 want 的 k-子集；返回顶点元组或 None。"""
    if k < 2:
        return None
    for comb in combinations(range(n), k):
        ok = True
        for a, b in combinations(comb, 2):
            if adj[a][b] is not want:
                ok = False
                break
        if ok:
            return comb
    return None


def brute_cost(n: int, red: list[int], s: int, t: int) -> int:
    """暴力统计 红色 K_s 数 + 蓝色 K_t 数。仅供小规模交叉校验使用。"""
    adj = to_matrix(n, red)
    n_red = 0
    if s >= 2:
        for comb in combinations(range(n), s):
            if all(adj[a][b] for a, b in combinations(comb, 2)):
                n_red += 1
    n_blue = 0
    if t >= 2:
        for comb in combinations(range(n), t):
            if all(not adj[a][b] for a, b in combinations(comb, 2)):
                n_blue += 1
    return n_red + n_blue


def verify(n: int, red: list[int], s: int, t: int) -> tuple[bool, tuple | None]:
    """判定染色是否合法（无红色 K_s 且无蓝色 K_t）。

    返回 (是否合法, 反例)。合法时反例为 None。
    """
    adj = to_matrix(n, red)
    w = find_mono_clique(n, adj, s, True)
    if w is not None:
        return False, w
    w = find_mono_clique(n, adj, t, False)
    if w is not None:
        return False, w
    return True, None


def parse_graph6(line: str) -> tuple[int, list[int]]:
    """解析 graph6 格式，返回 (n, 红邻接位掩码表)。

    便于直接读入公开已知构造（例如 43 顶点的 (5,5)-图）。
    """
    data = [ord(c) - 63 for c in line.strip() if c.strip()]
    if not data:
        raise ValueError("空的 graph6 输入")
    n = data[0]
    if n > 62:                                   # 本课程规模用不到大端扩展
        raise ValueError(f"暂不支持 n={n} 的 graph6（>62）")
    nbits = n * (n - 1) // 2
    bits = []
    for byte in data[1:]:
        for k in range(5, -1, -1):
            bits.append((byte >> k) & 1)
    bits = bits[:nbits]
    red = [0] * n
    idx = 0
    for j in range(1, n):
        for i in range(j):
            if bits[idx]:
                red[i] |= 1 << j
                red[j] |= 1 << i
            idx += 1
    return n, red


def to_graph6(n: int, red: list[int]) -> str:
    """导出 graph6（n <= 62）。"""
    if n > 62:
        raise ValueError(f"暂不支持 n={n} 的 graph6（>62）")
    bits = []
    for j in range(1, n):
        for i in range(j):
            bits.append(1 if red[i] >> j & 1 else 0)
    while len(bits) % 6:
        bits.append(0)
    chars = [chr(n + 63)]
    for k in range(0, len(bits), 6):
        v = 0
        for b in bits[k:k + 6]:
            v = (v << 1) | b
        chars.append(chr(v + 63))
    return "".join(chars)
