"""列出 agent 自己注册过的工具，以及能力曲线的摘要。

用法：python growth/list_tools.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GROWTH = Path(__file__).resolve().parent
ROOT = GROWTH.parent
sys.path.insert(0, str(ROOT))

from growth import grow                                       # noqa: E402


def main() -> int:
    tools = grow.list_tools()

    print("=" * 72)
    print("agent 自建的工具（能力存量）")
    print("=" * 72)
    if not tools:
        print("  还没有。下次运行中可以用 ramsey_grow 注册。")
    else:
        for t in tools:
            desc = (t["description"] or "")[:64]
            print(f"  {t['name']:<24} {desc}")
            print(f"  {'':<24} 来源项目: {t['project'] or '(未记录)'}"
                  f"   注册于 {t['registered_at']}")
    print("=" * 72)

    curve = grow.read_curve()
    t1 = [p for p in curve if p.get("tier") == "t1"]
    print(f"\n能力曲线（Tier 1，共 {len(t1)} 个数据点）")
    if not t1:
        print("  还没有数据点。运行 `marsa.ps1 benchmark` 开始记录。")
    else:
        print(f"  {'#':>3}  {'基准分':>8}  {'工具覆盖':>8}  {'耗时':>8}  自建工具")
        for p in t1:
            print(f"  {p['run_index']:>3}  {p['score']:>7.1%}  "
                  f"{p['tools_covered']:>8}  {p['duration_seconds']:>7.1f}s  "
                  f"{', '.join(p.get('dynamic_tools') or []) or '—'}")
        if len(t1) >= 2:
            first, last = t1[0], t1[-1]
            d = last["score"] - first["score"]
            print(f"\n  首末对比：{first['score']:.1%} → {last['score']:.1%} "
                  f"({d:+.1%})")
            dt = last["tools_covered"] - first["tools_covered"]
            print(f"  工具覆盖：{first['tools_covered']} → "
                  f"{last['tools_covered']} ({dt:+d})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
