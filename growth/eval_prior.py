"""S3 评估：策略先验的推荐是否站得住。

一个先验表最危险的失败模式是**自信地推荐错的算子**——它会把搜索
系统性地引向差配置，而且看起来很有根据。所以评估必须包含独立复测。

四个阶段
--------
1. 清空先验，确认新单元返回 no_data（**不做跨单元迁移**）
2. 在若干单元上跑 ramsey_compare，数据自动累积
3. 查询先验给出推荐
4. 用**全新 seed** 独立复测，检查推荐是否真的更好
5. 查询未测过的单元，确认它拒绝迁移

用法：
    python growth/eval_prior.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from marsa import prior                                        # noqa: E402
from marsa.ops import compare                                 # noqa: E402
from marsa.search import SAConfig, TabuConfig, run_operator    # noqa: E402

# 参与比较的算子（都相对便宜）
OPS = ["tabu_focus", "tabu_violation"]

# 训练单元：先验在这里积累
TRAIN_CELLS = [(42, 5, 5, 3.0), (43, 5, 5, 3.0), (44, 5, 5, 3.0)]


def _measure(n, s, t, budget, op, seed):
    """单次测量，返回违反度。与 ops.search 同一实现，但只取数字。"""
    cfg = TabuConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                     seed=seed, report_every=0, keep_elites=0)
    return int(run_operator(op, cfg).best_cost)


def main() -> int:
    print("=" * 74)
    print("S3 评估：策略先验")
    print("=" * 74)

    # ---------- 阶段 1：清空后应无数据 ----------
    p = prior.prior_path()
    if p.exists():
        p.unlink()
    print("\n[阶段 1] 清空先验表，确认新单元返回 no_data")
    r = prior.recommend(n=44, s=5, t=5, budget=3.0)
    print(f"  status = {r['status']}   recommended = {r['recommended']}")
    assert r["status"] == "no_data", r
    assert r["recommended"] is None
    print("  OK：没有数据时拒绝推荐（不做跨单元迁移）")

    # ---------- 阶段 2：积累数据 ----------
    print("\n[阶段 2] 每个单元跑 2 个独立 episode 的 ramsey_compare")
    for (n, s, t, b) in TRAIN_CELLS:
        for ep, base in enumerate((0, 50), start=1):
            res = compare(OPS, n=n, s=s, t=t, budget=b, seeds=3,
                          seed_base=base)
            print(f"  n={n} ep{ep}: verdict={res['verdict']:<28} "
                  f"margin={res['margin']} noise={res['noise_floor']}")
    st = prior.stats()
    print(f"  先验表：{st['episodes']} 条 episode，{st['cells']} 个单元")

    # ---------- 阶段 3：查询推荐 ----------
    print("\n[阶段 3] 查询先验推荐")
    recs = {}
    for (n, s, t, b) in TRAIN_CELLS:
        r = prior.recommend(n=n, s=s, t=t, budget=b)
        recs[n] = r
        pick = r["recommended"] or "（无）"
        print(f"  n={n}: status={r['status']:<22} recommended={pick}")
        if r.get("margin") is not None:
            print(f"        margin={r['margin']}  noise={r['noise_floor']}  "
                  f"样本={{{', '.join(f'{k}:{v['samples']}' for k, v in r['operators'].items())}}}")

    # ---------- 阶段 4：独立复测验证 ----------
    print("\n[阶段 4] 用**全新 seed** 独立复测，检查推荐是否真的更好")
    print(f"  {'n':>4} {'推荐算子':<18}{'推荐均值':>10}{'另一算子':>12}"
          f"{'差值':>9}  结论")
    print("  " + "-" * 70)
    agree = checked = 0
    for (n, s, t, b) in TRAIN_CELLS:
        r = recs[n]
        pick = r["recommended"]
        if pick is None:
            print(f"  {n:>4} {'（无推荐）':<18}{'—':>10}{'—':>12}{'—':>9}  跳过")
            continue
        other = [o for o in OPS if o != pick][0]
        # 全新 seed 区间，与训练时不同
        seeds = [900, 901, 902]
        pick_vals = [_measure(n, s, t, b, pick, sd) for sd in seeds]
        other_vals = [_measure(n, s, t, b, other, sd) for sd in seeds]
        pm = sum(pick_vals) / len(pick_vals)
        om = sum(other_vals) / len(other_vals)
        diff = om - pm          # 正数表示推荐更好
        verdict = "推荐更优" if diff > 0 else ("推荐更差" if diff < 0 else "持平")
        checked += 1
        if diff > 0:
            agree += 1
        print(f"  {n:>4} {pick:<18}{pm:>10.1f}{om:>12.1f}{diff:>+9.1f}  {verdict}")

    # ---------- 阶段 5：拒绝跨单元迁移 ----------
    print("\n[阶段 5] 查询未测过的单元，确认它拒绝迁移")
    r = prior.recommend(n=45, s=5, t=5, budget=3.0)
    print(f"  n=45 status = {r['status']}   recommended = {r['recommended']}")
    assert r["status"] == "no_data", "未测过的单元必须返回 no_data"
    print("  OK：不把 n=44 的结论套到 n=45")

    # ---------- 汇总 ----------
    print("\n" + "=" * 74)
    print(f"独立复测：{agree}/{checked} 个单元里推荐算子确实更优")
    if checked and agree == checked:
        print("结论：先验的推荐在全新 seed 上站得住。")
    elif checked:
        print("结论：先验有部分推荐未被复测支持 —— 这是真信号，应记录而非掩盖。")
    print("=" * 74)
    return 0 if checked and agree == checked else 1


if __name__ == "__main__":
    sys.exit(main())
