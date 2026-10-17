"""确定性计算动作 —— 供控制台、命令行与 DSH 子智能体共用。

把"一次实验"封装成纯函数：输入参数、返回结构化结果。三者共用同一实现，
避免控制台和命令行出现两套行为。

**全部动作都不调用任何大模型。**
"""

from __future__ import annotations

import time
from typing import Any, Dict

from .bitset import Coloring
from .search import SAConfig, TabuConfig, run_operator
from .symmetric import FastChecker, circulant_red, circulant_size
from .verifier import parse_graph6, to_graph6, verify

OPERATORS = ("sa", "tabu", "tabu_focus", "tabu_sample", "tabu_violation")

MAX_ENUMERATION_SPACE = 40_000_000


def _result(action: str, status: str, conclusion: str, **extra) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": status not in ("error",),
        "action": action,
        "status": status,
        "conclusion": conclusion,
    }
    out.update(extra)
    return out


def search(n: int, s: int = 5, t: int = 5, operator: str = "tabu_focus",
           budget: float = 5.0, seed: int = 0) -> Dict[str, Any]:
    """在固定墙钟预算下跑一次搜索。成功必须过独立验证器。"""
    n, s, t = int(n), int(s), int(t)
    op = str(operator)
    if op not in OPERATORS:
        return _result("search", "error", f"未知算子 {op}",
                       error=f"unknown operator {op!r}")
    budget = max(0.1, min(float(budget), 600.0))
    if op == "sa":
        cfg = SAConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                       seed=int(seed), report_every=0, keep_elites=0)
    else:
        cfg = TabuConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                         seed=int(seed), report_every=0, keep_elites=0)
    t0 = time.perf_counter()
    res = run_operator(op, cfg)
    dt = time.perf_counter() - t0

    extra = dict(n=n, s=s, t=t, operator=op, seed=int(seed),
                 budget_seconds=budget, seconds=round(dt, 2),
                 steps=int(res.steps_done),
                 init_violations=int(res.init_cost),
                 violations=int(res.best_cost), graph6=None, verified=None)
    if res.best_cost == 0:
        good, witness = verify(n, res.best_red, s, t)
        extra["verified"] = bool(good)
        extra["graph6"] = to_graph6(n, res.best_red) if n <= 62 else None
        extra["witness"] = list(witness) if witness else None
        if good:
            return _result("search", "solved",
                           f"已解出且经独立验证：R({s},{t}) > {n}。", **extra)
        return _result("search", "verification_failed",
                       "搜索自称成功，但独立验证器否决 —— 该结果不可信。", **extra)
    return _result(
        "search", "unsolved",
        f"该预算内未解出，当前违反度 {res.best_cost}。"
        f"这只是「努力不够」，不是「不存在」的证据。", **extra)


def enumerate_family(n: int, s: int = 5, t: int = 5,
                     family: str = "circulant") -> Dict[str, Any]:
    """穷举对称族，给出判定性结论（exists / none_exist）。"""
    n, s, t = int(n), int(s), int(t)
    fam = str(family).lower()
    if fam != "circulant":
        return _result("enumerate", "error", f"暂不支持的族：{fam}",
                       error=f"unsupported family {fam!r}")
    k = circulant_size(n)
    total = 1 << k
    if total > MAX_ENUMERATION_SPACE:
        return _result("enumerate", "error",
                       f"空间过大（2^{k} = {total:,}），不适合穷举",
                       error="space too large", free_parameters=k, space=total)
    checker = FastChecker(n, s, t)
    t0 = time.perf_counter()
    found = [b for b in range(total) if checker.is_valid(b)]
    dt = time.perf_counter() - t0

    extra = dict(n=n, s=s, t=t, family=fam, free_parameters=k, space=total,
                 solutions=len(found), seconds=round(dt, 2), exhaustive=True,
                 graph6=None, connection_set=None, verified=None)
    if found:
        bits = found[0]
        red = circulant_red(n, bits)
        good, _w = verify(n, red, s, t)
        extra["verified"] = bool(good)
        extra["graph6"] = to_graph6(n, red)
        extra["connection_set"] = sorted(
            d for d in range(1, n // 2 + 1) if bits >> (d - 1) & 1)
        extra["connection_set_bits"] = bits
        return _result(
            "enumerate", "exists",
            f"判定：循环图族在 n={n} 上有 {len(found)} 个合法 ({s},{t})-染色"
            f"（全空间 {total:,} 已查完）⇒ R({s},{t}) > {n}。", **extra)
    return _result(
        "enumerate", "none_exist",
        f"判定性否定：循环图族在 n={n} 上**无**合法 ({s},{t})-染色"
        f"（全空间 {total:,} 已查完）。这个族被排除，不是「没搜到」。", **extra)


def verify_construction(n: int, s: int = 5, t: int = 5,
                        graph6: str = "") -> Dict[str, Any]:
    """用独立实现精确判定一份构造是否合法。"""
    n, s, t = int(n), int(s), int(t)
    text = str(graph6 or "").strip()
    if not text:
        return _result("verify", "error", "graph6 为空", error="empty graph6")
    try:
        n2, red = parse_graph6(text)
    except Exception as exc:                                # noqa: BLE001
        return _result("verify", "error", f"graph6 解析失败: {exc}",
                       error=f"graph6 parse failed: {exc}")
    if n2 != n:
        return _result("verify", "error",
                       f"graph6 是 n={n2}，与给出的 n={n} 不一致",
                       error=f"n mismatch: graph6 has {n2}, expected {n}")
    good, witness = verify(n, red, s, t)
    cost = Coloring(n, s, t, red).cost()
    extra = dict(n=n, s=s, t=t, violations=int(cost), verified=bool(good),
                 witness=list(witness) if witness else None)
    if good:
        return _result("verify", "verified",
                       f"验证通过：这是一份合法 ({s},{t})-染色 ⇒ "
                       f"R({s},{t}) > {n}。", **extra)
    return _result("verify", "refuted",
                   f"验证否决：该图含单色团 {list(witness) if witness else ''}，"
                   f"不能证明任何下界。", **extra)


def violations(n: int, s: int = 5, t: int = 5,
               graph6: str = "") -> Dict[str, Any]:
    """精确统计违反度 = 红色 K_s 个数 + 蓝色 K_t 个数。"""
    n, s, t = int(n), int(s), int(t)
    try:
        n2, red = parse_graph6(str(graph6 or "").strip())
    except Exception as exc:                                # noqa: BLE001
        return _result("violations", "error", f"graph6 解析失败: {exc}",
                       error=str(exc))
    if n2 != n:
        return _result("violations", "error",
                       f"graph6 是 n={n2}，与给出的 n={n} 不一致",
                       error=f"n mismatch: {n2} != {n}")
    cost = Coloring(n, s, t, red).cost()
    verdict = "zero" if cost == 0 else "nonzero"
    return _result("violations", verdict,
                   f"违反度 {cost}（0 表示合法）。",
                   n=n, s=s, t=t, violations=int(cost), passed=(cost == 0))


def compare(operators, n: int, s: int = 5, t: int = 5, budget: float = 5.0,
            seeds: int = 3, seed_base: int = 0) -> Dict[str, Any]:
    """在**固定预算**下公平比较多个算子，并给出"是否落在噪声内"的判定。

    为什么需要这个工具
    ------------------
    在这些实例上，同一配置不同 seed 的最优违反度能差近一倍。
    因此"某算子最好"这句话几乎总要带条件。此前发生过一次：某算子在
    一个实例上均值略低，就被写成"最好"，而复算显示两者落在种子噪声内。
    与其在文档里再叮嘱一次"要诚实"，不如把这条判断**放进工具的返回值** ——
    比较的那一刻就由代码给出 verdict，agent 无需也不应自行改写。

    判定规则（保守且可解释）
    ------------------------
      * 任一算子已解出（违反度 0 且经独立验证） => 直接判 clear_winner；
      * 否则：最好与次好的均值之差 > 两者标准差的较大者 => clear_winner；
      * 否则 => inconclusive_within_noise，winner 为 None。

    返回的 `verdict` 与 `winner` 是**权威判定**，报告时不得改写为确定性结论。
    """
    try:
        ops = [str(x).strip() for x in (operators or []) if str(x).strip()]
    except TypeError:
        return _result("compare", "error", "operators 参数格式不对",
                       error="operators must be a list of operator names")
    if len(ops) < 2:
        return _result("compare", "error", "至少需要两个算子才能比较",
                       error="need at least two operators")
    unknown = [o for o in ops if o not in OPERATORS]
    if unknown:
        return _result("compare", "error", f"未知算子：{unknown}",
                       error=f"unknown operators: {unknown}")
    n, s, t = int(n), int(s), int(t)
    budget = max(0.1, min(float(budget), 120.0))
    seeds = max(2, min(int(seeds), 12))

    per: Dict[str, Any] = {}
    run_log: Dict[str, list] = {}
    solved_ops: list[str] = []

    for op in ops:
        costs: list[int] = []
        graph6: str | None = None
        for i in range(seeds):
            res = search(n, s, t, op, budget, seed_base + i)
            c = int(res.get("violations", 10 ** 9))
            costs.append(c)
            if c == 0 and res.get("verified") and graph6 is None:
                graph6 = res.get("graph6")
        mean = sum(costs) / len(costs)
        ordered = sorted(costs)
        med = ordered[len(ordered) // 2]
        var = sum((x - mean) ** 2 for x in costs) / max(1, len(costs) - 1)
        std = var ** 0.5
        per[op] = {
            "violations": costs, "mean": round(mean, 2), "median": med,
            "std": round(std, 2), "min": min(costs), "max": max(costs),
            "range": max(costs) - min(costs),
            "solved_any": 0 in costs,
        }
        run_log[op] = costs
        if 0 in costs and any(c == 0 for c in costs):
            solved_ops.append(op)

    ranking = sorted(ops, key=lambda o: per[o]["mean"])
    best, second = ranking[0], ranking[1] if len(ranking) > 1 else None
    # 注意排序是按"均值升序"（违反度越低越好），所以 best 的均值**更小**；
    # 差距要写成正数，否则会与噪声地板（标准差，非负）比较时方向相反。
    margin = round(per[second]["mean"] - per[best]["mean"], 2) if second else 0.0
    noise = round(max(per[best]["std"], per[second]["std"]), 2) if second else 0.0

    detail: Dict[str, Any] = dict(
        n=n, s=s, t=t, budget_seconds=budget, seeds=seeds,
        seed_base=seed_base, operators=ops,
        per_operator=per, ranking=ranking, best=best,
        second_best=second, margin=margin, noise_floor=noise,
    )

    if solved_ops:
        winning = min(solved_ops, key=lambda o: (per[o]["min"], per[o]["mean"]))
        detail.update(
            winner=winning, verdict="solved", solved_operators=solved_ops,
            conclusion=(f"判定：算子 {winning} 在全部 {seeds} 个 seed 上"
                        f"找到合法构造并经独立验证 ⇒ R({s},{t}) > {n}。"
                        f"{'其余算子也有解：' + ', '.join(sorted(set(solved_ops) - {winning})) if len(solved_ops) > 1 else ''}"
                        ).strip(),
        )
        return _result("compare", "solved", detail.pop("conclusion"), **detail)

    if margin > noise:
        detail.update(
            winner=best, verdict="clear_winner",
            conclusion=(f"判定：在固定 {budget}s 预算、{seeds} 个 seed 下，"
                        f"{best} 优于 {second}（均值差 {margin} > 噪声地板 "
                        f"{noise}）。这是**已测量**的相对优劣，不是任何存在性结论。"
                        ),
        )
        return _result("compare", "clear_winner", detail.pop("conclusion"), **detail)

    detail.update(
        winner=None, verdict="inconclusive_within_noise",
        conclusion=(f"**无定论**：{best}（均值 {per[best]['mean']}, 标准差 "
                    f"{per[best]['std']}）与 {second}（均值 "
                    f"{per[second]['mean']}, 标准差 {per[second]['std']}）"
                    f"的差距 {margin} ≤ 噪声地板 {noise}。"
                    f"不得宣称二者有优劣；若需要分出高下，应增加 seed 数或"
                    f"预算，并重跑本工具。"
                    ),
    )
    return _result("compare", "inconclusive", detail.pop("conclusion"), **detail)


ACTIONS = {
    "search": search,
    "enumerate": enumerate_family,
    "verify": verify_construction,
    "violations": violations,
    "compare": compare,
}
