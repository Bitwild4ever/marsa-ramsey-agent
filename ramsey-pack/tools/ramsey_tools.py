"""Ramsey 反例构造的**确定性**工具 —— 本项目对 Moonshine 的二次开发贡献。

为什么必须补这一层
------------------
Moonshine 原生的 `verify_correctness_*` 系列是 **LLM 评审**：它审查的是
"证明过程"里有没有计算错误、假设误用、逻辑漏洞。这对待数学证明是合理的。

但对**计算性断言**——例如"这个 43 顶点的图不含 $K_5$"——LLM 无法判定。
它只能评论，不能计算。这类断言的正确处理方式是**精确计算**，而且要有
一条与搜索器**独立实现**的验证路径（否则搜索器报错时会一起错）。

本项目已有的 `marsa` 引擎正好提供这个能力，本模块把它接成 Moonshine 的
一等工具，使这一类断言由**计算**决定，而不是由模型评价决定。

工具清单
--------
- `ramsey_verify_construction`：**精确独立验证**一份构造是否合法（核心贡献）
- `ramsey_violations`：精确统计违反度（单色团个数）
- `ramsey_search`：跑一次固定预算的搜索并返回结果
- `ramsey_enumerate_family`：对对称构造族做**穷举**，给出判定性结论
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

# --- 计算内核：与搜索器独立的实现路径 -------------------------------------
from marsa.bitset import Coloring
from marsa.search import SAConfig, TabuConfig, run_operator
from marsa.symmetric import (
    FastChecker, circulant_red, circulant_size, verify_bits,
)
from marsa.verifier import parse_graph6, to_graph6, verify

TOOL_VERSION = "marsa-0.2.0"


def _safe_graph6(n: int, red: List[int]) -> str:
    try:
        return to_graph6(n, red)
    except Exception:                                     # noqa: BLE001
        return ""


def _result(tool: str, passed: bool, verdict: str, **extra) -> Dict[str, object]:
    """统一的结果包装，字段命名与 Moonshine 的验证结果保持一致。"""
    payload: Dict[str, object] = {
        "tool": tool,
        "status": "completed",
        "passed": bool(passed),
        "overall_verdict": verdict,
        "failure_policy": (
            "Deterministic exact computation. No LLM judgement is involved. "
            "A construction passes only if it contains no monochromatic "
            "K_s and no monochromatic K_t, checked by an implementation "
            "independent of the search engine."
        ),
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": TOOL_VERSION,
    }
    payload.update(extra)
    return payload


# --------------------------------------------------------------------------
# 1. 精确验证（核心贡献）
# --------------------------------------------------------------------------

def ramsey_verify_construction(
    runtime: dict,
    n: int,
    s: int,
    t: int,
    graph6: str,
    project_slug: str = "",
) -> Dict[str, object]:
    """用独立实现精确判定一份构造是否合法。

    返回 passed=True 表示：该图既不含红色 K_s，也不含蓝色 K_t；
    于是由定义立得 R(s,t) > n。
    """
    n = int(n)
    s, t = int(s), int(t)
    text = str(graph6 or "").strip()
    if not text:
        return _result("ramsey_verify_construction", False, "invalid_input",
                       claim=f"R({s},{t}) > {n}", error="graph6 is empty")
    try:
        n_parsed, red = parse_graph6(text)
    except Exception as exc:                              # noqa: BLE001
        return _result("ramsey_verify_construction", False, "invalid_input",
                       claim=f"R({s},{t}) > {n}",
                       error=f"graph6 parse failed: {exc}")
    if n_parsed != n:
        return _result("ramsey_verify_construction", False, "invalid_input",
                       claim=f"R({s},{t}) > {n}",
                       error=f"graph6 encodes n={n_parsed}, expected n={n}")

    ok, witness = verify(n, red, s, t)
    cost = Coloring(n, s, t, red).cost()
    detail = {
        "claim": f"There exists a 2-colouring of K_{n} with no red K_{s} "
                 f"and no blue K_{t}; equivalently R({s},{t}) > {n}.",
        "n": n, "s": s, "t": t,
        "violations": int(cost),
        "method": "explicit adjacency matrix + exhaustive subset enumeration "
                  "(independent of the bitmask search engine)",
    }
    if ok:
        detail["conclusion"] = f"VERIFIED. This construction proves R({s},{t}) > {n}."
        return _result("ramsey_verify_construction", True, "verified", **detail)
    detail["witness_clique"] = list(witness) if witness else None
    detail["conclusion"] = (
        f"REFUTED. The given colouring contains a monochromatic clique, "
        f"so it does NOT prove R({s},{t}) > {n}."
    )
    return _result("ramsey_verify_construction", False, "refuted", **detail)


# --------------------------------------------------------------------------
# 2. 违反度
# --------------------------------------------------------------------------

def ramsey_violations(
    runtime: dict,
    n: int,
    s: int,
    t: int,
    graph6: str,
) -> Dict[str, object]:
    """精确统计违反度 = 红色 K_s 个数 + 蓝色 K_t 个数（0 表示合法）。"""
    n, s, t = int(n), int(s), int(t)
    try:
        n_parsed, red = parse_graph6(str(graph6 or "").strip())
    except Exception as exc:                              # noqa: BLE001
        return _result("ramsey_violations", False, "invalid_input",
                       error=f"graph6 parse failed: {exc}")
    if n_parsed != n:
        return _result("ramsey_violations", False, "invalid_input",
                       error=f"graph6 encodes n={n_parsed}, expected n={n}")
    cost = Coloring(n, s, t, red).cost()
    return _result("ramsey_violations", cost == 0, "zero" if cost == 0 else "nonzero",
                   n=n, s=s, t=t, violations=int(cost))


# --------------------------------------------------------------------------
# 3. 搜索
# --------------------------------------------------------------------------

_OPERATORS = ("sa", "tabu", "tabu_focus", "tabu_sample", "tabu_violation")


def ramsey_search(
    runtime: dict,
    n: int,
    s: int = 5,
    t: int = 5,
    operator: str = "tabu_focus",
    budget_seconds: float = 20.0,
    seed: int = 0,
) -> Dict[str, object]:
    """在固定墙钟预算下跑一次搜索，返回最优违反度与（若已解出）构造。

    结果一律经独立验证器复核；搜索器只有提议权，没有宣布权。
    """
    n, s, t = int(n), int(s), int(t)
    op = str(operator or "tabu_focus")
    if op not in _OPERATORS:
        return _result("ramsey_search", False, "invalid_input",
                       error=f"unknown operator {op!r}; choose from {_OPERATORS}")
    budget = max(0.1, min(float(budget_seconds or 20.0), 600.0))
    seed = int(seed)

    if op == "sa":
        cfg = SAConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                       seed=seed, report_every=0, keep_elites=0)
    else:
        cfg = TabuConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                         seed=seed, report_every=0, keep_elites=0)
    started = time.perf_counter()
    res = run_operator(op, cfg)
    elapsed = time.perf_counter() - started

    detail: Dict[str, object] = {
        "n": n, "s": s, "t": t, "operator": op, "seed": seed,
        "budget_seconds": budget,
        "elapsed_seconds": round(elapsed, 3),
        "steps": int(res.steps_done),
        "violations": int(res.best_cost),
        "init_violations": int(res.init_cost),
    }
    if res.best_cost == 0:
        ok, witness = verify(n, res.best_red, s, t)
        detail["graph6"] = _safe_graph6(n, res.best_red)
        detail["independent_verification"] = bool(ok)
        if ok:
            detail["conclusion"] = (
                f"SOLVED and independently VERIFIED: R({s},{t}) > {n}."
            )
            return _result("ramsey_search", True, "solved", **detail)
        detail["conclusion"] = (
            "The search reported zero violations but the independent verifier "
            "REFUTED it. Treat the search output as unreliable."
        )
        return _result("ramsey_search", False, "verification_failed", **detail)
    detail["conclusion"] = (
        f"Not solved within the budget. Best violations = {res.best_cost}. "
        f"This is a bound on effort, not a proof that no construction exists."
    )
    return _result("ramsey_search", False, "unsolved", **detail)


# --------------------------------------------------------------------------
# 4. 对称族穷举（判定性）
# --------------------------------------------------------------------------

def ramsey_enumerate_family(
    runtime: dict,
    n: int,
    s: int = 5,
    t: int = 5,
    family: str = "circulant",
) -> Dict[str, object]:
    """对某个对称构造族做**穷举**，给出"存在/不存在"的判定性结论。

    循环图族的自由参数只有 floor(n/2) 个比特（n=43 时 21 个，约 210 万种），
    把合法性判定化为位运算后可以**全部查完**。因此结论是判定性的，
    不是"没搜到"。
    """
    n, s, t = int(n), int(s), int(t)
    fam = str(family or "circulant").strip().lower()
    if fam != "circulant":
        return _result("ramsey_enumerate_family", False, "invalid_input",
                       error="only family='circulant' is supported")
    k = circulant_size(n)
    total = 1 << k
    if total > 40_000_000:
        return _result("ramsey_enumerate_family", False, "too_large",
                       n=n, s=s, t=t, family=fam, space_size=total,
                       error="search space too large for exhaustive enumeration")

    checker = FastChecker(n, s, t)
    started = time.perf_counter()
    found: List[int] = []
    for bits in range(total):
        if checker.is_valid(bits):
            found.append(bits)
    elapsed = time.perf_counter() - started

    detail: Dict[str, object] = {
        "n": n, "s": s, "t": t, "family": fam,
        "free_parameters": k, "space_size": total,
        "solutions_found": len(found),
        "elapsed_seconds": round(elapsed, 2),
        "exhaustive": True,
    }
    if found:
        bits = found[0]
        red = circulant_red(n, bits)
        ok, _w = verify_bits(n, s, t, bits)
        detail["example"] = {
            "connection_set": sorted(
                {d for d in range(1, n // 2 + 1) if bits >> (d - 1) & 1}
            ),
            "graph6": _safe_graph6(n, red),
            "connection_set_bits": bits,
        }
        detail["independent_verification"] = bool(ok)
        detail["conclusion"] = (
            f"EXHAUSTIVE: the {fam} family on n={n} contains "
            f"{len(found)} valid ({s},{t})-colouring(s); the whole family was "
            f"enumerated. Hence R({s},{t}) > {n} is witnessed inside this family."
        )
        return _result("ramsey_enumerate_family", True, "exists", **detail)

    detail["conclusion"] = (
        f"EXHAUSTIVE NEGATIVE RESULT: the {fam} family on n={n} contains NO "
        f"valid ({s},{t})-colouring. All {total} members were checked, so this "
        f"is a decision, not a failed search. This rules out this family as a "
        f"route to R({s},{t}) > {n}."
    )
    return _result("ramsey_enumerate_family", False, "none_exist", **detail)
