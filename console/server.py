"""MARSA 控制台 —— 一个零依赖的本地 Web 前端。

为什么需要它
------------
命令行能跑，但演示和日常使用都不方便：要记一串参数、结果是裸 JSON、
想看"当前边界是什么、哪些族已排除"得翻日志。控制台把三件事放到一页：
**当前边界状态 / 一键跑实验 / 已装载能力**。

为什么不需要 API key
--------------------
它直接调用本项目的**确定性计算内核**（`marsa.ops`），完全不经过 LLM。
所以即使没有模型接口，它也是一个真正能用的工具——这恰好体现了本项目的分工。

计算逻辑与命令行共用 `marsa.ops`，避免两套行为。
只用 Python 标准库，无第三方依赖，绑定 127.0.0.1。

用法：
    python console/server.py                 # 默认 http://127.0.0.1:8777
    python console/server.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.ops import (                                       # noqa: E402
    ACTIONS, OPERATORS,
)

HERE = Path(__file__).resolve().parent
DEFAULT_HOME = Path("D:/myagent/moonshine-home")
MOONSHINE_HOME = DEFAULT_HOME

FRONTIER = {
    "R(5,5)": {
        "lower": 43, "upper": 46,
        "note": "下界 1989 年至今未改进；上界 46 由 Angeltveit & McKay (2024) 证明。",
        "open_targets": [44, 45],
        "why": ("R(5,5) ≥ 43 意味着存在 43 顶点的合法染色；删点保持合法性，"
                "故所有 n ≤ 43 都存在。真正开放的只有 n = 44 和 45。"),
        "check": "n = 46 上必然无解（与已证明的上界一致），可作工具链的自检。",
    },
    "R(4,6)": {
        "lower": 35, "upper": 41,
        "note": "缺口 6 格；下界历史上被搜索改进过。",
        "open_targets": [36],
        "why": "找到 36 顶点的 (4,6)-图即可把下界推到 36。",
        "check": "",
    },
}

_lock = threading.Lock()


def read_catalog() -> dict:
    """读 Moonshine 运行时目录，列出装进去的工具 / 技能 / 人格。"""
    home = MOONSHINE_HOME
    cat = {"home": str(home), "available": home.exists(),
           "tools": [], "skills": [], "agents": []}
    if not home.exists():
        return cat

    for f in sorted((home / "tools" / "definitions").glob("ramsey_*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"description"\s*:\s*"(.*?)"\s*,', text, re.S)
        cat["tools"].append({"name": f.stem,
                             "description": (m.group(1)[:200] if m else "")})
    for d in sorted((home / "skills" / "installed").iterdir()):
        sm = d / "SKILL.md"
        if not sm.exists():
            continue
        text = sm.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        cat["skills"].append({"name": d.name,
                              "description": (m.group(1).strip()[:220] if m else "")})
    for d in sorted((home / "agents" / "installed").iterdir()):
        am = d / "AGENT.md"
        if not am.exists():
            continue
        text = am.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"title"\s*:\s*"(.*?)"', text)
        cat["agents"].append({"name": d.name,
                              "title": (m.group(1) if m else d.name)})
    return cat


class Handler(BaseHTTPRequestHandler):
    server_version = "MARSA-Console/0.2"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code=200):
        self._send(code,
                   json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif self.path == "/api/state":
            with _lock:
                self._json({"frontier": FRONTIER, "catalog": read_catalog(),
                            "operators": list(OPERATORS)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            self._json({"ok": False, "error": f"请求不是合法 JSON: {exc}"}, 400)
            return
        action = str(payload.pop("action", ""))
        fn = ACTIONS.get(action)
        if fn is None:
            self._json({"ok": False, "error": f"未知动作 {action}"}, 400)
            return
        try:
            with _lock:                       # 串行，避免多次实验互相拖慢
                result = fn(**payload)
        except TypeError as exc:
            result = {"ok": False, "error": f"参数不对: {exc}"}
        except Exception as exc:                                   # noqa: BLE001
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        self._json(result)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--home", default=str(DEFAULT_HOME))
    args = ap.parse_args()

    global MOONSHINE_HOME
    MOONSHINE_HOME = Path(args.home)

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"MARSA 控制台已启动：http://127.0.0.1:{args.port}")
    print(f"  Moonshine home: {MOONSHINE_HOME} "
          f"({'已找到' if MOONSHINE_HOME.exists() else '未找到（目录面板会为空）'})")
    print("  按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
