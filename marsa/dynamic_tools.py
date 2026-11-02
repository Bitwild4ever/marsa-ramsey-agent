"""动态工具加载器 —— 把 agent 自己写、且通过校验的工具接进 Moonshine。

为什么需要这个
--------------
Moonshine 的工具 handler 是**硬编码**在 `registry.py` 的字典里的。这意味着
agent 就算在 workspace 里写出了好用的代码，下一次运行也用不上——它只是个
"会写代码的脚本"，不是"会扩展自己能力的 agent"。

这个模块补上那一环：扫描 `growth/tools/` 下已注册的工具，为每一个生成一个
handler 闭包，注册进 registry。于是 agent 在运行 A 里写的工具，运行 B 里可以
**原生调用**。

设计约束（安全）
----------------
1. **每个工具单独捕获异常**：一个坏工具不能把整个注册表带崩。
2. **只加载显式注册过的**：必须存在 `definition.md` 与 `impl.py`，光有 .py 不算。
3. **不 import 未通过校验的**：注册时已跑过它的测试，见 grow.py。

用法（由 registry.py 调用）：
    from marsa.dynamic_tools import load_handlers
    _handler_map.update(load_handlers())
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List

DEFAULT_GROWTH_DIR = r"D:\myagent\growth"


def growth_dir() -> Path:
    return Path(os.environ.get("MARSA_GROWTH_DIR", DEFAULT_GROWTH_DIR))


def tools_dir() -> Path:
    return growth_dir() / "tools"


def _load_module(name: str, path: Path):
    """以唯一模块名加载一个 .py 文件。"""
    mod_name = f"marsa_growth_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 {path} 创建模块规格")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def registered_tools() -> List[dict]:
    """列出 growth/tools/ 下所有已注册工具（不做 import）。"""
    base = tools_dir()
    if not base.exists():
        return []
    out = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        impl = d / "impl.py"
        definition = d / "definition.md"
        if not (impl.exists() and definition.exists()):
            continue
        entry = "run"
        meta = {}
        try:
            import json
            meta_path = d / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                entry = str(meta.get("entry") or "run")
        except Exception:                                       # noqa: BLE001
            pass
        out.append({"name": d.name, "impl": impl,
                    "definition": definition, "entry": entry, "meta": meta})
    return out


def load_handlers() -> Dict[str, Callable]:
    """为每个已注册工具生成一个 handler 闭包。

    返回 {tool_name: handler}，其中 handler 的签名是 (runtime, **kwargs)。
    任何单个工具加载失败只跳过它，不影响其余。
    """
    handlers: Dict[str, Callable] = {}
    for item in registered_tools():
        name = item["name"]
        entry_name = item["entry"]
        impl_path = item["impl"]

        def _make(tool_name: str, path: Path, entry: str):
            def handler(runtime, **kwargs):
                return _invoke(tool_name, path, entry, runtime, **kwargs)
            return handler

        handlers[name] = _make(name, impl_path, entry_name)
    return handlers


def _invoke(tool_name: str, impl_path: Path, entry: str,
            runtime, **kwargs) -> dict:
    """延迟到真正调用时才 import，避免启动期把所有工具都拉起来。"""
    try:
        module = _load_module(tool_name, impl_path)
    except Exception as exc:                                    # noqa: BLE001
        return {
            "tool": tool_name, "status": "error", "passed": False,
            "overall_verdict": "tool_load_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    fn = getattr(module, entry, None)
    if fn is None:
        return {
            "tool": tool_name, "status": "error", "passed": False,
            "overall_verdict": "entry_not_found",
            "error": f"模块里找不到入口函数 {entry!r}",
        }
    try:
        result = fn(runtime=runtime, **kwargs) \
            if _accepts_runtime(fn) else fn(**kwargs)
    except TypeError:
        # 有些工具函数不想收 runtime，退一步只传参数
        try:
            result = fn(**kwargs)
        except Exception as exc:                                # noqa: BLE001
            return {
                "tool": tool_name, "status": "error", "passed": False,
                "overall_verdict": "tool_call_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
    except Exception as exc:                                    # noqa: BLE001
        return {
            "tool": tool_name, "status": "error", "passed": False,
            "overall_verdict": "tool_call_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    if isinstance(result, dict):
        result.setdefault("tool", tool_name)
        return result
    return {"tool": tool_name, "status": "completed", "passed": True,
            "result": result}


def _accepts_runtime(fn) -> bool:
    try:
        import inspect
        sig = inspect.signature(fn)
        return "runtime" in sig.parameters
    except (TypeError, ValueError):
        return False
