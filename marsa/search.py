"""执行器：在邻接矩阵上做模拟退火 / 重启局部搜索。

执行器只负责"搜索"，**没有任何权力宣布成功**——成功与否一律交由
verifier 复核。

设计要点：
  * 代价维护完全增量：每次翻转 O(n) 次位运算（见 bitset 模块注释）。
  * 温度自动标定：先采样若干次随机翻转的 |Δ|，据此设定 T0，避免手调。
  * 记录 elite（每次刷新最优时保存的染色），供长期记忆模块沉淀与检索。
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field, replace

from .bitset import Coloring


@dataclass
class SAConfig:
    n: int
    s: int = 5
    t: int = 5
    steps: int = 100_000
    seed: int = 0
    t0: float | None = None          # None 时自动标定
    t1_ratio: float = 0.01           # 终止温度 = t1_ratio * T0
    init_red: list[int] | None = None
    init_p: float = 0.5              # 随机初始染色的红边概率
    report_every: int = 2000
    target_cost: int = 0
    restart_on_stall: int = 0        # >0 时无改进这么多步就重启
    restarts: int = 1
    keep_elites: int = 5
    max_seconds: float = 0.0         # >0 时按墙钟时间截止（公平比较算子所必需）
    # 退火时间表的**名义长度**。必须与 steps 解耦：按时间预算运行时 steps 是
    # 一个极大的上限，若直接用它算衰减率 (t1/t0)^(1/steps) ≈ 1，温度几乎不降，
    # 退火就退化成随机游走。默认取 min(steps, 150000)。
    schedule_steps: int = 0
    reheat: bool = True              # 每个时间表结束后重新升温（anytime 行为）

    def __post_init__(self):
        if self.t0 is None:
            self.t0 = -1.0           # 标记为待标定


@dataclass
class SAResult:
    n: int
    s: int
    t: int
    best_cost: int
    best_red: list[int]
    steps_done: int
    restarts_done: int
    t0: float
    init_cost: int = 0
    trace: list[dict] = field(default_factory=list)
    elites: list[tuple[int, list[int]]] = field(default_factory=list)

    @property
    def solved(self) -> bool:
        return self.best_cost == 0


def calibrate_t0(n: int, s: int, t: int, rng: random.Random,
                 samples: int = 300, pct: float = 0.7) -> float:
    """采样随机翻转的 |Δ|，用其分位数作为起始温度 —— 避免手调超参。"""
    c = Coloring.random(n, s, t, rng)
    pairs = c.edges()
    deltas = []
    for _ in range(samples):
        i, j = pairs[rng.randrange(len(pairs))]
        deltas.append(abs(c.apply_flip(i, j)))
    deltas.sort()
    if not deltas:
        return 1.0
    val = deltas[min(len(deltas) - 1, int(pct * len(deltas)))]
    return max(0.5, float(val))


def run_sa(cfg: SAConfig, rng: random.Random | None = None) -> SAResult:
    """跑一次模拟退火，返回最优染色、代价轨迹与 elite 集合。"""
    rng = rng or random.Random(cfg.seed)
    n, s, t = cfg.n, cfg.s, cfg.t

    t0 = calibrate_t0(n, s, t, rng) if cfg.t0 is None or cfg.t0 < 0 else cfg.t0
    t1 = max(1e-6, t0 * cfg.t1_ratio)
    sched = max(1, cfg.schedule_steps or min(cfg.steps, 150_000))

    trace: list[dict] = []
    elites: list[tuple[int, list[int]]] = []
    best_cost = None
    best_red: list[int] = []
    total_steps = 0
    restarts_done = 1
    global_best_cost = None
    global_best_red: list[int] = []
    first_init_cost = 0
    edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
    t_start = time.perf_counter()
    timed_out = False

    for r_idx in range(cfg.restarts):
        if r_idx == 0 and cfg.init_red is not None:
            cur = Coloring(n, s, t, cfg.init_red)
        else:
            cur = Coloring.random(n, s, t, rng, p=cfg.init_p)
        cost = cur.cost()
        best_cost, best_red = cost, cur.red_list()
        if r_idx == 0:
            first_init_cost = cost
        if global_best_cost is None or cost < global_best_cost:
            global_best_cost, global_best_red = cost, cur.red_list()

        decay = (t1 / t0) ** (1.0 / sched)
        temp = t0
        local = 0
        since_improve = 0
        accepted = 0
        accepted_bad = 0

        for step in range(1, cfg.steps + 1):
            if cfg.reheat and local >= sched:      # 重新升温，保持 anytime 性质
                temp = t0
                local = 0
            local += 1
            i, j = edges[rng.randrange(len(edges))]
            delta = cur.apply_flip(i, j)
            if delta <= 0 or rng.random() < math.exp(-delta / temp):
                if delta > 0:
                    accepted_bad += 1
                accepted += 1
                cost = cur.cost()
                if cost < best_cost:
                    best_cost = cost
                    best_red = cur.red_list()
                    since_improve = 0
                    if cfg.keep_elites:
                        elites.append((cost, best_red))
                        if len(elites) > cfg.keep_elites * 4:
                            elites.sort(key=lambda e: e[0])
                            elites = elites[:cfg.keep_elites]
                    if cost < global_best_cost:
                        global_best_cost = cost
                        global_best_red = cur.red_list()
                else:
                    since_improve += 1
            else:
                cur.apply_flip(i, j)         # 撤销
                since_improve += 1

            temp *= decay
            total_steps += 1

            if cfg.report_every and step % cfg.report_every == 0:
                trace.append({
                    "restart": r_idx,
                    "step_in_restart": step,
                    "global_step": total_steps,
                    "cost": cost,
                    "best_cost": best_cost,
                    "global_best_cost": global_best_cost,
                    "temp": round(temp, 6),
                    "accept_rate": round(accepted / step, 4),
                    "accept_bad_rate": round(accepted_bad / step, 4),
                })

            if best_cost <= cfg.target_cost:
                break
            if cfg.restart_on_stall and since_improve >= cfg.restart_on_stall:
                break
            if (cfg.max_seconds and step % 512 == 0
                    and time.perf_counter() - t_start > cfg.max_seconds):
                timed_out = True
                break

        if best_cost <= cfg.target_cost:
            break
        if timed_out:
            break
        if r_idx + 1 < cfg.restarts:
            restarts_done += 1

    # 最终 elite 集合：按代价升序，去重
    seen = set()
    uniq: list[tuple[int, list[int]]] = []
    for cost, red in sorted(elites, key=lambda e: e[0]):
        key = tuple(red)
        if key not in seen:
            seen.add(key)
            uniq.append((cost, red))
    uniq = uniq[:cfg.keep_elites]

    return SAResult(
        n=n, s=s, t=t,
        best_cost=global_best_cost, best_red=global_best_red,
        steps_done=total_steps, restarts_done=restarts_done,
        t0=t0, init_cost=first_init_cost, trace=trace, elites=uniq,
    )


# --------------------------------------------------------------------------
# 禁忌搜索（best-improvement）：在"针尖型"实例上比朴素退火强得多
# --------------------------------------------------------------------------

@dataclass
class TabuConfig:
    n: int
    s: int = 5
    t: int = 5
    steps: int = 20_000
    seed: int = 0
    init_red: list[int] | None = None
    init_p: float = 0.5
    target_cost: int = 0
    report_every: int = 200
    keep_elites: int = 5
    tenure_base: int = 8
    tenure_rand: int = 8
    restarts: int = 1
    max_seconds: float = 0.0         # >0 时按墙钟时间截止
    # ---- 候选表策略：把每步要评估的边数从 C(n,2) 降下来 ----
    #   "full"   评估全部边（最强单步，但 O(n^2)）
    #   "sample" 每步随机抽 candidate_size 条边
    #   "focus"  上一次移动的两个端点的关联边（活跃区）+ 随机补充
    #   "violation" 当前**违反团所涉及的边**（VLNS 式聚焦，每 refresh 步重算）
    candidate_mode: str = "full"
    candidate_size: int = 128
    candidate_refresh: int = 50


def run_tabu(cfg: TabuConfig, rng: random.Random | None = None) -> SAResult:
    """禁忌搜索：每步取"代价 + 频率惩罚"最优的非禁忌边翻转。

    禁忌表阻止刚刚翻过的边被立刻翻回；aspiration 准则允许突破历史最优的
    禁忌移动。频率惩罚用于在同分移动之间做多样化。
    """
    rng = rng or random.Random(cfg.seed)
    n, s, t = cfg.n, cfg.s, cfg.t
    edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
    # 关联表：[v] -> 所有含 v 的边。用于 O(n) 构造"活跃区"候选，
    # 否则每次都要扫描全部 O(n^2) 条边，候选表就失去意义了。
    incident: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for _e in edges:
        incident[_e[0]].append(_e)
        incident[_e[1]].append(_e)
    m_cand = min(cfg.candidate_size, len(edges))
    trace: list[dict] = []
    elites: list[tuple[int, list[int]]] = []
    total_steps = 0
    restarts_done = 0
    global_best: int | None = None
    global_best_red: list[int] = []
    first_init_cost = 0
    t_start = time.perf_counter()
    timed_out = False

    for r_idx in range(cfg.restarts):
        if r_idx == 0 and cfg.init_red is not None:
            cur = Coloring(n, s, t, cfg.init_red)
        else:
            cur = Coloring.random(n, s, t, rng, p=cfg.init_p)
        cost = cur.cost()
        best_cost, best_red = cost, cur.red_list()
        if r_idx == 0:
            first_init_cost = cost
        if global_best is None or best_cost < global_best:
            global_best, global_best_red = best_cost, best_red
        tabu: dict[tuple[int, int], int] = {}
        freq: dict[tuple[int, int], int] = {}
        since_improve = 0
        last_move: tuple[int, int] | None = None
        viol_pool: list[tuple[int, int]] | None = None

        for it in range(cfg.steps):
            # ---- 构造候选边集合 ----
            if cfg.candidate_mode == "full" or m_cand >= len(edges):
                cand = edges
            elif cfg.candidate_mode == "sample":
                cand = rng.sample(edges, m_cand)
            elif cfg.candidate_mode == "focus":
                if last_move is None:
                    cand = rng.sample(edges, m_cand)
                else:
                    u, v = last_move
                    local = incident[u] + incident[v]
                    extra = m_cand - len(local)
                    if extra > 0:
                        local = local + rng.sample(edges, min(extra, len(edges)))
                    cand = local
            elif cfg.candidate_mode == "violation":
                if viol_pool is None or it % max(1, cfg.candidate_refresh) == 0:
                    viol_pool = cur.violation_edges()
                if not viol_pool:
                    cand = rng.sample(edges, m_cand)
                elif len(viol_pool) > m_cand:
                    cand = rng.sample(viol_pool, m_cand)
                else:
                    extra = m_cand - len(viol_pool)
                    cand = viol_pool + (rng.sample(edges, min(extra, len(edges)))
                                        if extra > 0 else [])
            else:
                raise ValueError(f"未知候选表策略: {cfg.candidate_mode}")

            best_move = None
            best_score = None
            best_freq = None
            best_delta = 0
            for e in cand:
                delta = cur.delta_of_flip(e[0], e[1])
                score = cost + delta
                if tabu.get(e, -1) > it and score >= best_cost:
                    continue                      # 禁忌且无 aspiration
                f = freq.get(e, 0)
                if (best_score is None or score < best_score
                        or (score == best_score and f < best_freq)):
                    best_score, best_move, best_freq, best_delta = score, e, f, delta
            if best_move is None:                 # 全被禁忌：随机走一步
                best_move = edges[rng.randrange(len(edges))]
                best_delta = cur.delta_of_flip(best_move[0], best_move[1])

            cur.apply_flip(best_move[0], best_move[1])
            cost = cur.cost()
            last_move = best_move
            tabu[best_move] = it + cfg.tenure_base + rng.randint(0, cfg.tenure_rand)
            freq[best_move] = freq.get(best_move, 0) + 1
            total_steps += 1

            if cost < best_cost:
                best_cost, best_red = cost, cur.red_list()
                since_improve = 0
                if cfg.keep_elites:
                    elites.append((cost, best_red))
                    if len(elites) > cfg.keep_elites * 4:
                        elites.sort(key=lambda x: x[0])
                        elites = elites[:cfg.keep_elites]
                if cost < global_best:
                    global_best, global_best_red = cost, best_red
            else:
                since_improve += 1

            if cfg.report_every and (it + 1) % cfg.report_every == 0:
                trace.append({
                    "restart": r_idx,
                    "step_in_restart": it + 1,
                    "global_step": total_steps,
                    "cost": cost,
                    "best_cost": best_cost,
                    "global_best_cost": global_best,
                    "temp": 0.0,
                    "accept_rate": 1.0,
                    "accept_bad_rate": 0.0,
                    "stall": since_improve,
                })

            if global_best <= cfg.target_cost:
                break
            if cfg.max_seconds and time.perf_counter() - t_start > cfg.max_seconds:
                timed_out = True
                break
        restarts_done += 1
        if global_best <= cfg.target_cost:
            break
        if timed_out:
            break

    seen = set()
    uniq: list[tuple[int, list[int]]] = []
    for c, red in sorted(elites, key=lambda x: x[0]):
        k = tuple(red)
        if k not in seen:
            seen.add(k)
            uniq.append((c, red))

    return SAResult(
        n=n, s=s, t=t,
        best_cost=global_best, best_red=global_best_red,
        steps_done=total_steps, restarts_done=restarts_done,
        t0=0.0, init_cost=first_init_cost, trace=trace,
        elites=uniq[:cfg.keep_elites],
    )


# --------------------------------------------------------------------------
# 统一入口：规划器就是通过这个函数选择算子的
# --------------------------------------------------------------------------

OPERATORS = ("sa", "tabu", "tabu_focus", "tabu_sample", "tabu_violation")


def run_operator(op: str, cfg) -> SAResult:
    """统一入口：规划器就是通过这个函数选择算子的。

    新增的 tabu_focus / tabu_sample / tabu_violation 都是**候选表禁忌**：
    不评估全部 C(n,2) 条边，只评估一个候选子集，从而把每步成本降下来。
    实测 tabu_focus 在 n=43/46 上把最优代价压低约 16% / 20%
    （见 bench_candidates.py）。
    """
    if op == "sa":
        return run_sa(cfg)
    if op == "tabu":
        return run_tabu(cfg)
    if op in ("tabu_focus", "tabu_sample", "tabu_violation"):
        repl = replace(cfg, candidate_mode=op.split("_", 1)[1])
        return run_tabu(repl)
    raise ValueError(f"未知算子: {op}")
