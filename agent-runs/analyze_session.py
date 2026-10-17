"""分析一次 Moonshine 自主运行的**无人值守稳定性**。

从会话日志里提取稳定性信号：
  * 工具调用总量、各工具频次
  * **死循环检测**：连续 N 次完全相同的（工具名 + 参数）
  * 错误率与错误类型
  * 研究日志里 failed_path / verification 记录数
  * 终止原因

用法：
    python agent-runs/analyze_session.py <session-dir>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"_unparsed": line[:120]})
    return out


def _normalize_call(event: dict) -> tuple:
    """把一次工具调用归一化成可比较的签名（工具名 + 参数预览）。

    Moonshine 的 tool_events.jsonl 里字段是 `tool` / `arguments_preview`
    （预览字符串），不是 `name` / `arguments`。用错字段会让所有调用看起来
    一样，从而产生"死循环"的**假阳性**。
    """
    name = str(event.get("tool") or event.get("name") or event.get("type") or "?")
    args = (event.get("arguments_preview")
            or event.get("arguments")
            or event.get("args")
            or event.get("input")
            or "")
    return (name, str(args)[:220])


def analyze(session_dir: Path, project_dir: Path | None = None) -> dict:
    events = _read_jsonl(session_dir / "tool_events.jsonl")
    messages = _read_jsonl(session_dir / "messages.jsonl")

    # 工具频次
    names = [str(e.get("tool") or e.get("name") or e.get("type") or "?")
             for e in events]
    freq = Counter(names)

    # 死循环检测：连续相同调用签名
    calls = [_normalize_call(e) for e in events]
    max_run, cur_run = 1, 1
    worst = (1, calls[0] if calls else None)
    for i in range(1, len(calls)):
        if calls[i] == calls[i - 1]:
            cur_run += 1
            if cur_run > max_run:
                max_run, worst = cur_run, (cur_run, calls[i])
        else:
            cur_run = 1
    loop_suspected = worst[0] >= 5 and worst[1] is not None

    # 错误与空结果：Moonshine 用 status / error / output_preview 字段
    errorish = [e for e in events
                if (str(e.get("status") or "").lower() not in ("ok", "")
                    or e.get("error"))]
    empty_results = [e for e in events
                     if not (e.get("output_preview") or e.get("output")
                             or e.get("content"))]

    # 研究日志的记录类型分布
    types: Counter = Counter()
    if project_dir and (project_dir / "memory" / "research_log.jsonl").exists():
        log = _read_jsonl(project_dir / "memory" / "research_log.jsonl")
        types = Counter(str(r.get("type") or "?") for r in log)
    else:
        log = []

    return {
        "session": session_dir.name,
        "total_tool_calls": len(events),
        "total_messages": len(messages),
        "distinct_tools": len(freq),
        "tool_frequency": dict(freq.most_common()),
        "max_consecutive_same_call": worst[0],
        "loop_suspected": loop_suspected,
        "loop_signature": (f"{worst[1][0]}  x{worst[0]}"
                           if loop_suspected else "—"),
        "events_with_error": len(errorish),
        "events_with_empty_result": len(empty_results),
        "research_log_records": len(log),
        "research_log_types": dict(types.most_common()),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    session = Path(sys.argv[1])
    if not session.exists():
        print(f"找不到会话目录: {session}")
        return 2
    # 可选：项目目录，用于读取 research_log.jsonl 的类型分布
    project = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    r = analyze(session, project)

    print("=" * 62)
    print(f"无人值守稳定性分析 —— {r['session']}")
    print("=" * 62)
    print(f"  工具调用总数        : {r['total_tool_calls']}")
    print(f"  消息总数            : {r['total_messages']}")
    print(f"  使用过的不同工具    : {r['distinct_tools']}")
    print()
    print("  工具频次：")
    for name, cnt in r["tool_frequency"].items():
        print(f"    {name:<32}{cnt:>5}")
    print()
    print(f"  最长连续相同调用    : {r['max_consecutive_same_call']} 次")
    if r["loop_suspected"]:
        print(f"  死循环嫌疑          : 是  ({r['loop_signature']})")
    else:
        print("  死循环嫌疑          : 否")
    print(f"  失败状态的事件      : {r['events_with_error']}")
    print(f"  结果为空的事件      : {r['events_with_empty_result']}")
    print(f"  研究日志记录数      : {r['research_log_records']}")
    if r["research_log_types"]:
        print("  日志类型分布        :",
              ", ".join(f"{k}={v}" for k, v in r["research_log_types"].items()))

    print()
    print("-" * 62)
    verdict = []
    if r["loop_suspected"]:
        verdict.append(
            f"**发现死循环嫌疑**：连续 {r['max_consecutive_same_call']} 次"
            f"调用 {r['loop_signature']}。这正是人格里"
            f"'工具反复返回同一错误而不加改变地反复重试'所警告的情况。"
        )
    else:
        verdict.append("未发现死循环（最长连续相同调用 %d 次）。"
                       % r["max_consecutive_same_call"])
    if r["total_tool_calls"] >= 40:
        verdict.append(f"工具调用 {r['total_tool_calls']} 次，"
                       f"规模足够观察无人值守行为。")
    if r["research_log_records"] >= 10:
        verdict.append(f"研究日志 {r['research_log_records']} 条，"
                       f"状态维护在持续进行。")
    for v in verdict:
        print(f"  - {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
