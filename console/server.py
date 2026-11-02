"""MARSA Agent 控制台 —— 在浏览器里启动、观察、中断一次自主研究运行。

为什么要有它
------------
命令行能跑，但"自主运行"这种长过程最需要的是**可观察性**：
它在第几轮？刚调了什么工具？结果是什么？有没有在打转？
这些在终端里是滚动日志，在控制台里是可见的状态。

它做什么
--------
1. **启动**一次自主研究运行（指定任务 / 轮数 / 项目名）
2. **实时流式**显示 agent 的输出（`[status]` / `[tool]` / `[tool-result]` 分类着色）
3. **中断**正在跑的运行
4. **回看**历次运行的日志
5. 顺带保留**确定性工具**面板（不经过 LLM，断网也能用）

用法：
    python console/server.py                # http://127.0.0.1:8777
    python console/server.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marsa.ops import ACTIONS, OPERATORS                 # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_HOME = Path("D:/myagent/moonshine-home")
AGENT_SLUG = "computational-construction-search"

MOONSHINE_HOME = DEFAULT_HOME

FRONTIER = {
    "R(5,5)": {
        "lower": 43, "upper": 46,
        "note": "下界 1989 年至今未改进；上界 46 由 Angeltveit & McKay (2024) 证明。",
        "open_targets": [44, 45],
        "why": ("R(5,5) >= 43 意味着存在 43 顶点的合法染色；删点保持合法性，"
                "故所有 n <= 43 都存在。真正开放的只有 n = 44 和 45。"),
        "check": "n = 46 上必然无解（与已证明上界一致），可作工具链自检。",
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


# ===========================================================================
#  运行管理
# ===========================================================================

class AgentRun:
    """一次自主研究运行的句柄。"""

    def __init__(self, run_id: str, project: str, task: str, iterations: int):
        self.run_id = run_id
        self.project = project
        self.task = task
        self.iterations = iterations
        self.lines: list[str] = []
        self.status = "starting"      # starting | running | done | stopped | error
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self.lines.append(line)

    def snapshot(self, start: int = 0) -> tuple[list[str], str]:
        with self._lock:
            return self.lines[start:], self.status

    def line_count(self) -> int:
        with self._lock:
            return len(self.lines)

    def stats(self) -> dict:
        """从输出里统计工具调用，用于面板上的实时指标。"""
        with self._lock:
            text = "\n".join(self.lines)
        tools = re.findall(r"^\[tool\]\s+(\S+)", text, re.M)
        rounds = len(re.findall(r"^\[status\]\s+Model round", text, re.M))
        iters = re.findall(r"iteration\s+(\d+)/(\d+)", text)
        counts: dict[str, int] = {}
        for t in tools:
            counts[t] = counts.get(t, 0) + 1
        return {
            "tool_calls": len(tools),
            "tool_counts": counts,
            "model_rounds": rounds,
            "iteration": (int(iters[-1][0]) if iters else 0),
            "iterations": self.iterations,
            "elapsed_seconds": round(
                (self.ended_at or time.time()) - self.started_at, 1),
        }


_runs: dict[str, AgentRun] = {}
_runs_lock = threading.Lock()


def _python_exe() -> str:
    for cand in (
        r"C:\Users\26319\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe",
        sys.executable,
    ):
        if Path(cand).exists():
            return cand
    return sys.executable


def start_run(task: str, iterations: int, project: str) -> AgentRun:
    run_id = uuid.uuid4().hex[:12]
    project = project.strip() or ("web_" + time.strftime("%m%d_%H%M"))
    run = AgentRun(run_id, project, task, iterations)

    cmd = [
        _python_exe(), "-u", "-m", "moonshine",
        "--home", str(MOONSHINE_HOME),
        "ask", "--mode", "research",
        "--project", project,
        "--agent", AGENT_SLUG,
        "--max-iterations", str(iterations),
        task,
    ]
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # 不依赖 pip 的 editable 安装（DSH 环境被重置过多次）：
    # 用 PYTHONPATH + _shims 目录联接保证 moonshine / marsa 永远可导入。
    base = str(ROOT)
    shim = str(ROOT / "_shims")
    existing = env.get("PYTHONPATH", "")
    parts = [base, shim] + [p for p in existing.split(os.pathsep) if p]
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(parts))

    def reader() -> None:
        try:
            run.proc = subprocess.Popen(
                cmd, cwd=str(ROOT), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            run.status = "running"
            assert run.proc.stdout is not None
            for line in run.proc.stdout:
                run.append(line.rstrip("\r\n"))
            run.proc.wait()
            if run.status != "stopped":
                run.status = "done" if run.proc.returncode == 0 else "error"
                if run.proc.returncode not in (0, None):
                    run.append(f"[控制台] 进程退出码 {run.proc.returncode}")
        except Exception as exc:                                # noqa: BLE001
            run.status = "error"
            run.append(f"[控制台] 启动失败: {type(exc).__name__}: {exc}")
        finally:
            run.ended_at = time.time()

    with _runs_lock:
        _runs[run_id] = run
    threading.Thread(target=reader, daemon=True).start()
    return run


def stop_run(run_id: str) -> bool:
    with _runs_lock:
        run = _runs.get(run_id)
    if not run or not run.proc or run.proc.poll() is not None:
        return False
    try:
        run.status = "stopped"
        run.proc.terminate()
        return True
    except Exception:                                          # noqa: BLE001
        return False


# ===========================================================================
#  历次运行 / 日志 / 目录
# ===========================================================================

def list_projects() -> list[dict]:
    pdir = MOONSHINE_HOME / "projects"
    if not pdir.exists():
        return []
    out = []
    for d in sorted(pdir.iterdir(), key=lambda p: p.stat().st_mtime,
                    reverse=True):
        if not d.is_dir():
            continue
        log = d / "memory" / "research_log.md"
        records = 0
        if log.exists():
            try:
                records = log.read_text(encoding="utf-8",
                                        errors="replace").count("\n## ")
            except OSError:
                pass
        out.append({
            "project": d.name,
            "records": records,
            "modified": time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(d.stat().st_mtime)),
            "has_log": log.exists(),
        })
    return out


def read_log(project: str) -> str:
    log = MOONSHINE_HOME / "projects" / project / "memory" / "research_log.md"
    if not log.exists():
        return f"(没有找到 {project} 的研究日志)"
    try:
        return log.read_text(encoding="utf-8", errors="replace")[-60000:]
    except OSError as exc:
        return f"(读取失败: {exc})"


def read_catalog() -> dict:
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


# ===========================================================================
#  HTTP
# ===========================================================================

class Handler(BaseHTTPRequestHandler):
    server_version = "MARSA-Console/0.3"

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

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(),
                       "text/html; charset=utf-8")
            return

        if path == "/api/state":
            with _lock:
                self._json({"frontier": FRONTIER, "catalog": read_catalog(),
                            "operators": list(OPERATORS),
                            "agent": AGENT_SLUG})
            return

        if path == "/api/agent/runs":
            self._json({"projects": list_projects()})
            return

        if path == "/api/agent/log":
            proj = (qs.get("project") or [""])[0]
            self._json({"project": proj, "log": read_log(proj)})
            return

        if path == "/api/agent/status":
            rid = (qs.get("run_id") or [""])[0]
            with _runs_lock:
                run = _runs.get(rid)
            if not run:
                self._json({"error": "unknown run_id"}, 404)
                return
            lines, status = run.snapshot(0)
            self._json({"status": status, "line_count": len(lines),
                        "stats": run.stats(), "project": run.project,
                        "task": run.task, "iterations": run.iterations})
            return

        if path == "/api/agent/stream":
            rid = (qs.get("run_id") or [""])[0]
            start = int((qs.get("from") or ["0"])[0] or 0)
            with _runs_lock:
                run = _runs.get(rid)
            if not run:
                self._json({"error": "unknown run_id"}, 404)
                return
            self._stream(run, start)
            return

        self._json({"error": "not found"}, 404)

    def _stream(self, run: AgentRun, start: int):
        """以 Server-Sent Events 推送新增输出行与实时指标。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        idx = start
        try:
            while True:
                chunk, status = run.snapshot(idx)
                for line in chunk:
                    payload = json.dumps({"type": "line", "text": line},
                                         ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    idx += 1
                st = json.dumps({"type": "stats", "status": status,
                                 **run.stats()}, ensure_ascii=False)
                self.wfile.write(f"data: {st}\n\n".encode("utf-8"))
                self.wfile.flush()
                if status in ("done", "error", "stopped") \
                        and idx >= run.line_count():
                    done = json.dumps({"type": "end", "status": status},
                                      ensure_ascii=False)
                    self.wfile.write(f"data: {done}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    return
                time.sleep(0.35)
        except (BrokenPipeError, ConnectionResetError):
            return

    # ---------- POST ----------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            self._json({"ok": False, "error": f"请求不是合法 JSON: {exc}"}, 400)
            return

        if path == "/api/agent/start":
            task = str(payload.get("task") or "").strip()
            if not task:
                self._json({"ok": False, "error": "任务描述不能为空"}, 400)
                return
            iters = max(1, min(int(payload.get("iterations") or 10), 60))
            project = str(payload.get("project") or "")
            run = start_run(task, iters, project)
            self._json({"ok": True, "run_id": run.run_id,
                        "project": run.project})
            return

        if path == "/api/agent/stop":
            self._json({"ok": stop_run(str(payload.get("run_id") or ""))})
            return

        if path == "/api/run":
            action = str(payload.pop("action", ""))
            fn = ACTIONS.get(action)
            if fn is None:
                self._json({"ok": False, "error": f"未知动作 {action}"}, 400)
                return
            try:
                with _lock:
                    result = fn(**payload)
            except TypeError as exc:
                result = {"ok": False, "error": f"参数不对: {exc}"}
            except Exception as exc:                            # noqa: BLE001
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            self._json(result)
            return

        self._json({"error": "not found"}, 404)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--home", default=str(DEFAULT_HOME))
    args = ap.parse_args()

    global MOONSHINE_HOME
    MOONSHINE_HOME = Path(args.home)

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"MARSA Agent 控制台：http://127.0.0.1:{args.port}")
    print(f"  Moonshine home : {MOONSHINE_HOME} "
          f"({'已找到' if MOONSHINE_HOME.exists() else '未找到'})")
    print(f"  agent 人格     : {AGENT_SLUG}")
    print("  按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
