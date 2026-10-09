"""算子库：把"搜索策略"抽象成可注册、可对比、可组合的一等对象。

为什么需要这一层
----------------
之前的结论"策略记忆只能追平最优固定算子"有一个**退化的前提**：只有 3 个算子，
且其中一个在所有实例与预算上都占优。在那种情况下，多臂老虎机**在数学上不可能**
超过事后最优的那一臂 —— 我们测到的不是"记忆无效"，而是"只有一个赢家时选择没有价值"。

要真正检验记忆，必须给它一个**大而异质**的算子空间：每个算子在某些
(实例规模, 时间预算) 区间里是赢家，而没有任何一个在所有区间都占优。

异构性的来源（这些维度会产生真实的取舍）
----------------------------------------
1. 候选表：候选越大 -> 单步质量越高但步频越低（预算越短，小候选越有利）
2. 禁忌长度：短 -> 多样化；长 -> 强化
3. 卡住扰动：关闭 -> 纯局部搜索；开启 -> 能跳出盆地（长预算/多峰时有利）
4. 退火时间表：升温/降温快慢，决定探索与利用的分配
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .search import SAConfig, TabuConfig, run_sa, run_tabu


@dataclass(frozen=True)
class Policy:
    """一个完整的搜索策略（自包含，可直接跑）。"""

    name: str
    kind: str                       # "sa" | "tabu"
    kwargs: tuple = ()              # 冻结的配置项，便于 hash / 打印
    desc: str = ""
    tags: tuple = ()

    def build(self, n: int, s: int, t: int, budget: float, seed: int,
              init_red: list[int] | None = None):
        base = dict(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                    seed=seed, report_every=0, keep_elites=0)
        if init_red is not None:
            base["init_red"] = init_red
        extra = dict(self.kwargs)
        if self.kind == "sa":
            return SAConfig(**base, **extra)
        return TabuConfig(**base, **extra)


def run_policy(p: Policy, n: int, s: int, t: int, budget: float, seed: int,
               init_red: list[int] | None = None):
    """按策略跑一次搜索。注意：调用方必须自己用验证器复核结果。"""
    cfg = p.build(n, s, t, budget, seed, init_red)
    return run_sa(cfg) if p.kind == "sa" else run_tabu(cfg)


# --------------------------------------------------------------------------
# 默认算子组合
# --------------------------------------------------------------------------

def _tabu(name, desc, tags=(), **kw):
    return Policy(name=name, kind="tabu", kwargs=tuple(sorted(kw.items())),
                  desc=desc, tags=tuple(tags))


def _sa(name, desc, tags=(), **kw):
    return Policy(name=name, kind="sa", kwargs=tuple(sorted(kw.items())),
                  desc=desc, tags=tuple(tags))


def default_portfolio() -> list[Policy]:
    """构造一个覆盖各取舍维度的异构算子组合（≥ 20 个）。"""
    ps: list[Policy] = []

    # ---- 1. 候选表维度：候选越大单步越准、步频越低 ----
    ps.append(_tabu("tabu_full", "禁忌/评估全部边（最强单步，最慢）",
                    ["cand"], candidate_mode="full"))
    ps.append(_tabu("tabu_sample32", "禁忌/随机抽 32 条（步频最高）",
                    ["cand", "fast"], candidate_mode="sample", candidate_size=32))
    ps.append(_tabu("tabu_sample128", "禁忌/随机抽 128 条",
                    ["cand"], candidate_mode="sample", candidate_size=128))
    ps.append(_tabu("tabu_focus64", "禁忌/活跃区 64 条",
                    ["cand", "fast"], candidate_mode="focus", candidate_size=64))
    ps.append(_tabu("tabu_focus128", "禁忌/活跃区 128 条",
                    ["cand"], candidate_mode="focus", candidate_size=128))
    ps.append(_tabu("tabu_viol128", "禁忌/违反团边 128 条",
                    ["cand", "vlns"], candidate_mode="violation",
                    candidate_size=128))
    ps.append(_tabu("tabu_viol256", "禁忌/违反团边 256 条（当前最佳）",
                    ["cand", "vlns"], candidate_mode="violation",
                    candidate_size=256))
    ps.append(_tabu("tabu_viol512", "禁忌/违反团边 512 条（单步最准）",
                    ["cand", "vlns"], candidate_mode="violation",
                    candidate_size=512))

    # ---- 2. 禁忌长度维度：短=多样化，长=强化 ----
    for tb, tr, tag in ((3, 3, "短"), (20, 20, "长")):
        ps.append(_tabu(f"tabu_viol256_ten{tb}", f"违反团256 + 禁忌长度{tag}",
                        ["tenure"], candidate_mode="violation",
                        candidate_size=256, tenure_base=tb, tenure_rand=tr))
    ps.append(_tabu("tabu_full_ten20", "全量候选 + 长禁忌",
                    ["tenure"], candidate_mode="full",
                    tenure_base=20, tenure_rand=20))

    # ---- 3. 卡住扰动维度：能否跳出盆地 ----
    ps.append(_tabu("tabu_viol256_stall300v2",
                    "违反团256 + 每300步扰动2条（违反团内）",
                    ["stall"], candidate_mode="violation", candidate_size=256,
                    stall_limit=300, perturb_edges=2, perturb_mode="violation"))
    ps.append(_tabu("tabu_viol256_stall80v2",
                    "违反团256 + 每80步扰动2条（触发更频繁）",
                    ["stall"], candidate_mode="violation", candidate_size=256,
                    stall_limit=80, perturb_edges=2, perturb_mode="violation"))
    ps.append(_tabu("tabu_viol256_stall300v5",
                    "违反团256 + 每300步扰动5条（扰动更强）",
                    ["stall"], candidate_mode="violation", candidate_size=256,
                    stall_limit=300, perturb_edges=5, perturb_mode="violation"))
    ps.append(_tabu("tabu_viol256_stall300r2",
                    "违反团256 + 每300步随机扰动2条（对照：非定向）",
                    ["stall"], candidate_mode="violation", candidate_size=256,
                    stall_limit=300, perturb_edges=2, perturb_mode="random"))
    ps.append(_tabu("tabu_focus128_stall300v2",
                    "活跃区128 + 每300步扰动2条",
                    ["stall", "cand"], candidate_mode="focus",
                    candidate_size=128, stall_limit=300, perturb_edges=2))
    ps.append(_tabu("tabu_sample32_stall80v2",
                    "随机32 + 高频扰动（步频最高的扰动型）",
                    ["stall", "fast"], candidate_mode="sample",
                    candidate_size=32, stall_limit=80, perturb_edges=2))

    # ---- 4. 候选表刷新频率（VLNS 专属超参）----
    ps.append(_tabu("tabu_viol256_ref10", "违反团256 + 每10步重算候选",
                    ["vlns", "fast"], candidate_mode="violation",
                    candidate_size=256, candidate_refresh=10))
    ps.append(_tabu("tabu_viol256_ref200", "违反团256 + 每200步重算候选",
                    ["vlns"], candidate_mode="violation",
                    candidate_size=256, candidate_refresh=200))

    # ---- 5. 退火维度：时间表快慢 + 是否重升温 ----
    ps.append(_sa("sa_default", "退火/默认时间表", ["sa"]))
    ps.append(_sa("sa_cold", "退火/终温更低（更偏利用）", ["sa"],
                  t1_ratio=0.001))
    ps.append(_sa("sa_hot", "退火/终温更高（更偏探索）", ["sa"], t1_ratio=0.1))
    ps.append(_sa("sa_sched30k", "退火/短时间表（30k 步一次循环）", ["sa"],
                  schedule_steps=30_000))
    ps.append(_sa("sa_sched500k", "退火/长时间表（500k 步一次循环）", ["sa"],
                  schedule_steps=500_000))
    ps.append(_sa("sa_noreheat", "退火/不重升温（单次降温到底）", ["sa"],
                  reheat=False, schedule_steps=200_000))

    return ps


def portfolio_by_name() -> dict[str, Policy]:
    return {p.name: p for p in default_portfolio()}
