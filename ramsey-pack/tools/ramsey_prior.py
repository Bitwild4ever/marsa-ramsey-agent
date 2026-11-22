"""ramsey_prior —— 查询已积累的策略先验：这个单元历史上哪个算子最好。

这是 S3（策略先验累积）的入口。它的价值在于**省掉重复测量**：
同一个 (n, s, t, budget) 单元不必每次从头比较一遍。

推荐严格服从统计纪律：证据不足、样本太少、或差距落在种子噪声内，
一律返回 `inconclusive` 且 `recommended` 为 None。
先验表如果开始"自信地推荐错的算子"，比没有先验更糟——它会把搜索
系统性地引向差配置。
"""

from __future__ import annotations

from typing import Any, Dict


def ramsey_prior(
    runtime: dict,
    action: str = "recommend",
    n: int = 0,
    s: int = 5,
    t: int = 5,
    budget: float = 5.0,
    min_samples: int = 3,
) -> Dict[str, Any]:
    """查询策略先验表。"""
    from marsa import prior as _prior

    act = str(action or "recommend").strip().lower()

    if act in ("stats", "overview"):
        return _prior.stats()

    if act in ("recommend", "query"):
        if not n:
            return {
                "ok": False, "status": "error",
                "error": "recommend 需要 n 参数",
                "conclusion": "recommend 需要 n 参数。",
            }
        return _prior.recommend(n=int(n), s=int(s), t=int(t),
                                budget=float(budget),
                                min_samples=int(min_samples))

    return {
        "ok": False, "status": "error",
        "error": f"未知 action：{act}（可用 recommend / stats）",
        "conclusion": f"未知 action：{act}",
    }
