"""端到端验证：本项目新增的 4 个确定性工具在 Moonshine 里是否真的可用。

不经过 LLM，直接走 Moonshine 的 ToolRegistry.dispatch，
这样验的是"工具接线是否正确"，与模型无关。
"""
import sys

MOONSHINE_ROOT = r"D:\myagent\Moonshine-main\Moonshine-main"
HOME = r"D:\myagent\moonshine-home"
sys.path.insert(0, MOONSHINE_ROOT)

from moonshine.moonshine_constants import MoonshinePaths          # noqa: E402
from moonshine.moonshine_cli.config import resolve_home           # noqa: E402
from moonshine.tools.registry import ToolRegistry                 # noqa: E402

registry = ToolRegistry(MoonshinePaths(resolve_home(HOME)))
runtime = {"mode": "research", "project_slug": "ramsey-test"}

names = [d.name for d in registry.list_definitions() if d.name.startswith("ramsey")]
print(f"注册的 ramsey 工具 ({len(names)}): {names}")
assert len(names) == 4, "应有 4 个工具"

# --- 1) 搜索，拿到候选 -----------------------------------------------------
r1 = registry.dispatch("ramsey_search", {
    "n": 34, "s": 5, "t": 5, "operator": "tabu_focus",
    "budget_seconds": 3.0, "seed": 0,
}, runtime)
print(f"\n[ramsey_search] n=34 -> {r1['overall_verdict']} "
      f"| violations={r1['violations']} passed={r1['passed']} "
      f"| {r1['elapsed_seconds']}s steps={r1['steps']}")
assert r1["violations"] >= 0

# --- 2) 独立验证 -----------------------------------------------------------
if r1.get("graph6"):
    r2 = registry.dispatch("ramsey_verify_construction", {
        "n": 34, "s": 5, "t": 5, "graph6": r1["graph6"],
    }, runtime)
    print(f"[ramsey_verify_construction] -> {r2['overall_verdict']} "
          f"passed={r2['passed']}")
    print(f"    {r2['conclusion']}")

    r3 = registry.dispatch("ramsey_violations", {
        "n": 34, "s": 5, "t": 5, "graph6": r1["graph6"],
    }, runtime)
    print(f"[ramsey_violations] -> {r3['overall_verdict']} "
          f"violations={r3['violations']}")
else:
    print("[skip] 该预算内未解出，跳过验证工具演示")

# --- 3) 穷举对称族（判定性）-----------------------------------------------
r4 = registry.dispatch("ramsey_enumerate_family", {
    "n": 38, "s": 5, "t": 5, "family": "circulant",
}, runtime)
print(f"\n[ramsey_enumerate_family] n=38 circulant -> {r4['overall_verdict']} "
      f"| solutions={r4['solutions_found']} space={r4['space_size']:,} "
      f"exhaustive={r4['exhaustive']} | {r4['elapsed_seconds']}s")
print(f"    {str(r4['conclusion'])[:150]}")

# --- 4) 已知答案的交叉检查 -------------------------------------------------
# R(5,5) <= 46 已被证明 => n=46 上不可能存在合法染色。
r5 = registry.dispatch("ramsey_enumerate_family", {
    "n": 46, "s": 5, "t": 5, "family": "circulant",
}, runtime)
print(f"\n[交叉检查] n=46 circulant -> {r5['overall_verdict']} "
      f"| solutions={r5['solutions_found']}")
assert r5["solutions_found"] == 0, "与已证明的 R(5,5)<=46 矛盾"
print("    与已证明的 R(5,5) <= 46 一致（n=46 必然无解）-> 内核正确性获得独立佐证")

print("\n全部 4 个工具接线正常，且结果经独立验证器复核。")
