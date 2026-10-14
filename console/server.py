"""MARSA 控制台 —— 一个零依赖的本地 Web 前端。

为什么需要它
------------
命令行能跑，但演示和日常使用都不方便：
- 要记一串参数（n / s / t / operator / budget / seed）
- 结果是一个大 JSON，读起来费劲
- 想看"当前边界是什么、哪些族已排除"得翻日志

这个控制台把三件事放到一个页面上：**当前边界状态 / 一键跑实验 / 结果与目录**。

为什么不需要 API key
--------------------
它直接调用本项目的**确定性计算内核**（marsa），完全不经过 LLM。
所以即使没有模型接口，它也是一个真正能用的工具——
这恰好体现了本项目的分工：需要计算的事交给计算，不需要模型。

只用 Python 标准库，无第三方依赖。绑定 127.0.0.1。

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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.bitset import Coloring                       # noqa: E402
from marsa.search import SAConfig, TabuConfig, run_operator   # noqa: E402
from marsa.symmetric import (                           # noqa: E402
    FastChecker, circulant_red, circulant_size,
)
from marsa.verifier import parse_graph6, to_graph6, verify   # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_HOME = Path("D:/myagent/moonshine-home")
MOONSHINE_HOME = DEFAULT_HOME

# 已知边界（写死为知识，不是计算出来的）
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

_OPERATORS = ("sa", "tabu", "tabu_focus", "tabu_sample", "tabu_violation")
_lock = threading.Lock()


# --------------------------------------------------------------------------
# 计算动作（全部确定性，不调用 LLM）
# --------------------------------------------------------------------------

def act_search(n, s=5, t=5, operator="tabu_focus", budget=5.0, seed=0):
    n, s, t = int(n), int(s), int(t)
    op = str(operator)
    if op not in _OPERATORS:
        return {"ok": False, "error": f"未知算子 {op}"}
    budget = max(0.1, min(float(budget), 120.0))
    if op == "sa":
        cfg = SAConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                       seed=int(seed), report_every=0, keep_elites=0)
    else:
        cfg = TabuConfig(n=n, s=s, t=t, steps=10 ** 9, max_seconds=budget,
                         seed=int(seed), report_every=0, keep_elites=0)
    t0 = time.perf_counter()
    res = run_operator(op, cfg)
    dt = time.perf_counter() - t0

    out = {
        "ok": True, "action": "search", "n": n, "s": s, "t": t,
        "operator": op, "seed": int(seed), "budget": budget,
        "seconds": round(dt, 2), "steps": int(res.steps_done),
        "init_violations": int(res.init_cost),
        "violations": int(res.best_cost),
        "graph6": None, "verified": None,
    }
    if res.best_cost == 0:
        good, witness = verify(n, res.best_red, s, t)
        out["verified"] = bool(good)
        out["graph6"] = to_graph6(n, res.best_red) if n <= 62 else None
        out["witness"] = list(witness) if witness else None
        out["status"] = "solved" if good else "verification_failed"
        out["conclusion"] = (
            f"已解出且经独立验证：R({s},{t}) > {n}。" if good
            else "搜索自称成功，但独立验证器否决 —— 该结果不可信。"
        )
    else:
        out["status"] = "unsolved"
        out["conclusion"] = (
            f"该预算内未解出，当前违反度 {res.best_cost}。"
            f"这只是「努力不够」，不是「不存在」的证据。"
        )
    return out


def act_enumerate(n, s=5, t=5):
    n, s, t = int(n), int(s), int(t)
    k = circulant_size(n)
    total = 1 << k
    if total > 40_000_000:
        return {"ok": False, "error": f"空间过大（2^{k} = {total:,}），不适合穷举"}
    checker = FastChecker(n, s, t)
    t0 = time.perf_counter()
    found = [b for b in range(total) if checker.is_valid(b)]
    dt = time.perf_counter() - t0
    out = {
        "ok": True, "action": "enumerate", "n": n, "s": s, "t": t,
        "family": "circulant", "free_parameters": k, "space": total,
        "solutions": len(found), "seconds": round(dt, 2), "exhaustive": True,
        "graph6": None, "connection_set": None, "verified": None,
    }
    if found:
        bits = found[0]
        red = circulant_red(n, bits)
        good, _w = verify(n, red, s, t)
        out["verified"] = bool(good)
        out["graph6"] = to_graph6(n, red)
        out["connection_set"] = sorted(
            d for d in range(1, n // 2 + 1) if bits >> (d - 1) & 1)
        out["status"] = "exists"
        out["conclusion"] = (
            f"判定：循环图族在 n={n} 上有 {len(found)} 个合法染色"
            f"（全空间 {total:,} 已查完）⇒ R({s},{t}) > {n}。"
        )
    else:
        out["status"] = "none_exist"
        out["conclusion"] = (
            f"判定性否定：循环图族在 n={n} 上**无**合法染色"
            f"（全空间 {total:,} 已查完）。这个族被排除，不是「没搜到」。"
        )
    return out


def act_verify(n, s=5, t=5, graph6=""):
    n, s, t = int(n), int(s), int(t)
    try:
        n2, red = parse_graph6(str(graph6).strip())
    except Exception as exc:                               # noqa: BLE001
        return {"ok": False, "error": f"graph6 解析失败: {exc}"}
    if n2 != n:
        return {"ok": False, "error": f"graph6 是 n={n2}，与给出的 n={n} 不一致"}
    good, witness = verify(n, red, s, t)
    cost = Coloring(n, s, t, red).cost()
    return {
        "ok": True, "action": "verify", "n": n, "s": s, "t": t,
        "violations": int(cost), "verified": bool(good),
        "witness": list(witness) if witness else None,
        "status": "verified" if good else "refuted",
        "conclusion": (
            f"验证通过：这是一份合法 ({s},{t})-染色 ⇒ R({s},{t}) > {n}。" if good
            else f"验证否决：该图含单色团 {list(witness) if witness else ''}，"
                 f"不能证明任何下界。"
        ),
    }


ACTIONS = {"search": act_search, "enumerate": act_enumerate,
           "verify": act_verify}


# --------------------------------------------------------------------------
# 目录（可选读 Moonshine home）
# --------------------------------------------------------------------------

def read_catalog() -> dict:
    """读 Moonshine 运行时目录，列出我们装进去的工具/技能/人格。"""
    home = MOONSHINE_HOME
    cat = {"home": str(home), "available": home.exists(),
           "tools": [], "skills": [], "agents": []}
    if not home.exists():
        return cat

    for f in sorted((home / "tools" / "definitions").glob("ramsey_*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"description"\s*:\s*"(.*?)"\s*,', text, re.S)
        cat["tools"].append({
            "name": f.stem,
            "description": (m.group(1)[:200] if m else ""),
        })
    for d in sorted((home / "skills" / "installed").iterdir()):
        sm = d / "SKILL.md"
        if not sm.exists():
            continue
        text = sm.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        cat["skills"].append({
            "name": d.name,
            "description": (m.group(1).strip()[:220] if m else ""),
        })
    for d in sorted((home / "agents" / "installed").iterdir()):
        am = d / "AGENT.md"
        if not am.exists():
            continue
        text = am.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"title"\s*:\s*"(.*?)"', text)
        cat["agents"].append({
            "name": d.name,
            "title": (m.group(1) if m else d.name),
        })
    return cat


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "MARSA-Console/0.2"

    def log_message(self, fmt, *args):                     # 静音
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code=200):
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = (HERE / "index.html").read_bytes()
            self._send(200, page, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            with _lock:
                self._json({"frontier": FRONTIER, "catalog": read_catalog(),
                            "operators": list(_OPERATORS)})
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
            with _lock:                                    # 串行，避免互相拖慢
                result = fn(**payload)
        except TypeError as exc:
            result = {"ok": False, "error": f"参数不对: {exc}"}
        except Exception as exc:                           # noqa: BLE001
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
    url = f"http://127.0.0.1:{args.port}"
    print(f"MARSA 控制台已启动：{url}")
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
