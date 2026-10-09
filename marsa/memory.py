"""长期记忆模块 —— 本项目的创新点。

动机
----
局部搜索每次失败都会产生大量**近失解**（near-miss）以及它们"为什么失败"的
结构性信息。经典做法每次重启都从零开始，把这些信息全部丢弃。

本模块负责三件事：

  1. **存储**：把每个 episode 的最优解（elite）连同其结构签名写入记忆；
  2. **检索**：在需要重启时，从记忆里取回一组历史解来指导新一轮搜索；
  3. **复用**：对取回的解做扰动（perturbation）后作为新一轮的初始解。

检索策略是可对照的四档（这构成消融实验的四组）：

    none        冷启动，随机初始解            —— 基线
    random      随机取回 k 个历史 elite
    nearest     取回与当前最优最相似的 k 个    —— 贪心利用
    submodular  次模最大化取回 k 个            —— 兼顾相关性与多样性（本方法）

次模目标
--------
取回集合 S 的价值用**设施选址函数**（facility location）度量：

    F(S) = Σ_{i ∈ P} max_{j ∈ S} sim(i, j)

其中 P 是候选池，sim 是"边一致度"。F 是单调次模函数，贪心算法有
(1 − 1/e) 的近似保证。它同时奖励"覆盖候选池"和"内部多样"，因此不会
像 nearest 那样取回一堆几乎相同的解。
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

RETRIEVAL_MODES = ("none", "random", "nearest", "submodular")


# --------------------------------------------------------------------------
# 相似度
# --------------------------------------------------------------------------

def edge_distance(n: int, a: list[int], b: list[int]) -> int:
    """两个染色之间不同颜色的边数。O(n) 次位运算。"""
    d = 0
    for i in range(n):
        d += (a[i] ^ b[i]).bit_count()
    return d // 2


def similarity(n: int, a: list[int], b: list[int]) -> float:
    """边一致度 ∈ [0,1]。1 表示完全相同。"""
    total = n * (n - 1) // 2
    if total == 0:
        return 1.0
    return 1.0 - edge_distance(n, a, b) / total


# --------------------------------------------------------------------------
# 次模检索
# --------------------------------------------------------------------------

def facility_location_greedy(pool: list[list[int]], k: int, n: int) -> list[int]:
    """贪心最大化设施选址函数 F(S) = Σ_i max_{j∈S} sim(i,j)。

    返回被选中的 pool 下标（至多 k 个）。贪心有 (1−1/e) 近似保证。
    """
    m = len(pool)
    if m == 0 or k <= 0:
        return []
    k = min(k, m)
    # 预计算相似度矩阵（对称，只算上三角）
    sim = [[1.0] * m for _ in range(m)]
    for i in range(m):
        for j in range(i + 1, m):
            s = similarity(n, pool[i], pool[j])
            sim[i][j] = sim[j][i] = s

    best_val = [0.0] * m          # 每个候选点当前被覆盖的最佳相似度
    chosen: list[int] = []
    # 贪心地选第一个：选"最中心"的点（覆盖总量最大）
    totals = [sum(sim[i]) for i in range(m)]
    first = max(range(m), key=lambda i: totals[i])
    chosen.append(first)
    for i in range(m):
        best_val[i] = sim[i][first]

    while len(chosen) < k:
        best_gain, best_j = -1.0, None
        for j in range(m):
            if j in chosen:
                continue
            gain = 0.0
            for i in range(m):
                if sim[i][j] > best_val[i]:
                    gain += sim[i][j] - best_val[i]
            if gain > best_gain:
                best_gain, best_j = gain, j
        if best_j is None or best_gain <= 1e-12:
            break
        chosen.append(best_j)
        for i in range(m):
            if sim[i][best_j] > best_val[i]:
                best_val[i] = sim[i][best_j]
    return chosen


# --------------------------------------------------------------------------
# 记忆条目与存储
# --------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    task: str                     # 例如 "5,5,43"
    episode: int
    operator: str
    cost: int
    red: list[int]
    steps: int
    seconds: float
    signature: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "task": self.task, "episode": self.episode,
            "operator": self.operator, "cost": self.cost,
            "red": self.red, "steps": self.steps,
            "seconds": round(self.seconds, 4),
            "signature": self.signature,
        }, ensure_ascii=False)


def obstruction_signature(n: int, red: list[int], s: int, t: int) -> dict:
    """把一次失败压缩成轻量结构签名（供统计与规划器读取）。

    这里刻意选 O(n) 就能算出来的量：红/蓝度分布 + 度序列的离散程度。
    它们刻画"近失解长什么样"，而不需要枚举违反团（那在大 n 上太贵）。
    """
    red_deg = [red[i].bit_count() for i in range(n)]
    blue_deg = [n - 1 - d for d in red_deg]
    def stats(xs):
        mu = sum(xs) / len(xs)
        var = sum((x - mu) ** 2 for x in xs) / len(xs)
        return {"min": min(xs), "max": max(xs), "mean": round(mu, 3),
                "std": round(math.sqrt(var), 3)}
    return {
        "red_deg": stats(red_deg),
        "blue_deg": stats(blue_deg),
        "red_deg_seq": red_deg,
    }


class MemoryStore:
    """episode 级长期记忆，持久化为 JSONL。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: list[MemoryEntry] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, entry: MemoryEntry) -> None:
        self.entries.append(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

    def load(self) -> "MemoryStore":
        if self.path.exists():
            self.entries = []
            with self.path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    self.entries.append(MemoryEntry(**d))
        return self

    # ---------- 检索 ----------

    def pool(self, task: str, k_best: int | None = None) -> list[MemoryEntry]:
        """同一任务下的历史 elite，按代价升序（可只取最好的若干条）。"""
        ps = [e for e in self.entries if e.task == task]
        ps.sort(key=lambda e: e.cost)
        return ps[:k_best] if k_best else ps

    def retrieve(self, mode: str, task: str, n: int, current: list[int],
                 k: int, rng) -> list[list[int]]:
        """按指定策略取回 k 个历史解（返回邻接表列表，而不是条目）。"""
        if mode == "none":
            return []
        ps = self.pool(task)
        if not ps:
            return []
        cand = [e.red for e in ps]
        if mode == "random":
            if len(cand) <= k:
                return list(cand)
            return rng.sample(cand, k)
        if mode == "nearest":
            order = sorted(cand, key=lambda r: edge_distance(n, current, r))
            return order[:k]
        if mode == "submodular":
            idx = facility_location_greedy(cand, k, n)
            return [cand[i] for i in idx]
        raise ValueError(f"未知检索策略: {mode}")


# --------------------------------------------------------------------------
# 复用：对取回的解做扰动后作为新初始解
# --------------------------------------------------------------------------

def perturb(n: int, red: list[int], strength: int, rng) -> list[int]:
    """随机翻转 strength 条边，用于跳出取回解所在的局部最优盆地。"""
    out = list(red)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
    for _ in range(strength):
        i, j = edges[rng.randrange(len(edges))]
        out[i] ^= 1 << j
        out[j] ^= 1 << i
    return out


def warm_start_red(n: int, task: str, memory: MemoryStore, mode: str,
                   current: list[int], k: int, strength: int,
                   rng) -> tuple[list[int] | None, dict]:
    """按策略取回并扰动，得到新初始解。返回 (邻接表 或 None, 诊断信息)。"""
    picked = memory.retrieve(mode, task, n, current, k, rng)
    if not picked:
        return None, {"retrieved": 0, "mode": mode}
    src = picked[rng.randrange(len(picked))]
    init = perturb(n, src, strength, rng)
    return init, {"retrieved": len(picked), "mode": mode,
                  "strength": strength,
                  "src_cost": None}
