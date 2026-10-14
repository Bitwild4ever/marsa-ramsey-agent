"""验证 4 份技能能被 Moonshine 正常发现与加载（走 agent 真实使用的工具路径）。

只用确定性的 SkillManager + ToolRegistry，不需要任何模型接口。
"""
import sys

MOONSHINE_ROOT = r"D:\myagent\Moonshine-main\Moonshine-main"
HOME = r"D:\myagent\moonshine-home"
sys.path.insert(0, MOONSHINE_ROOT)

from moonshine.moonshine_constants import MoonshinePaths          # noqa: E402
from moonshine.moonshine_cli.config import resolve_home           # noqa: E402
from moonshine.skills.manager import SkillManager                 # noqa: E402
from moonshine.tools.registry import ToolRegistry                 # noqa: E402

paths = MoonshinePaths(resolve_home(HOME))
manager = SkillManager(paths)
registry = ToolRegistry(paths)
runtime = {"mode": "research", "project_slug": "ramsey-test",
           "paths": paths, "skill_manager": manager}

EXPECTED = [
    "ramsey-construction-search",
    "symmetric-family-exhaustion",
    "search-operator-iteration",
    "ramsey-frontier-bookkeeping",
]

all_ok = True

# 1) 目录发现 —— build_prompt_index 返回的是**一个字符串**（模型可见的技能目录），
#    不是列表。所以要在字符串里检索，而不是遍历它。
index_text = manager.build_prompt_index(limit=256)
index_lower = index_text.lower()
print(f"模型可见的技能目录：{len(index_text)} 字符")
for name in EXPECTED:
    pos = index_lower.find(name)
    mark = "OK " if pos >= 0 else "!! "
    print(f"  {mark}{name}" + (f"  (位置 {pos})" if pos >= 0 else "  —— 不在目录里"))
    if pos < 0:
        all_ok = False

# 2) 通过工具逐个加载（agent 的真实加载路径）
print("\n通过 load_skill_definition 逐个加载：")
for slug in EXPECTED:
    try:
        res = registry.dispatch("load_skill_definition", {"slug": slug}, runtime)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  !! {slug}: {type(exc).__name__}: {exc}")
        all_ok = False
        continue
    body = ""
    for key in ("definition", "content", "body", "markdown", "text"):
        value = res.get(key)
        if isinstance(value, str) and value:
            body = value
            break
    if not body:
        body = str(res)
    sections = [s for s in ("Usage Hint", "Execution Steps", "Tool Calls",
                            "Output Contract", "Notes") if s in body]
    print(f"  OK {slug:<32} 正文 {len(body):>5} 字符 | 含章节 {sections}")
    if len(sections) < 4:
        all_ok = False

print()
print("结论：" + ("4 份技能全部可被发现并加载，结构完整。"
                 if all_ok else "存在未通过项，见上。"))
sys.exit(0 if all_ok else 1)
