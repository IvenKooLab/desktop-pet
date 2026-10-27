"""OpenCode 适配器重放测试：本地 mock SSE 服务 → 收件箱统一事件。"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADAPTER = REPO / "adapters" / "opencode" / "comi_opencode.py"

EVENTS = [
    {"type": "session.status", "sessionID": "s1", "status": "busy"},
    {"type": "tool.execute.before", "sessionID": "s1", "toolCallID": "c1",
     "tool": "bash"},
    {"type": "permission.asked", "sessionID": "s1"},
    {"type": "session.error", "sessionID": "s2"},
]


class MockSSE(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/event"):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for ev in EVENTS:
            self.wfile.write(b"data: " + json.dumps(ev).encode() + b"\n\n")
            self.wfile.flush()
            time.sleep(0.15)
        time.sleep(10)          # 保持连接，等适配器收够退出

    def log_message(self, *a):
        pass


class OpencodeAdapterCase(unittest.TestCase):
    def test_sse_lifecycle(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockSSE)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env = dict(os.environ, COMI_BRIDGE_DIR=tmp)
                proc = subprocess.run(
                    [sys.executable, str(ADAPTER),
                     "--base", f"http://127.0.0.1:{port}",
                     "--max-events", "4", "--debug"],
                    capture_output=True, text=True, timeout=30, env=env)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                events = [json.loads(f.read_text(encoding="utf-8"))
                          for f in sorted(Path(tmp).glob("*.json"))]
                kinds = [e["kind"] for e in events]
                self.assertEqual(kinds, ["turn.started", "tool.started",
                                         "permission.required", "turn.failed"])
                self.assertEqual(events[1]["tool_call_id"], "c1")
                self.assertEqual(events[1]["tool_name"], "bash")
                self.assertEqual(events[3]["session_id"], "s2")
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
