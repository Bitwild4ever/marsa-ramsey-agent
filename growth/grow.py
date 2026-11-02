"""生长回路的核心：把 agent 写出来的东西变成**下次运行可用的能力**。

S1 要解决的问题
---------------
之前的实测发现：agent 写了 11 个 Python 文件（Cayley 枚举器、分片驱动、
探针脚本……），但**下一次运行一个都用不上**——它们只是躺在 workspace 里的
孤儿代码。这就是"死工具"的定义。

这个模块补上缺失的那一环：

    workspace 里的代码  →  【校验】 → growth/tools/  →  【同步】 → 注册表
                            ↑ 必须有测试且通过

关键约束（对应课程材料的"约束优先于指导"）
------------------------------------------
**没有测试 = 不允许注册。** 不是建议，是硬性拒绝。
理由：一个自己写的、没人验证过的工具被注册成能力，比没有这个工具更危险——
它会带着错误的结果进入后续所有运行。

目录结构
--------
    growth/
    ├── tools/<name>/
    │   ├── impl.py          工具实现（从 workspace 复制）
    │   ├── test_impl.py     它的测试（必须通过）
    │   ├── definition.md    给模型看的工具定义
    │   ├── meta.json        入口函数名等
    │   └── provenance.json  来源：哪个项目、何时、校验输出
    ├── episodes.jsonl       每次运行的记录
    └── curve.jsonl          能力曲线数据点
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

GROWTH_DIR = Path(__file__).resolve().parent
TOOLS_DIR = GROWTH_DIR / "tools"
EPISODES = GROWTH_DIR / "episodes.jsonl"
CURVE = GROWTH_DIR / "curve.jsonl"

DEFAULT_MOONSHINE_HOME = Path(r"D:\myagent\moonshine-home")

_NAME_RE = r"^[a-z][a-z0-9_]{2,48}$"


# ===========================================================================
#  注册
# ===========================================================================

def register_tool(
    name: str,
    source: str,
    test: str,
    entry: str = "run",
    description: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    hints: str = "",
    project: str = "",
    timeout: int = 120,
) -> Dict[str, Any]:
    """校验并注册一个工具。**测试不通过就不会被注册。**

    参数
    ----
    name        工具名（小写字母开头，用来做 Moonshine 的工具名）
    source      实现文件路径（相对 project workspace 或绝对路径）
    test        测试文件路径；**必填**
    entry       入口函数名，默认 "run"
    description 给模型看的一句话说明
    parameters  JSON Schema 的 properties 字典
    hints       使用提示（markdown）
    project     来源项目名，用于追溯
    """
    import re
    name = str(name or "").strip()
    if not re.match(_NAME_RE, name):
        return _fail(f"工具名不合法：{name!r}（要求 {_NAME_RE}）")

    src = Path(source)
    if not src.exists():
        return _fail(f"实现文件不存在：{src}")
    if not test:
        return _fail("拒绝注册：必须提供测试文件。没有测试的工具不允许成为能力。")
    tst = Path(test)
    if not tst.exists():
        return _fail(f"测试文件不存在：{tst}")

    dest = TOOLS_DIR / name
    if dest.exists():
        return _fail(f"工具 {name} 已存在；如需更新请先 unregister。")

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest / "impl.py")
    shutil.copy2(tst, dest / "test_impl.py")

    # ---- 校验：测试必须通过 ----
    ok, output = _run_test(dest)
    if not ok:
        shutil.rmtree(dest, ignore_errors=True)
        return _fail(f"测试未通过，拒绝注册。输出：\n{output[-1500:]}")

    # ---- 写元数据 ----
    params = parameters or {
        "type": "object", "additionalProperties": True, "properties": {}
    }
    if "type" not in params:
        params = {"type": "object", "additionalProperties": False,
                  "properties": params, "required": []}

    meta = {
        "name": name,
        "entry": entry,
        "description": description or f"（agent 自建工具）{name}",
        "project": project,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "validation": "passed",
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    provenance = {
        "name": name,
        "source_file": str(src),
        "test_file": str(tst),
        "project": project,
        "registered_at": meta["registered_at"],
        "test_output_tail": output[-1500:],
    }
    (dest / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")

    (dest / "definition.md").write_text(
        _render_definition(name, meta["description"], params, hints, project),
        encoding="utf-8")

    synced = sync_to_moonshine()
    return {
        "ok": True,
        "action": "register",
        "status": "registered",
        "name": name,
        "entry": entry,
        "test_passed": True,
        "synced_to": synced.get("synced", []),
        "conclusion": (
            f"工具 {name} 已通过测试并注册。下次运行可用原生方式调用它，"
            f"不必重写。这就是自扩展：能力从一次运行延续到后续运行。"
        ),
    }


def _run_test(dest: Path, timeout: int = 120) -> tuple[bool, str]:
    test_file = dest / "test_impl.py"
    try:
        proc = subprocess.run(
            [sys.executable, "-u", str(test_file)],
            cwd=str(dest), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"测试超时（>{timeout}s）"
    except Exception as exc:                                    # noqa: BLE001
        return False, f"测试无法运行：{type(exc).__name__}: {exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out


def _render_definition(name: str, description: str, params: Dict[str, Any],
                       hints: str, project: str) -> str:
    meta = {
        "name": name,
        "handler": name,
        "description": description,
        "parameters": params,
    }
    header = "<!--\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n-->\n"
    body = [
        f"\n# Tool: {name}\n",
        f"\n{description}\n",
        "\n## Provenance\n",
        f"- 这个工具是 agent 自己在运行中写出来并注册的。\n",
        f"- 来源项目：`{project or '（未记录）'}`\n",
        "- 注册前已通过它自己的测试；测试不通过则不会被注册。\n",
        "\n## Usage Hint\n",
    ]
    if hints.strip():
        body.append(hints.strip() + "\n")
    else:
        body.append("- 上次运行发现这个工具好用，所以把它保留了下来；"
                    "优先复用它，而不是重新写一份。\n")
    return header + "".join(body)


# ===========================================================================
#  同步到 Moonshine 运行时
# ===========================================================================

def sync_to_moonshine(home: Optional[Path] = None) -> Dict[str, Any]:
    """把已注册工具的 definition.md 复制进运行时，使其对模型可见。

    同时清理**我们曾经同步过、但现在已注销**的定义文件。

    为什么需要清单：Moonshine 的 ToolRegistry 在遇到一个"有定义但没有
    handler"的工具时会直接抛 KeyError，导致**整个注册表加载失败**。
    所以注销时必须把运行时的定义一起删掉，否则一个孤儿定义会让所有
    工具（包括内置的）全部不可用。这里用 growth/synced.json 记录我们
    推送过哪些名字，才能可靠地只删自己的、不误删别人的。
    """
    home = Path(home) if home else DEFAULT_MOONSHINE_HOME
    defdir = home / "tools" / "definitions"
    if not defdir.exists():
        return {"ok": False, "error": f"运行时目录不存在：{defdir}",
                "synced": []}

    manifest_path = GROWTH_DIR / "synced.json"
    previously: List[str] = []
    try:
        if manifest_path.exists():
            previously = list(json.loads(
                manifest_path.read_text(encoding="utf-8")).get("names", []))
    except (json.JSONDecodeError, OSError):
        previously = []

    synced, removed = [], []
    wanted = {t["name"] for t in list_tools()}

    # 1) 删掉注销掉的
    for name in previously:
        if name in wanted:
            continue
        dst = defdir / f"{name}.md"
        if dst.exists():
            dst.unlink()
            removed.append(name)

    # 2) 推送当前的
    for t in list_tools():
        src = TOOLS_DIR / t["name"] / "definition.md"
        dst = defdir / f"{t['name']}.md"
        if src.exists():
            shutil.copy2(src, dst)
            synced.append(t["name"])

    manifest_path.write_text(
        json.dumps({"names": sorted(wanted)}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    return {"ok": True, "synced": synced, "removed": removed,
            "definitions_dir": str(defdir)}


def list_tools() -> List[Dict[str, Any]]:
    from marsa.dynamic_tools import registered_tools
    out = []
    for item in registered_tools():
        meta = item.get("meta") or {}
        out.append({
            "name": item["name"],
            "entry": item["entry"],
            "description": meta.get("description", ""),
            "project": meta.get("project", ""),
            "registered_at": meta.get("registered_at", ""),
        })
    return out


def unregister_tool(name: str, home: Optional[Path] = None) -> Dict[str, Any]:
    dest = TOOLS_DIR / name
    if not dest.exists():
        return _fail(f"没有这个工具：{name}")
    shutil.rmtree(dest, ignore_errors=True)
    synced = sync_to_moonshine(home)
    return {"ok": True, "action": "unregister", "status": "removed",
            "name": name, "removed_from": synced.get("removed", []),
            "conclusion": f"工具 {name} 已注销，下次运行不再可用。"}


# ===========================================================================
#  运行记录与能力曲线（S2）
# ===========================================================================

def record_episode(record: Dict[str, Any]) -> None:
    record = dict(record)
    record.setdefault("recorded_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    EPISODES.parent.mkdir(parents=True, exist_ok=True)
    with EPISODES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_curve(point: Dict[str, Any]) -> None:
    point = dict(point)
    point.setdefault("recorded_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    CURVE.parent.mkdir(parents=True, exist_ok=True)
    with CURVE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(point, ensure_ascii=False) + "\n")


def read_curve() -> List[Dict[str, Any]]:
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


def _fail(msg: str) -> Dict[str, Any]:
    return {"ok": False, "status": "error", "error": msg,
            "conclusion": msg}
