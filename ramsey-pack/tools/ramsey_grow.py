"""ramsey_grow —— 让 agent 把自己写的东西变成**下次可用的能力**。

这是 S1（工具自扩展）的入口。它做四件事：

  register   把一个已通过测试的工具注册进来，之后每次运行都能原生调用
  list       列出已注册的能力
  unregister 注销一个工具
  harvest    扫描当前项目的 workspace，报告哪些 .py 还没被注册

**硬约束：没有测试文件就不允许注册。**
理由：一个自己写的、没人验证过的工具被当成能力，比没有它更危险——
它会带着错误的结果进入后续所有运行，而且很难归因。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_grow():
    """按路径加载 growth/grow.py（它不在已安装的包里）。"""
    try:
        from marsa.dynamic_tools import growth_dir
        gdir = growth_dir()
    except Exception:                                            # noqa: BLE001
        gdir = Path(r"D:\myagent\growth")
    path = gdir / "grow.py"
    if not path.exists():
        raise FileNotFoundError(f"找不到生长回路核心：{path}")
    mod_name = "marsa_growth_core"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve(path_value: str, workspace: Path, project_root: Path) -> Path:
    p = Path(str(path_value or "").strip())
    if p.is_absolute():
        return p
    for base in (workspace, project_root):
        cand = (base / p).resolve()
        if cand.exists():
            return cand
    return (workspace / p).resolve()


def ramsey_grow(
    runtime: dict,
    action: str = "list",
    name: str = "",
    source: str = "",
    test: str = "",
    entry: str = "run",
    description: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    hints: str = "",
    timeout: int = 120,
) -> Dict[str, Any]:
    """把 agent 自建的工具注册为可复用能力。"""
    try:
        grow = _load_grow()
    except Exception as exc:                                     # noqa: BLE001
        return _err(f"生长回路核心加载失败：{type(exc).__name__}: {exc}")

    paths = (runtime or {}).get("paths")
    slug = str((runtime or {}).get("project_slug") or "").strip()
    if paths is None or not slug:
        workspace = Path.cwd()
        project_root = workspace
    else:
        project_root = paths.project_dir(slug).resolve()
        workspace = project_root / "workspace"

    act = str(action or "list").strip().lower()

    # ---------------- list ----------------
    if act == "list":
        tools = grow.list_tools()
        return {
            "ok": True, "action": "list", "status": "ok",
            "count": len(tools), "tools": tools,
            "conclusion": (
                f"当前有 {len(tools)} 个自建工具可用。"
                + ("它们是之前运行留下的能力，优先复用，不要重写。"
                   if tools else "还没有任何自建工具。")
            ),
        }

    # ---------------- harvest ----------------
    if act == "harvest":
        if not workspace.exists():
            return _err(f"workspace 不存在：{workspace}")
        registered = {t["name"] for t in grow.list_tools()}
        candidates: List[dict] = []
        for f in sorted(workspace.rglob("*.py")):
            rel = str(f.relative_to(workspace))
            if rel.startswith("__pycache__"):
                continue
            if not f.name.startswith("test_") and f.stem not in registered:
                tests = list(f.parent.glob(f"test_{f.stem}.py"))
                candidates.append({
                    "file": rel,
                    "size": f.stat().st_size,
                    "has_test": bool(tests),
                    "test": str(tests[0].relative_to(workspace)) if tests else "",
                })
        return {
            "ok": True, "action": "harvest", "status": "ok",
            "workspace": str(workspace),
            "candidates": candidates,
            "conclusion": (
                f"workspace 里有 {len(candidates)} 个未注册的 .py。"
                f"其中 {sum(1 for c in candidates if c['has_test'])} 个有配套测试，"
                "可以走 register 注册；其余的需要先写测试。"
            ),
        }

    # ---------------- register ----------------
    if act == "register":
        if not name:
            return _err("register 需要 name 参数")
        if not source:
            return _err("register 需要 source 参数（实现文件）")
        if not test:
            return _err(
                "拒绝注册：必须提供 test 参数（该工具的测试文件）。"
                "没有测试的工具不允许成为能力——它会把错误结果带进后续所有运行。"
            )
        src = _resolve(source, workspace, project_root)
        tst = _resolve(test, workspace, project_root)
        result = grow.register_tool(
            name=name, source=str(src), test=str(tst), entry=entry,
            description=description, parameters=parameters, hints=hints,
            project=slug, timeout=timeout,
        )
        if result.get("ok"):
            result["conclusion"] = (
                f"工具 {name} 已通过测试并注册（入口 {entry}）。"
                "从现在起它是常驻能力：后续运行可以直接调用它，不必重写。"
                "写报告时应说明这一条——这是能力在运行之间延续的证据。"
            )
        return result

    # ---------------- unregister ----------------
    if act == "unregister":
        if not name:
            return _err("unregister 需要 name 参数")
        return grow.unregister_tool(name)

    return _err(f"未知 action：{act}（可用 register / list / unregister / harvest）")


def _err(msg: str) -> Dict[str, Any]:
    return {"ok": False, "status": "error", "error": msg, "conclusion": msg}
