"""从 JSONL 迭代日志生成报告用图表（Pillow 渲染，无第三方依赖）。

目前生成两张：
  1. 记忆机制消融：全局最优代价 vs episode（四种记忆策略对比）
  2. 消融终值柱状图

数据来源是 agent 写出的 episode 级 JSONL，图里每个点都对应一次真实迭代。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.charts import bar_chart, line_chart      # noqa: E402

RUNS = Path("D:/myagent/runs")
OUT = Path("D:/myagent/report/figures")


def read_episodes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "episode":
                out.append(d)
    return out


def collect(tag: str, mode: str, seeds: list[int]) -> list[dict]:
    return [e for s in seeds for e in
            read_episodes(RUNS / f"{tag}_{mode}_seed{s}.jsonl")]


def chart_ablation(tag: str, n: int, modes: list[str], seeds: list[int],
                   title: str) -> str:
    series = []
    for mode in modes:
        eps = collect(tag, mode, seeds)
        if not eps:
            continue
        by_ep: dict[int, list[int]] = {}
        for e in eps:
            by_ep.setdefault(e["episode"], []).append(e["global_best_cost"])
        xs = sorted(by_ep)
        ys = [sum(by_ep[i]) / len(by_ep[i]) for i in xs]
        series.append({"label": mode, "xs": xs, "ys": ys})
    if not series:
        raise SystemExit(f"没有找到 {tag} 的 episode 日志，请先运行对应实验")
    return line_chart(
        OUT / f"{tag}_convergence.png", series,
        title=title, xlabel="episode（智能体迭代轮次）",
        ylabel="全局最优代价（0 = 已解出）",
        y_min_zero=True)


def chart_final_bar(tag: str, modes: list[str], seeds: list[int],
                    title: str) -> str:
    labels, vals = [], []
    for mode in modes:
        seed_best = {}
        for sd in seeds:
            rows = read_episodes(RUNS / f"{tag}_{mode}_seed{sd}.jsonl")
            if rows:
                seed_best[sd] = min(r["global_best_cost"] for r in rows)
        if seed_best:
            labels.append(mode)
            vals.append(round(sum(seed_best.values()) / len(seed_best), 1))
    return bar_chart(
        OUT / f"{tag}_final.png", labels, [{"label": "平均最优代价", "ys": vals}],
        title=title, ylabel="平均最优代价（越低越好）")


def chart_frontier(tag: str = "frontier", s: int = 5, t: int = 5) -> str:
    """前沿曲线：最优代价 vs n（来自 frontier.py 的实测存档）。"""
    path = RUNS / f"{tag}_{s}{t}.json"
    if not path.exists():
        raise SystemExit(f"缺少 {path}，请先运行 scripts/frontier.py")
    data = json.loads(path.read_text(encoding="utf-8"))
    ns = [r["n"] for r in data["rows"]]
    best = [r["best"] for r in data["rows"]]
    mean = [round(r["mean"], 1) for r in data["rows"]]
    solved = [r["n"] for r in data["rows"] if r["solved"] and r["verified"]]
    print(f"  前沿：已验证可解出的 n = {solved}")
    return line_chart(
        OUT / f"{tag}_curve.png",
        [{"label": "最优代价（多次运行取最优）", "xs": ns, "ys": best},
         {"label": "平均代价", "xs": ns, "ys": mean, "color": "#c00000"}],
        title=f"前沿曲线：候选表禁忌在 (5,5) 上把违反度压到多低（n=34..45）",
        xlabel="n（顶点数）", ylabel="违反度：单色 K5 个数（0=构造成功）",
        y_min_zero=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    modes = ["none", "random", "nearest", "submodular"]
    seeds = [0, 1]
    p1 = chart_ablation("smallbudget", 43, modes, seeds,
                        "记忆机制消融：(5,5) n=43 收敛曲线")
    print("生成:", p1)
    p2 = chart_final_bar("smallbudget", modes, seeds,
                         "记忆机制消融：终值对比（n=43）")
    print("生成:", p2)
    p3 = chart_frontier()
    print("生成:", p3)
