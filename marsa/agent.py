"""智能体主循环：规划 -> 搜索 -> 验证 -> 记忆 -> 记录。

四个模块的接线方式：

    Planner 决定本 episode 用什么算子/多少步/怎么用记忆
       |
    Memory  按策略取回历史 elite，扰动后作为热启动初始解
       |
    Search  执行局部搜索（代价增量维护）
       |
    Verifier 独立复核；只有它有权宣布成功
       |
    Logger  每个 episode 与每个采样步都写入 JSONL，供出图与复现

记录里刻意保留 init_cost 与 improved_over_init：热启动天然占便宜（起点就好），
真正有意义的问题是"它是否还能在起点之上继续改进"，所以必须把两者都记下来。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bitset import Coloring
from .memory import (
    MemoryEntry, MemoryStore, obstruction_signature, warm_start_red,
)
from .planner import LLMPlanner, Plan, PlanContext, ScriptedPlanner
from .search import SAConfig, TabuConfig, run_operator
from .verifier import to_graph6, verify


@dataclass
class AgentConfig:
    n: int
    s: int = 5
    t: int = 5
    episodes: int = 10
    seed: int = 0
    memory_path: str = "runs/memory.jsonl"
    log_path: str = "runs/agent.jsonl"
    planner: str = "scripted"            # "scripted" | "llm"
    llm_complete: object = None          # (prompt)->str，供 LLMPlanner 注入
    memory_mode_override: str | None = None   # 消融用：强制固定记忆策略
    operator_override: str | None = None      # 消融用：强制固定算子
    steps_override: int | None = None         # 消融用：强制固定步数
    seconds_override: float = 0.0             # >0 时按墙钟时间预算（公平比较算子）
    strategy_path: str | None = None          # 策略记忆持久化路径
    retrieve_k: int = 3
    perturb_strength: int = 40
    report_every: int = 5000
    keep_elites: int = 4
    max_seconds: float = 0.0             # >0 时超时即停止


@dataclass
class AgentResult:
    n: int
    s: int
    t: int
    best_cost: int
    best_red: list[int]
    solved: bool
    solved_verified: bool
    episodes: list[dict] = field(default_factory=list)
    graph6: str = ""

    def summary(self) -> dict:
        return {
            "n": self.n, "s": self.s, "t": self.t,
            "best_cost": self.best_cost,
            "solved": self.solved,
            "solved_verified": self.solved_verified,
            "n_episodes": len(self.episodes),
            "best_episode": min(
                (e["episode"] for e in self.episodes
                 if e["best_cost"] == self.best_cost), default=None),
        }


def build_planner(cfg: AgentConfig):
    if cfg.planner == "llm":
        return LLMPlanner(complete=cfg.llm_complete, fallback=ScriptedPlanner())
    if cfg.planner == "adaptive":
        from .planner import AdaptivePlanner
        return AdaptivePlanner(seconds=cfg.seconds_override or 1.5,
                               memory_path=cfg.strategy_path,
                               seed=cfg.seed)
    return ScriptedPlanner()


def run_agent(cfg: AgentConfig) -> AgentResult:
    rng = random.Random(cfg.seed)
    task = f"{cfg.s},{cfg.t},{cfg.n}"
    planner = build_planner(cfg)

    log_path = Path(cfg.log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = log_path.open("w", encoding="utf-8")

    memory = MemoryStore(cfg.memory_path)
    # 每次运行都从干净的记忆开始，避免不同实验互相污染
    if Path(cfg.memory_path).exists():
        Path(cfg.memory_path).unlink()
    memory.entries = []

    global_best = None
    global_best_red: list[int] = []
    current = [0] * cfg.n
    episodes: list[dict] = []
    solved = False
    solved_verified = False
    t_start = time.perf_counter()

    for ep in range(cfg.episodes):
        ctx = PlanContext(
            n=cfg.n, s=cfg.s, t=cfg.t, episode=ep,
            best_cost=global_best if global_best is not None else -1,
            history=episodes, memory_size=len(memory.entries),
        )
        plan: Plan = planner.plan(ctx)

        # 消融实验：强制固定记忆策略 / 算子 / 步数
        if cfg.memory_mode_override is not None:
            plan.memory_mode = cfg.memory_mode_override
            plan.retrieve_k = cfg.retrieve_k
        if cfg.operator_override is not None:
            plan.operator = cfg.operator_override
        if cfg.steps_override is not None:
            plan.steps = cfg.steps_override

        # 时间预算：让不同算子在同一墙钟预算下比较（否则无可比性）。
        # 未显式给定步数上限时，把步数上限放到极大，使时间成为唯一的截止条件。
        if cfg.seconds_override and cfg.steps_override is None:
            plan.steps = 10 ** 9

        # ---- 记忆取回 + 热启动 ----
        init_red = None
        mem_diag: dict = {"mode": plan.memory_mode, "retrieved": 0}
        if plan.memory_mode != "none" and memory.entries:
            init_red, mem_diag = warm_start_red(
                cfg.n, task, memory, plan.memory_mode, current,
                plan.retrieve_k, plan.perturb_strength, rng)

        init_cost = None
        if init_red is not None:
            init_cost = Coloring(cfg.n, cfg.s, cfg.t, init_red).cost()

        # ---- 搜索 ----
        seed_ep = cfg.seed * 1000 + ep
        if plan.operator == "tabu":
            scfg = TabuConfig(n=cfg.n, s=cfg.s, t=cfg.t, steps=plan.steps,
                              seed=seed_ep, init_red=init_red,
                              report_every=cfg.report_every,
                              keep_elites=cfg.keep_elites,
                              max_seconds=cfg.seconds_override)
        else:
            scfg = SAConfig(n=cfg.n, s=cfg.s, t=cfg.t, steps=plan.steps,
                            seed=seed_ep, init_red=init_red,
                            report_every=cfg.report_every,
                            keep_elites=cfg.keep_elites,
                            max_seconds=cfg.seconds_override)

        t0 = time.perf_counter()
        res = run_operator(plan.operator, scfg)
        dt = time.perf_counter() - t0

        # ---- 独立验证（只有这里能宣布成功）----
        if res.best_cost == 0:
            good, witness = verify(cfg.n, res.best_red, cfg.s, cfg.t)
            if good:
                solved = True
                solved_verified = True
            else:
                log_f.write(json.dumps({
                    "type": "verification_failure", "episode": ep,
                    "witness": list(witness) if witness else None,
                }, ensure_ascii=False) + "\n")

        improved_over_init = res.best_cost < res.init_cost

        if global_best is None or res.best_cost < global_best:
            global_best = res.best_cost
            global_best_red = res.best_red
        current = res.best_red

        # ---- 把结果反馈给规划器（策略记忆就是在这一步积累经验的）----
        observe = getattr(planner, "observe", None)
        if callable(observe):
            observe(n=cfg.n, s=cfg.s, t=cfg.t, operator=plan.operator,
                    seconds=dt, steps=res.steps_done,
                    init_cost=res.init_cost, best_cost=res.best_cost)

        # ---- 写入记忆 ----
        sig = obstruction_signature(cfg.n, res.best_red, cfg.s, cfg.t)
        sig.pop("red_deg_seq", None)
        memory.add(MemoryEntry(
            task=task, episode=ep, operator=plan.operator,
            cost=res.best_cost, red=res.best_red,
            steps=res.steps_done, seconds=dt,
            signature={"plan": plan.to_dict(), **sig},
        ))

        rec = {
            "type": "episode",
            "episode": ep,
            "task": task,
            "n": cfg.n, "s": cfg.s, "t": cfg.t,
            "operator": plan.operator,
            "planned_steps": plan.steps,
            "steps_done": res.steps_done,
            "seconds": round(dt, 4),
            "cost": res.best_cost,
            "best_cost": res.best_cost,
            "global_best_cost": global_best,
            "memory_mode": plan.memory_mode,
            "retrieved": mem_diag.get("retrieved", 0),
            "warm_started": init_red is not None,
            "init_cost": res.init_cost,
            "warm_init_cost": init_cost,
            "improved_over_init": improved_over_init,
            "rationale": plan.rationale,
        }
        episodes.append(rec)
        log_f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # 采样步轨迹（供收敛曲线使用）
        for st in res.trace:
            st = dict(st)
            st["type"] = "step"
            st["episode"] = ep
            st["operator"] = plan.operator
            st["memory_mode"] = plan.memory_mode
            log_f.write(json.dumps(st, ensure_ascii=False) + "\n")

        if solved:
            break
        if cfg.max_seconds and (time.perf_counter() - t_start) > cfg.max_seconds:
            log_f.write(json.dumps({
                "type": "timeout", "episode": ep,
                "elapsed": round(time.perf_counter() - t_start, 2),
            }, ensure_ascii=False) + "\n")
            break

    log_f.write(json.dumps({
        "type": "final",
        "best_cost": global_best,
        "solved": solved,
        "solved_verified": solved_verified,
        "n_episodes": len(episodes),
        "elapsed": round(time.perf_counter() - t_start, 3),
        "planner_stats": getattr(planner, "stats", None),
    }, ensure_ascii=False) + "\n")
    log_f.close()

    g6 = to_graph6(cfg.n, global_best_red) if cfg.n <= 62 else ""
    return AgentResult(n=cfg.n, s=cfg.s, t=cfg.t, best_cost=global_best,
                       best_red=global_best_red, solved=solved,
                       solved_verified=solved_verified,
                       episodes=episodes, graph6=g6)
