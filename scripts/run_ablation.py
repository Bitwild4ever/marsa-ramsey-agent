"""端到端消融实验：记忆机制到底有没有用？

四组对照（其余配置完全相同）：
    none        冷启动（基线）
    random      随机取回历史 elite
    nearest     取回最相似的历史 elite
    submodular  次模最大化取回多样历史 elite（本方法）

每个 episode、每个采样步都写入 JSONL，供出图与复现。
核心指标除最终最优代价外，还包括 improved_over_init ——因为热启动天然起点更好，
必须单独看"是否在起点之上还有改进"，否则结论不诚实。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.agent import AgentConfig, run_agent        # noqa: E402

MODES = ["none", "random", "nearest", "submodular"]
RUNS = Path("D:/myagent/runs")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=43)
    ap.add_argument("--s", type=int, default=5)
    ap.add_argument("--t", type=int, default=5)
    ap.add_argument("--episodes", type=int, default=8)
    ap.add_argument("--steps", type=int, default=100_000)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--operator", default="sa")
    ap.add_argument("--tag", default="ablation")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    out_json = RUNS / f"{args.tag}_n{args.n}_{args.s}{args.t}.json"

    print("=" * 84)
    print(f"记忆机制消融实验  (s,t)=({args.s},{args.t})  n={args.n}  "
          f"算子={args.operator}")
    print(f"episodes={args.episodes}  每 episode 步数={args.steps:,}  "
          f"seeds={args.seeds}")
    print("=" * 84)

    results: dict[str, list[dict]] = {}
    t_all = time.perf_counter()

    for mode in MODES:
        rows = []
        for seed in range(args.seeds):
            log_path = RUNS / f"{args.tag}_{mode}_seed{seed}.jsonl"
            mem_path = RUNS / f"{args.tag}_{mode}_seed{seed}_memory.jsonl"
            cfg = AgentConfig(
                n=args.n, s=args.s, t=args.t,
                episodes=args.episodes, seed=seed,
                log_path=str(log_path), memory_path=str(mem_path),
                memory_mode_override=mode,
                operator_override=args.operator,
                steps_override=args.steps,
                retrieve_k=3, perturb_strength=40,
                report_every=max(1000, args.steps // 40),
            )
            res = run_agent(cfg)
            eps = res.episodes
            warm = [e for e in eps if e["warm_started"]]
            rows.append({
                "seed": seed,
                "best_cost": res.best_cost,
                "solved": res.solved,
                "solved_verified": res.solved_verified,
                "n_warm": len(warm),
                "n_improved_over_init": sum(
                    1 for e in warm if e["improved_over_init"]),
                "first_episode_best": eps[0]["best_cost"] if eps else None,
                "last_episode_best": eps[-1]["best_cost"] if eps else None,
                "log": str(log_path),
            })
        results[mode] = rows
        best = min(r["best_cost"] for r in rows)
        med = statistics.median(r["best_cost"] for r in rows)
        warm_tot = sum(r["n_warm"] for r in rows)
        imp_tot = sum(r["n_improved_over_init"] for r in rows)
        print(f"  {mode:<12} 最优={best:<6} 中位={med:<7.1f} "
              f"热启动次数={warm_tot:<4} 其中在起点之上继续改进={imp_tot}")

    print("-" * 84)
    print("逐 seed 明细：")
    for mode in MODES:
        detail = "  ".join(f"s{r['seed']}:{r['best_cost']}" for r in results[mode])
        print(f"  {mode:<12} {detail}")

    base = [r["best_cost"] for r in results["none"]]
    print("-" * 84)
    print(f"基线 none 平均最优代价 = {statistics.mean(base):.1f}")
    for mode in MODES[1:]:
        vals = [r["best_cost"] for r in results[mode]]
        delta = statistics.mean(vals) - statistics.mean(base)
        rel = delta / statistics.mean(base) * 100 if statistics.mean(base) else 0
        verdict = "改善" if delta < 0 else ("持平" if delta == 0 else "变差")
        print(f"  {mode:<12} 平均={statistics.mean(vals):<7.1f} "
              f"相对基线 {delta:+.1f} ({rel:+.2f}%)  -> {verdict}")

    out_json.write_text(json.dumps({
        "config": vars(args), "results": results,
        "elapsed": time.perf_counter() - t_all,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("-" * 84)
    print(f"总用时 {time.perf_counter() - t_all:.1f}s")
    print(f"结果已保存: {out_json}")


if __name__ == "__main__":
    main()
