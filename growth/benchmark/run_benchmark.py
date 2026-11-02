"""能力基准 —— 用已知答案测「它现在到底几斤几两」，并画能力曲线。

为什么必须有这个
----------------
没有基准，"agent 变聪明了" 就只是自我感觉。这个脚本把能力变成一个数字：

  * **判定正确率**：每题答案都来自本项目自己的完整穷举，不是猜的
  * **工具覆盖数**：agent 每注册一个新工具，这个数字会真的上升
  * **总耗时**：同样正确率下更快也是进步

跑一次就往 `growth/curve.jsonl` 追加一个点。多次运行后把它画出来，
就能回答"第 20 次比第 1 次强了多少"这个唯一有意义的问题。

Tier 说明
---------
Tier 1（本文件实现）：**纯确定性，不调用任何 LLM**。测的是工具与已注册能力。
    优点：免费、秒级、可无限次跑。缺点：测不到"决策能力"。
Tier 2（未实现）：整轮 agent 自主运行，测决策与工具选择。
    缺点：每次都要花模型调用，只能稀疏地跑。

用法：
    python growth/benchmark/run_benchmark.py
    python growth/benchmark/run_benchmark.py --tier t1 --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

GROWTH = Path(__file__).resolve().parent.parent
ROOT = GROWTH.parent
sys.path.insert(0, str(ROOT))

TASKS = Path(__file__).resolve().parent / "tasks.json"
CURVE = GROWTH / "curve.jsonl"
MOONSHINE_HOME = Path(r"D:\myagent\moonshine-home")


def _runtime():
    from moonshine.moonshine_constants import MoonshinePaths
    from moonshine.moonshine_cli.config import resolve_home
    paths = MoonshinePaths(resolve_home(str(MOONSHINE_HOME)))
    return {"mode": "research", "project_slug": "benchmark", "paths": paths}


def _registry():
    from moonshine.tools.registry import ToolRegistry
    from moonshine.moonshine_constants import MoonshinePaths
    from moonshine.moonshine_cli.config import resolve_home
    return ToolRegistry(MoonshinePaths(resolve_home(str(MOONSHINE_HOME))))


def _check(result: dict, expect: dict) -> tuple[bool, str]:
    """把工具返回与期望比对。"""
    for key, want in expect.items():
        if key == "has_solution":
            got = bool(result.get("solutions_found")
                       or result.get("solutions")
                       or (result.get("status") == "exists"))
            if got != bool(want):
                return False, f"has_solution 期望 {want}，实得 {got}"
            continue
        if key not in result:
            return False, f"返回里没有字段 {key}"
        got = result[key]
        if got != want:
            return False, f"{key} 期望 {want}，实得 {got}"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="t1", choices=["t1"])
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-record", action="store_true",
                    help="只跑不写入曲线")
    args = ap.parse_args()

    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    tasks = spec["tasks"]

    try:
        reg = _registry()
        runtime = _runtime()
    except Exception as exc:                                     # noqa: BLE001
        print(f"[错误] 无法加载 Moonshine 注册表：{type(exc).__name__}: {exc}")
        print("提示：先运行 .\\marsa.ps1 install，或确认 PYTHONPATH 含 "
              "D:\\myagent 与 D:\\myagent\\_shims")
        return 2

    available = set(reg._tools)
    # 只统计**agent 自己注册**的工具（growth/tools/），不要把 Moonshine 原生工具算进来
    try:
        from marsa.dynamic_tools import registered_tools
        dynamic = sorted(t["name"] for t in registered_tools())
    except Exception:                                            # noqa: BLE001
        dynamic = []

    print("=" * 74)
    print("MARSA 能力基准 (Tier 1 — 纯确定性，不调用 LLM)")
    print("=" * 74)
    print(f"  注册工具总数 : {len(available)}")
    print(f"  自建工具     : {', '.join(dynamic) if dynamic else '(无)'}")
    print()

    t0 = time.perf_counter()
    passed = attempted = skipped = 0
    tools_ok: set[str] = set()
    rows = []

    for task in tasks:
        tid = task["id"]
        tool = task["tool"]
        optional = bool(task.get("optional"))

        if tool not in available:
            skipped += 1
            rows.append((tid, tool, "SKIP", "工具未注册"))
            if args.verbose:
                print(f"  {tid:<16} {tool:<24} SKIP  (工具未注册)")
            continue

        attempted += 1
        try:
            res = reg.dispatch(tool, dict(task["args"]), runtime)
        except Exception as exc:                                 # noqa: BLE001
            rows.append((tid, tool, "ERROR", f"{type(exc).__name__}: {exc}"))
            if args.verbose:
                print(f"  {tid:<16} {tool:<24} ERROR {exc}")
            continue

        good, why = _check(res, task["expect"])
        if good:
            passed += 1
            tools_ok.add(tool)
            rows.append((tid, tool, "PASS", ""))
            if args.verbose:
                print(f"  {tid:<16} {tool:<24} PASS")
        else:
            rows.append((tid, tool, "FAIL", why))
            if args.verbose:
                print(f"  {tid:<16} {tool:<24} FAIL  {why}")

    duration = time.perf_counter() - t0
    total = len(tasks)
    # 主指标必须是**绝对**的：passed / 全部题数。
    # 如果只算 passed/attempted，那么"工具没注册所以跳过"不会扣分，
    # 能力下降就看不出来了 —— 这正是我们最想测的东西。
    score = (passed / total) if total else 0.0
    accuracy = (passed / attempted) if attempted else 0.0

    print()
    print("-" * 74)
    print(f"  通过   : {passed}/{total} 题"
          f"{f'   (其中 {skipped} 题因工具未注册被跳过)' if skipped else ''}")
    print(f"  基准分 : {score:.1%}   ← 主指标（通过/总题数）")
    print(f"  条件正确率: {accuracy:.1%}   (通过/实际尝试)")
    print(f"  工具覆盖: {len(tools_ok)} 种 —— {', '.join(sorted(tools_ok))}")
    print(f"  耗时   : {duration:.1f}s")

    # ---- 与上一次比 ----
    prev = _last_point()
    if prev:
        delta = score - float(prev.get("score", 0))
        arrow = "↑" if delta > 0.0001 else ("↓" if delta < -0.0001 else "→")
        print(f"  对比上次: {prev.get('score', 0):.1%} → {score:.1%}  {arrow} "
              f"{delta:+.1%}")
        prev_tools = int(prev.get("tools_covered", 0))
        print(f"  工具覆盖: {prev_tools} → {len(tools_ok)} "
              f"{'（新增能力）' if len(tools_ok) > prev_tools else ''}")
    else:
        print("  对比上次: 这是第一个数据点（曲线起点）")

    print("-" * 74)

    failures = [r for r in rows if r[2] in ("FAIL", "ERROR")]
    if failures:
        print("\n未通过的题目：")
        for tid, tool, status, why in failures:
            print(f"  {status:<5} {tid:<16} {why}")

    if not args.no_record:
        point = {
            "tier": "t1",
            "run_index": _next_index(),
            "passed": passed,
            "total": total,
            "attempted": attempted,
            "skipped": skipped,
            "score": round(score, 4),
            "accuracy": round(accuracy, 4),
            "tools_covered": len(tools_ok),
            "tools": sorted(tools_ok),
            "duration_seconds": round(duration, 2),
            "total_registered_tools": len(available),
            "dynamic_tools": dynamic,
        }
        _append(point)
        print(f"\n已写入曲线：{CURVE}（第 {point['run_index']} 个数据点）")

    return 0 if not failures else 1


def _read_curve() -> list[dict]:
    if not CURVE.exists():
        return []
    out = []
    for line in CURVE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _last_point():
    pts = [p for p in _read_curve() if p.get("tier") == "t1"]
    return pts[-1] if pts else None


def _next_index() -> int:
    pts = [p for p in _read_curve() if p.get("tier") == "t1"]
    return (int(pts[-1].get("run_index", 0)) + 1) if pts else 1


def _append(point: dict) -> None:
    point.setdefault("recorded_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    CURVE.parent.mkdir(parents=True, exist_ok=True)
    with CURVE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(point, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
