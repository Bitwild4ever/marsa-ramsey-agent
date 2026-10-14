"""把 ramsey-pack 安装进一个 Moonshine 检出（幂等，可重复运行）。

做四件事：
  1. 把 tools/ramsey_tools.py 复制进 Moonshine 源码树
  2. 把工具定义 .md 复制进运行时 home 的 tools/definitions/
  3. 把技能 SKILL.md 复制进运行时 home 的 skills/installed/
  4. 给 Moonshine 的 tools/registry.py 打补丁，注册我们的 4 个处理函数

第 4 步是必须的：Moonshine 的 `_handler_map` 是**硬编码**的，
运行时目录里的工具定义只能引用已注册的 handler，无法自行引入新的 Python 实现。
这是我们这次"二次开发"唯一需要改动 Moonshine 源码的地方（约 40 行，纯新增）。

用法：
    python ramsey-pack/install.py --moonshine <Moonshine 源码目录> --home <运行时 home>
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent

IMPORT_ANCHOR = "from moonshine.tools.verification_tools import ("
IMPORT_BLOCK = '''

# --- 本项目（二次开发）新增：Ramsey 反例构造的确定性工具 -------------------
# 这些工具**不调用 LLM**：它们调用一个与搜索器独立实现的精确验证内核。
# 之所以必须补这一层：Moonshine 原生的 verify_correctness_* 是 LLM 评审，
# 它审的是"证明过程"，无法判定"某个具体图不含 K5"这类**计算性断言**。
try:  # 允许在不安装 marsa 时照常使用 Moonshine 的其余功能
    from moonshine.tools.ramsey_tools import (
        ramsey_enumerate_family,
        ramsey_search,
        ramsey_verify_construction,
        ramsey_violations,
    )
    _RAMSEY_TOOLS_AVAILABLE = True
    _RAMSEY_IMPORT_ERROR = ""
except Exception as _exc:  # noqa: BLE001
    ramsey_enumerate_family = ramsey_search = None
    ramsey_verify_construction = ramsey_violations = None
    _RAMSEY_TOOLS_AVAILABLE = False
    _RAMSEY_IMPORT_ERROR = str(_exc)


def _ramsey_unavailable(tool_name: str):
    """返回一个明确的失败结果，而不是让整个框架崩掉。"""
    def _handler(runtime, **kwargs):
        return {
            "tool": tool_name,
            "status": "completed",
            "passed": False,
            "overall_verdict": "engine_unavailable",
            "error": (
                "The `marsa` computation engine is not importable, so the "
                "deterministic Ramsey tools cannot run. Install it with "
                "`pip install -e <path-to-marsa>`. Import error: %s"
                % _RAMSEY_IMPORT_ERROR
            ),
        }
    return _handler
'''

HANDLER_ANCHOR = '            "load_mcp_server_definition": lambda runtime, **kwargs: load_mcp_server_definition(runtime, **kwargs),\n'
HANDLER_BLOCK = '''            # --- 本项目新增的确定性工具 ---
            "ramsey_verify_construction": (
                (lambda runtime, **kwargs: ramsey_verify_construction(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_verify_construction")
            ),
            "ramsey_violations": (
                (lambda runtime, **kwargs: ramsey_violations(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_violations")
            ),
            "ramsey_search": (
                (lambda runtime, **kwargs: ramsey_search(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_search")
            ),
            "ramsey_enumerate_family": (
                (lambda runtime, **kwargs: ramsey_enumerate_family(runtime, **kwargs))
                if _RAMSEY_TOOLS_AVAILABLE
                else _ramsey_unavailable("ramsey_enumerate_family")
            ),
'''

MARKER = "_RAMSEY_TOOLS_AVAILABLE = True"


def patch_registry(registry_path: Path) -> str:
    """幂等地给 registry.py 加上我们的 import 块与 handler 条目。"""
    text = registry_path.read_text(encoding="utf-8")
    if MARKER in text:
        return "已是打过补丁的状态，跳过"

    if IMPORT_ANCHOR not in text:
        raise SystemExit(f"找不到 import 锚点，registry.py 结构可能已变: {registry_path}")
    # 在 verification_tools 的 import 语句结束后插入
    idx = text.index(IMPORT_ANCHOR)
    close = text.index(")\n", idx) + len(")\n")
    text = text[:close] + IMPORT_BLOCK + text[close:]

    if HANDLER_ANCHOR not in text:
        raise SystemExit(f"找不到 handler 锚点，registry.py 结构可能已变: {registry_path}")
    text = text.replace(HANDLER_ANCHOR, HANDLER_ANCHOR + HANDLER_BLOCK, 1)

    shutil.copy2(registry_path, registry_path.with_suffix(".py.orig"))
    registry_path.write_text(text, encoding="utf-8")
    return "已打补丁（原文件备份为 registry.py.orig）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moonshine", required=True,
                    help="Moonshine 源码目录（含 tools/registry.py）")
    ap.add_argument("--home", required=True, help="Moonshine 运行时 home")
    args = ap.parse_args()

    moon = Path(args.moonshine).resolve()
    home = Path(args.home).resolve()
    registry = moon / "tools" / "registry.py"
    if not registry.exists():
        raise SystemExit(f"找不到 {registry}")

    # 1) 工具实现
    shutil.copy2(PACK / "tools" / "ramsey_tools.py",
                 moon / "tools" / "ramsey_tools.py")
    print(f"[1/4] 已复制 tools/ramsey_tools.py -> {moon / 'tools'}")

    # 2) 工具定义
    defs_src = PACK / "tools" / "definitions"
    defs_dst = home / "tools" / "definitions"
    defs_dst.mkdir(parents=True, exist_ok=True)
    n_defs = 0
    for f in sorted(defs_src.glob("*.md")):
        shutil.copy2(f, defs_dst / f.name)
        n_defs += 1
    print(f"[2/4] 已复制 {n_defs} 个工具定义 -> {defs_dst}")

    # 3) 技能
    skill_src = PACK / "skills" / "ramsey-construction-search" / "SKILL.md"
    skill_dst = home / "skills" / "installed" / "ramsey-construction-search"
    skill_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dst / "SKILL.md")
    print(f"[3/4] 已复制技能 -> {skill_dst}")

    # 4) 注册补丁
    status = patch_registry(registry)
    print(f"[4/4] registry.py: {status}")

    print("\n安装完成。自检：")
    print(f"  python -m moonshine --home {home} tools | findstr ramsey")
    return 0


if __name__ == "__main__":
    sys.exit(main())
