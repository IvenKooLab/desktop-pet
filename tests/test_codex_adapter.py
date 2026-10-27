"""Codex 适配器重放测试：mock app-server → 收件箱统一事件。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADAPTER = REPO / "adapters" / "codex" / "comi_codex.py"
MOCK = REPO / "tests" / "fixtures" / "mock_codex_server.py"


class CodexAdapterCase(unittest.TestCase):
    def test_mock_server_lifecycle(self):
        """握手 → turn/started → completed(本轮结束≠成功) → failed → approval。"""
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, COMI_BRIDGE_DIR=tmp)
            proc = subprocess.Popen(
                [sys.executable, str(ADAPTER),
                 "--server-cmd", f"{sys.executable} {MOCK}", "--debug"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, env=env)
            deadline = time.time() + 10
            events = []
            while time.time() < deadline:
                time.sleep(0.3)
                events = [json.loads(f.read_text(encoding="utf-8"))
                          for f in sorted(Path(tmp).glob("*.json"))]
                if len(events) >= 4:
                    break
            proc.terminate()
            proc.wait(timeout=5)
            kinds = [e["kind"] for e in events]
            self.assertEqual(kinds, ["turn.started", "turn.ended",
                                     "turn.failed", "permission.required"])
            for ev in events:
                self.assertEqual(ev["source"], "codex")
                self.assertEqual(ev["version"], 1)
            self.assertEqual(events[0]["session_id"], "thread-mock-1")
            self.assertEqual(events[2]["session_id"], "thread-mock-2")


if __name__ == "__main__":
    unittest.main()
