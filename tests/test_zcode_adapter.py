"""ZCode Hook 适配器的重放测试：真实 stdin payload → 收件箱统一事件。

payload 字段取自官方 Hooks 文档（session_id / hook_event_name /
tool_name / prompt / last_assistant_message / is_interrupt）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "adapters" / "zcode" / "iven_hook.py"


def payload(event, **kw):
    base = {"session_id": "sess-42", "hook_event_name": event,
            "transcript_path": "/tmp/zcode-hook/transcript.jsonl",
            "cwd": "/workspace/demo"}
    base.update(kw)
    return json.dumps(base)


class ZcodeHookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, IVEN_BRIDGE_DIR=self.tmp.name)
        self.env.pop("IVEN_BRIDGE_SUMMARY", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin_text):
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=stdin_text, capture_output=True, text=True, timeout=15,
            env=self.env)
        return proc

    def inbox(self):
        files = sorted(Path(self.tmp.name).glob("*.json"))
        return [json.loads(f.read_text(encoding="utf-8")) for f in files]

    def test_event_mapping(self):
        cases = [
            (payload("SessionStart", source="startup"), "session.started"),
            (payload("UserPromptSubmit", prompt="跑一下测试"), "turn.started"),
            (payload("PreToolUse", tool_name="Bash", tool_use_id="t1"), "tool.started"),
            (payload("PermissionRequest", tool_name="Bash"), "permission.required"),
            (payload("PostToolUse", tool_name="Bash", tool_response={"ok": 1}), "tool.finished"),
            (payload("PostToolUseFailure", tool_name="Bash", error="boom"), "tool.failed"),
            (payload("Stop", last_assistant_message="done", stop_hook_active=False), "turn.ended"),
        ]
        for text, kind in cases:
            with self.subTest(kind=kind):
                for old in Path(self.tmp.name).glob("*.json"):
                    old.unlink()                       # subTest 间清空收件箱
                proc = self.run_hook(text + "\n")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout, "")            # stdout 留给宿主协议
                events = self.inbox()
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["kind"], kind)
                self.assertEqual(events[0]["source"], "zcode")
                self.assertEqual(events[0]["session_id"], "sess-42")
                self.assertEqual(events[0]["version"], 1)

    def test_interrupt_maps_to_interrupted(self):
        proc = self.run_hook(payload("PostToolUseFailure", error="user stop",
                                     is_interrupt=True))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.inbox()[0]["kind"], "interrupted")

    def test_default_state_only_no_texts(self):
        """默认只传状态：prompt / 回复摘要不出现在事件里。"""
        self.run_hook(payload("UserPromptSubmit", prompt="机密提示词"))
        self.run_hook(payload("Stop", last_assistant_message="机密回复"))
        for ev in self.inbox():
            self.assertIsNone(ev["task_label"])
            self.assertIsNone(ev["summary"])

    def test_summary_opt_in(self):
        self.env["IVEN_BRIDGE_SUMMARY"] = "1"
        self.run_hook(payload("UserPromptSubmit", prompt="修复登录页 " + "细" * 200))
        self.run_hook(payload("Stop", last_assistant_message="回复内容" + "长" * 300))
        events = self.inbox()
        label = next(e for e in events if e["kind"] == "turn.started")
        self.assertEqual(label["task_label"], "修复登录页 " + "细" * 74)
        stop = next(e for e in events if e["kind"] == "turn.ended")
        self.assertTrue(stop["summary"].startswith("回复内容"))
        self.assertLessEqual(len(stop["summary"]), 160)

    def test_unknown_event_ignored(self):
        proc = self.run_hook(payload("SomethingNew"))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.inbox(), [])

    def test_malformed_stdin_exits_clean(self):
        proc = self.run_hook("{not json")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.inbox(), [])
        proc = self.run_hook("")
        self.assertEqual(proc.returncode, 0)

    def test_control_chars_stripped_from_label(self):
        self.env["IVEN_BRIDGE_SUMMARY"] = "1"
        self.run_hook(payload("UserPromptSubmit",
                              prompt="A\x00B\nC\x1b[31m"))
        ev = self.inbox()[0]
        self.assertEqual(ev["task_label"], "A B C [31m")


if __name__ == "__main__":
    unittest.main()
