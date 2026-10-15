"""Claude Code / Cursor Hook 适配器重放测试（真实 stdin payload 形态）。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADAPTERS = {
    "claude-code": REPO / "adapters" / "claude-code" / "claude_hook.py",
    "cursor": REPO / "adapters" / "cursor" / "cursor_hook.py",
}


class HostHookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # HOME 隔离：summary 开关文件等本机状态不得影响测试
        self.env = dict(os.environ, IVEN_BRIDGE_DIR=self.tmp.name,
                        HOME=self.tmp.name)
        self.env.pop("IVEN_BRIDGE_SUMMARY", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, host, stdin_text):
        proc = subprocess.run([sys.executable, str(ADAPTERS[host])],
                              input=stdin_text, capture_output=True,
                              text=True, timeout=15, env=self.env)
        return proc

    def inbox(self):
        return [json.loads(f.read_text(encoding="utf-8"))
                for f in sorted(Path(self.tmp.name).glob("*.json"))]

    # ---------- Claude Code ----------
    def test_claude_event_mapping(self):
        cases = [
            ({"session_id": "c1", "hook_event_name": "SessionStart"},
             "session.started"),
            ({"session_id": "c1", "hook_event_name": "UserPromptSubmit",
              "prompt": "跑测试"}, "turn.started"),
            ({"session_id": "c1", "hook_event_name": "PreToolUse",
              "tool_name": "Bash", "tool_use_id": "tu-9"}, "tool.started"),
            ({"session_id": "c1", "hook_event_name": "PermissionRequest",
              "tool_name": "Bash"}, "permission.required"),
            ({"session_id": "c1", "hook_event_name": "Notification",
              "message": "needs permission"}, "permission.required"),
            ({"session_id": "c1", "hook_event_name": "PostToolUse",
              "tool_name": "Bash"}, "tool.finished"),
            ({"session_id": "c1", "hook_event_name": "PostToolUseFailure",
              "error": "boom"}, "tool.failed"),
            ({"session_id": "c1", "hook_event_name": "Stop",
              "last_assistant_message": "done"}, "turn.ended"),
            ({"session_id": "c1", "hook_event_name": "SessionEnd"},
             "session.ended"),
        ]
        for payload, kind in cases:
            with self.subTest(kind=kind):
                for old in Path(self.tmp.name).glob("*.json"):
                    old.unlink()                   # subTest 间清空收件箱
                proc = self.run_hook("claude-code",
                                     json.dumps(payload) + "\n")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout, "")
                events = self.inbox()
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["kind"], kind)
                self.assertEqual(events[0]["source"], "claude-code")

    def test_claude_tool_call_id_forwarded(self):
        self.run_hook("claude-code", json.dumps(
            {"session_id": "c1", "hook_event_name": "PreToolUse",
             "tool_name": "Write", "tool_use_id": "toolu_01ABC"}) + "\n")
        ev = self.inbox()[0]
        self.assertEqual(ev["tool_call_id"], "toolu_01ABC")
        self.assertEqual(ev["tool_name"], "Write")

    # ---------- Cursor ----------
    def test_cursor_event_mapping(self):
        cases = [
            ({"sessionId": "u1", "hookEventName": "sessionStart"},
             "session.started"),
            ({"sessionId": "u1", "hookEventName": "beforeSubmitPrompt",
              "prompt": "改下样式"}, "turn.started"),
            ({"sessionId": "u1", "hookEventName": "preToolUse",
              "toolName": "terminal", "toolCallId": "tc-1"}, "tool.started"),
            ({"sessionId": "u1", "hookEventName": "postToolUse",
              "toolName": "terminal"}, "tool.finished"),
            ({"sessionId": "u1", "hookEventName": "postToolUseFailure",
              "error": "x"}, "tool.failed"),
            ({"sessionId": "u1", "hookEventName": "afterAgentResponse",
              "response": "改好了"}, "turn.ended"),
            ({"sessionId": "u1", "hookEventName": "stop",
              "status": "completed"}, "turn.ended"),
            ({"sessionId": "u1", "hookEventName": "stop",
              "status": "aborted"}, "interrupted"),
            ({"sessionId": "u1", "hookEventName": "stop",
              "status": "error"}, "turn.failed"),
            ({"sessionId": "u1", "hookEventName": "sessionEnd"},
             "session.ended"),
        ]
        for payload, kind in cases:
            with self.subTest(kind=kind):
                for old in Path(self.tmp.name).glob("*.json"):
                    old.unlink()                   # subTest 间清空收件箱
                proc = self.run_hook("cursor", json.dumps(payload) + "\n")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                events = self.inbox()
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["kind"], kind)
                self.assertEqual(events[0]["source"], "cursor")

    def test_stop_completed_is_not_task_success(self):
        """Cursor stop=completed 也只是本轮结束，不产生 task.completed。"""
        self.run_hook("cursor", json.dumps(
            {"sessionId": "u1", "hookEventName": "stop",
             "status": "completed"}) + "\n")
        self.assertEqual(self.inbox()[0]["kind"], "turn.ended")

    def test_summary_opt_in_and_thoughts_never_forwarded(self):
        """摘要开关开启后标签/回复摘要可用；内部推理（thought）永不转发。"""
        self.env["IVEN_BRIDGE_SUMMARY"] = "1"
        self.run_hook("cursor", json.dumps(
            {"sessionId": "u1", "hookEventName": "beforeSubmitPrompt",
             "prompt": "写个登录页"}) + "\n")
        self.run_hook("cursor", json.dumps(
            {"sessionId": "u1", "hookEventName": "afterAgentResponse",
             "response": "完成了"}) + "\n")
        events = {e["kind"]: e for e in self.inbox()}
        self.assertEqual(events["turn.started"]["task_label"], "写个登录页")
        self.assertEqual(events["turn.ended"]["summary"], "完成了")

    def test_default_state_only(self):
        self.run_hook("claude-code", json.dumps(
            {"session_id": "c1", "hook_event_name": "UserPromptSubmit",
             "prompt": "机密"}) + "\n")
        self.run_hook("cursor", json.dumps(
            {"sessionId": "u1", "hookEventName": "afterAgentResponse",
             "response": "机密回复"}) + "\n")
        for ev in self.inbox():
            self.assertIsNone(ev["task_label"])
            self.assertIsNone(ev["summary"])

    def test_unknown_events_ignored(self):
        for host, payload in (("claude-code", {"hook_event_name": "Future"}),
                              ("cursor", {"hookEventName": "future"})):
            with self.subTest(host=host):
                proc = self.run_hook(host, json.dumps(payload))
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(self.inbox(), [])


if __name__ == "__main__":
    unittest.main()
