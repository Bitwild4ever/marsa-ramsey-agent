"""对称 / 代数构造族搜索（阶段 2 的开端）。

动机
----
已知最好的 Ramsey 构造**高度对称**（循环图 / Cayley 图型）。通用局部搜索在
2^C(n,2) 的**通用图**空间里游走，而好解是"高对称的针尖"——这正解释了为什么
独立重启比记忆式爬坡更有效（阶段 1 已量到）。

与其在巨大的空间里碰运气，不如把空间缩到**历史上真正出成果的那一类**：

    循环图（circulant）：在 Z_n 上取连接集 S ⊆ Z_n\\{0}，且 S = -S。
    红边 = 差在 S 中的顶点对；蓝边 = 其余。

自由参数从 C(n,2) 降到 floor(n/2)：

    n=43：903 条边  ->  21 个比特（2^21 = 2,097,152 种）
    n=46：1035 条边 ->  23 个比特（2^23 = 8,388,608 种）

这个规模**小到可以穷举**，意味着可以做出一份"完全刻画"而不是"尽力而为"的结果。

重要性质（决定这个方向的野心）
------------------------------
* R(5,5) ≤ 46 已被证明 ⇒ **n=46 上不可能存在合法染色**。在 n=46 上穷举循环图
  应当得到"无解"，这正好可以当作对本项目代码与验证器的**独立交叉检查**。
* 若能在 **n=45** 上找到一份合法 (5,5)-染色，则 R(5,5) > 45，结合上界 46
  即得 **R(5,5) = 46**——问题就此解决。这是本项目唯一一个"逻辑上真能终结
  问题"的具体目标。
"""

from __future__ import annotations

from .bitset import Coloring
from .verifier import verify


def free_offsets(n: int) -> list[int]:
    """自由参数：偏移 d = 1..floor(n/2)（d 与 n-d 给出同一组边）。"""
    return list(range(1, n // 2 + 1))


def conn_from_bits(n: int, bits: int) -> set[int]:
    """把自由比特展开成连接集 S（自动补齐负方向）。"""
    conn: set[int] = set()
    for k, d in enumerate(free_offsets(n)):
        if bits >> k & 1:
            conn.add(d)
            conn.add((n - d) % n)
    conn.discard(0)
    return conn


def circulant_red(n: int, bits: int) -> list[int]:
    """构造循环图的红邻接位掩码表。"""
    conn = conn_from_bits(n, bits)
    red = [0] * n
    for i in range(n):
        row = 0
        for d in conn:
            row |= 1 << ((i + d) % n)
        red[i] = row
    return red


def circulant_size(n: int) -> int:
    """自由比特数。"""
    return len(free_offsets(n))


def cost_of_bits(n: int, s: int, t: int, bits: int) -> int:
    """给定自由比特的违反度（0 = 合法染色）。"""
    return Coloring(n, s, t, circulant_red(n, bits)).cost()


def verify_bits(n: int, s: int, t: int, bits: int):
    """用**独立验证器**复核循环图染色。"""
    return verify(n, circulant_red(n, bits), s, t)


def subset_masks(n: int, k: int) -> list[int]:
    """枚举**含顶点 0** 的 k-子集，返回每个子集"所需自由偏移"的位掩码。

    关键性质（这让判定变成几次位运算）
    ---------------------------------
    循环图具有平移对称性，所以一个 k-子集能否成为单色团，只需检查
    "含 0 的那些 k-子集"即可（其余都是平移像）。

    对含 0 的 k-子集 {0} ∪ {a1..a_{k-1}}，它的全部两点差都落在 1..n-1，
    每个差 d 对应自由偏移 min(d, n-d)。把这些自由偏移的比特收集成掩码 M，则

        该子集是**红**团  <=>  (S & M) == M
        该子集是**蓝**团  <=>  (S & M) == 0

    于是"这份循环图染色是否合法"可以在 O(子集数) 次位运算内判定，
    而且一旦发现违反立刻可以退出 —— 这使得**穷举**整个循环图族成为可能。
    """
    from itertools import combinations

    offsets = free_offsets(n)
    index = {d: j for j, d in enumerate(offsets)}
    masks: list[int] = []
    for rest in combinations(range(1, n), k - 1):
        verts = (0,) + rest
        m = 0
        ok = True
        for a in range(k):
            for b in range(a + 1, k):
                diff = (verts[b] - verts[a]) % n
                if diff == 0:
                    ok = False
                    break
                d = diff if diff <= n - diff else n - diff
                j = index.get(d)
                if j is None:
                    ok = False
                    break
                m |= 1 << j
            if not ok:
                break
        if ok:
            masks.append(m)
    return masks


class FastChecker:
    """把循环图的一份候选染色（自由比特 S）快速判为合法 / 不合法。

    判定规则：对每个含 0 的 s-子集掩码 M，"S & M == M" 表示存在红色 K_s；
    对每个含 0 的 t-子集掩码 M，"S & M == 0" 表示存在蓝色 K_t。
    两者任一成立即不合法。

    三处关键优化（实测把速度从 455 次/秒提到约 8 千次/秒）：
      1. **去重**：C(n-1,4) 个子集只有约 1/10 的掩码互不相同
         （n=43：111,930 -> 10,437）；
      2. **按掩码大小升序**：小掩码被命中的概率更高，早退能提前很多；
      3. **红蓝合并成一趟循环**：s == t 时两份掩码完全相同，一次遍历判两件事。
    """

    __slots__ = ("n", "s", "t", "m_red", "m_blue", "k", "_both")

    def __init__(self, n: int, s: int = 5, t: int = 5):
        self.n, self.s, self.t = n, s, t
        self.k = circulant_size(n)
        red = set(subset_masks(n, s)) if s >= 2 else set()
        blue = set(subset_masks(n, t)) if t >= 2 else set()

        def ordered(ms):
            return sorted(ms, key=lambda m: (m.bit_count(), m))

        if red and red == blue:
            self._both = ordered(red)
            self.m_red = self.m_blue = None
        else:
            self._both = None
            self.m_red = ordered(red)
            self.m_blue = ordered(blue)

    def is_valid(self, bits: int) -> bool:
        S = bits
        if self._both is not None:
            for M in self._both:
                v = S & M
                if v == M or v == 0:
                    return False
            return True
        for M in self.m_red:
            if (S & M) == M:
                return False
        for M in self.m_blue:
            if (S & M) == 0:
                return False
        return True

    def find_witness(self, bits: int):
        """返回一个反例掩码与颜色，便于排查；合法则返回 None。"""
        S = bits
        if self._both is not None:
            for M in self._both:
                v = S & M
                if v == M:
                    return ("red", M)
                if v == 0:
                    return ("blue", M)
            return None
        for M in self.m_red:
            if (S & M) == M:
                return ("red", M)
        for M in self.m_blue:
            if (S & M) == 0:
                return ("blue", M)
        return None


def enumerate_circulant(n: int, s: int = 5, t: int = 5,
                        start: int = 0, stop: int | None = None,
                        progress_every: int = 0) -> dict:
    """穷举 [start, stop) 区间内的全部自由比特，找**所有**合法染色。

    这是判定性的：跑完整个区间就能断言"该子族内存在/不存在合法染色"。
    """
    import time

    checker = FastChecker(n, s, t)
    total = 1 << circulant_size(n)
    hi = total if stop is None else min(stop, total)
    t0 = time.perf_counter()
    found: list[int] = []
    for bits in range(start, hi):
        if checker.is_valid(bits):
            found.append(bits)
        if progress_every and (bits - start) % progress_every == 0 and bits > start:
            done = bits - start
            rate = done / (time.perf_counter() - t0)
            eta = (hi - bits) / rate if rate else 0
            print(f"    {done:,}/{hi - start:,}  {rate:,.0f}/s  "
                  f"已找到 {len(found)}  预计剩余 {eta:.0f}s", flush=True)
    dt = time.perf_counter() - t0
    return {
        "n": n, "s": s, "t": t, "start": start, "stop": hi,
        "checked": hi - start, "found": found, "n_found": len(found),
        "seconds": round(dt, 3),
        "rate": round((hi - start) / dt, 1) if dt else None,
    }


def search_circulant(n: int, s: int = 5, t: int = 5, seconds: float = 30.0,
                     seed: int = 0, t0: float = 1.5, t1: float = 0.02,
                     verbose: bool = False) -> dict:
    """在循环图族的自由比特上做退火（每次评估全量重算代价）。

    单次评估约 O(n^2) 次位运算，n=43 时约 4.4ms（≈230 次/秒）。
    对 21 个比特的空间来说这个评估速率是可用的。
    """
    import math
    import random
    import time

    rng = random.Random(seed)
    k = circulant_size(n)
    cur = rng.getrandbits(k)
    cur_cost = cost_of_bits(n, s, t, cur)
    best, best_cost = cur, cur_cost
    t_start = time.perf_counter()
    evals = 0
    decay = (t1 / t0) ** (1.0 / 20000)
    temp = t0
    stall = 0
    while True:
        if time.perf_counter() - t_start > seconds:
            break
        bit = 1 << rng.randrange(k)
        cand = cur ^ bit
        c = cost_of_bits(n, s, t, cand)
        evals += 1
        delta = c - cur_cost
        if delta <= 0 or rng.random() < math.exp(-delta / max(1e-9, temp)):
            cur, cur_cost = cand, c
            if c < best_cost:
                best, best_cost = cand, c
                stall = 0
                if verbose:
                    print(f"    evals={evals} 代价={c}")
                if c == 0:
                    break
            else:
                stall += 1
        else:
            stall += 1
        temp *= decay
        if temp < t1:
            temp = t0                     # 重升温，保持 anytime 性质
        if stall > 3000 and evals % 97 == 0:
            cur = rng.getrandbits(k)      # 长期无改进则重新开始
            cur_cost = cost_of_bits(n, s, t, cur)
            temp = t0
            stall = 0
    return {
        "n": n, "s": s, "t": t, "bits": best, "cost": best_cost,
        "evals": evals, "seconds": round(time.perf_counter() - t_start, 2),
        "solved": best_cost == 0,
    }
