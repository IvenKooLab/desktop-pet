#!/usr/bin/env python3
"""Codex App Server → Iven 桌宠桥接适配器（stdio JSON-RPC 客户端）。

本机已验证：codex-cli 0.162.1，spawn `codex app-server` 后 initialize /
initialized / thread/list 握手与推送均正常（行分隔 JSON，通知带 emittedAtMs）。
桌面实例的 ~/.codex/ipc/ipc.sock 对本握手无响应，属内部 IPC——**不读它冒充
实时集成**。因此本适配器监听的是自己驱动的 app-server 实例的会话
（"仅支持本客户端会话"）；驱动接口（turn/start）属第二阶段，此处不实现。

用法：
    python3 adapters/codex/iven_codex.py            # 常驻：握手后转发事件
    python3 adapters/codex/iven_codex.py --list     # 只做握手 + 线程列表（诊断/验收）
    python3 adapters/codex/iven_codex.py --server-cmd "python3 mock.py"  # 测试替身

事件映射（宽容提取，未实机确认的字段按当期 schema 核验）：
    turn/started                          → turn.started
    turn/completed(completed/interrupted/failed) → turn.ended / interrupted / turn.failed
    方法名含 approval（asked/requested）    → permission.required
"""
import json
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from host_bridge import write_event, default_dir  # noqa: E402


def map_notification(method, params):
    """app-server 通知 → (kind, fields)；不认识的返回 None。"""
    params = params if isinstance(params, dict) else {}
    sid = (params.get("threadId") or params.get("sessionId")
           or params.get("conversationId") or "unknown")
    lower = method.lower()
    if method == "turn/started":
        return "turn.started", {"session_id": sid}
    if method == "turn/completed":
        status = str(params.get("status") or params.get("outcome")
                     or "completed").lower()
        kind = {"interrupted": "interrupted",
                "failed": "turn.failed", "error": "turn.failed"}.get(
                    status, "turn.ended")     # completed 只是本轮结束≠成功
        return kind, {"session_id": sid}
    if "approval" in lower and any(w in lower for w in
                                   ("ask", "request", "pending")):
        return "permission.required", {"session_id": sid}
    return None


class CodexBridge:
    def __init__(self, server_cmd, events_dir, debug=False):
        self.server_cmd = server_cmd
        self.events_dir = events_dir
        self.debug = debug
        self.proc = None
        self.next_id = 1

    def log(self, *msg):
        if self.debug:
            print("[iven-codex]", *msg, file=sys.stderr)

    def start(self):
        argv = shlex.split(self.server_cmd)
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def request(self, method, params=None):
        rid = self.next_id
        self.next_id += 1
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": rid, "method": method,
             "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        return rid

    def handshake(self):
        init_id = self.request("initialize", {
            "protocolVersion": 1, "capabilities": {},
            "clientInfo": {"name": "iven-bridge", "version": "0.1.0"}})
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "method": "initialized"}) + "\n")
        self.proc.stdin.flush()
        return init_id

    def serve(self, list_only=False):
        self.start()
        self.handshake()
        list_id = self.request("thread/list", {})   # 只读发现：顺带验证连接
        running = True

        def stop(*_):
            nonlocal running
            running = False
            try:
                self.proc.kill()      # 关掉子进程让 stdout 管道 EOF，解除阻塞
            except OSError:
                pass
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        while running:
            line = self.proc.stdout.readline()
            if not line:
                self.log("app-server exited")
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            method = msg.get("method")
            if method is None:
                if msg.get("id") == list_id:
                    data = (msg.get("result") or {}).get("data") or []
                    self.log(f"connected, {len(data)} threads visible")
                    if list_only:
                        for t in data[:10]:
                            print(f"  {t.get('id')}  "
                                  f"{str(t.get('preview'))[:60]}")
                        break
                continue
            mapped = map_notification(method, msg.get("params"))
            if mapped:
                kind, fields = mapped
                write_event(self.events_dir, "codex", kind, **fields)
                self.log("→", kind, fields.get("session_id"))
        try:
            self.proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return 0


def main():
    args = sys.argv[1:]
    list_only = "--list" in args
    server_cmd = "codex app-server"
    for i, a in enumerate(args):
        if a == "--server-cmd" and i + 1 < len(args):
            server_cmd = args[i + 1]
    debug = "--debug" in args
    bridge = CodexBridge(server_cmd, default_dir(), debug)
    return bridge.serve(list_only=list_only)


if __name__ == "__main__":
    sys.exit(main())
