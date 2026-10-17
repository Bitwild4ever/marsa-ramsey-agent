"""端到端验证 ramsey_compare 工具在 Moonshine 注册表中的行为。"""
import json
import sys

sys.path.insert(0, r"D:\myagent\Moonshine-main\Moonshine-main")

from moonshine.moonshine_constants import MoonshinePaths          # noqa: E402
from moonshine.moonshine_cli.config import resolve_home           # noqa: E402
from moonshine.tools.registry import ToolRegistry                 # noqa: E402

reg = ToolRegistry(MoonshinePaths(resolve_home(r"D:\myagent\moonshine-home")))
runtime = {"mode": "research", "project_slug": "t"}

# 确认注册
names = [d.name for d in reg.list_definitions() if d.name.startswith("ramsey")]
print(f"注册的 ramsey 工具 ({len(names)}): {names}")
assert "ramsey_compare" in names, "compare 未注册"

r = reg.dispatch("ramsey_compare",
                 {"operators": ["tabu_focus", "tabu_violation"], "n": 44,
                  "s": 5, "t": 5, "budget": 4.0, "seeds": 3}, runtime)
print("\n返回 keys:", sorted(r.keys()))
print("\n完整返回（截断 800 字符）:")
print(json.dumps(r, ensure_ascii=False, indent=2, default=str)[:800])
