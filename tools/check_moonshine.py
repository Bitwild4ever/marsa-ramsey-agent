"""检查 Moonshine 依赖与可运行性。"""
import importlib.util as u
import sys

print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
print("\n依赖可用性：")
for m in ("tiktoken", "lancedb", "chromadb", "langgraph",
          "requests", "httpx", "yaml", "numpy", "pandas"):
    print(f"  {m:<12} {'OK' if u.find_spec(m) else '--'}")

print("\nMoonshine 核心模块能否导入（不依赖第三方包的部分）：")
import os
root = r"D:\myagent\moonshine-main\Moonshine-main"
sys.path.insert(0, root)
sys.path.insert(0, os.path.dirname(root))  # 让 `import moonshine.*` 形式可用
for mod in ("config", "defaults", "moonshine_state", "json_schema",
            "markdown_metadata", "model_tools", "structured_tasks"):
    try:
        __import__(mod)
        print(f"  {mod:<20} OK")
    except Exception as exc:                      # noqa: BLE001
        print(f"  {mod:<20} 失败: {type(exc).__name__}: {exc}")
