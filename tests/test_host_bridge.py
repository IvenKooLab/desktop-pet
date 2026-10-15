"""host_bridge 归约器 + 收件箱消费的单元测试（重放 fixture 场景）。

场景对应维护文档 docs/BRIDGE.md 的验收清单：
开始→工具→等待确认→继续→本轮结束；工具失败；中断；并行会话；
断线回退；去重；过期清理；积压上限。
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from host_bridge import (HostBridge, Notice, write_event, EVENT_MAX_AGE,
                         MAX_BACKLOG)


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + ".000Z"


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.clock = FakeClock()
        self.bridge = HostBridge(directory=self.dir, clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def emit(self, kind, session="s1", label=None, **kw):
        kw.setdefault("timestamp", iso(self.clock()))
        path = write_event(self.dir, "test", kind, session_id=session,
                           task_label=label, **kw)
        self.assertIsNotNone(path, "write_event must succeed")
        return path

    def notices(self, kinds_only=True):
        out = self.bridge.poll()
        return [n.kind for n in out] if kinds_only else out

    # ---------- 归约主场景 ----------
    def test_full_working_session_lifecycle(self):
        """开始→工具×2→等待确认→继续→工具→本轮结束：Stop 不是成功。"""
        self.emit("session.started")
        self.emit("turn.started", label="运行测试")
        self.bridge.poll()
        self.assertEqual(self.bridge.mode, "working")
        self.assertEqual(self.bridge.label, "运行测试")

        self.emit("tool.started", tool_name="Bash")
        self.emit("tool.finished")
        self.emit("permission.required", tool_name="Bash")
        ns = self.notices()
        self.assertIn("permission.required", ns)
        self.assertEqual(self.bridge.mode, "waiting")

        self.clock.advance(2)                      # 用户在宿主里点了批准
        self.emit("tool.started")
        self.emit("tool.finished")
        self.bridge.poll()
        self.assertEqual(self.bridge.mode, "working")

        ns = self.notices()                        # 本轮结束
        self.emit("turn.ended")
        ns = self.notices()
        self.assertIn("turn.ended", ns)
        self.assertNotIn("task.completed", ns)     # 绝不把 Stop 当成功
        self.assertIsNone(self.bridge.mode)        # 回普通轮播

    def test_task_completed_only_from_explicit_event(self):
        self.emit("session.started")
        self.emit("turn.started")
        self.emit("task.completed", label="修复登录")
        ns = self.notices()
        self.assertIn("task.completed", ns)
        self.assertIsNone(self.bridge.mode)

    def test_turn_failed(self):
        self.emit("turn.started")
        self.emit("turn.failed", summary="boom")
        ns = self.notices()
        self.assertIn("turn.failed", ns)
        self.assertIsNone(self.bridge.mode)

    def test_tool_failed_keeps_working(self):
        """工具失败只是短暂闪现，宿主继续 → 仍 working。"""
        self.emit("turn.started")
        self.emit("tool.started")
        self.emit("tool.failed")
        ns = self.notices()
        self.assertIn("tool.failed", ns)
        self.assertEqual(self.bridge.mode, "working")

    def test_tool_finished_restores_working_after_permission(self):
        """审批通过后的第一个 tool.finished 把 waiting 拉回 working。"""
        self.emit("turn.started")
        self.emit("permission.required")
        self.notices()
        self.assertEqual(self.bridge.mode, "waiting")
        self.emit("tool.finished")
        self.notices()
        self.assertEqual(self.bridge.mode, "working")

    def test_quiet_session_decays_to_idle(self):
        """会话静默超 SESSION_QUIET：退 idle 回轮播，但仍在线（未断线清空）。"""
        from host_bridge import SESSION_QUIET
        self.emit("turn.started")
        self.notices()
        self.assertEqual(self.bridge.mode, "working")
        self.clock.advance(SESSION_QUIET + 1)
        self.notices()
        self.assertIsNone(self.bridge.mode)
        self.assertTrue(self.bridge.sessions, "session stays registered (still connected)")

    def test_parallel_sessions_grouped(self):
        """两个会话并行：一个结束不影响另一个的工作状态。"""
        self.emit("session.started", session="a")
        self.emit("session.started", session="b")
        self.emit("turn.started", session="a", label="A 任务")
        self.emit("turn.started", session="b")
        self.bridge.poll()
        self.assertEqual(self.bridge.mode, "working")
        self.emit("turn.ended", session="a")
        self.bridge.poll()
        self.assertEqual(self.bridge.mode, "working")   # b 还在干活
        self.emit("turn.ended", session="b")
        self.bridge.poll()
        self.assertIsNone(self.bridge.mode)

    def test_waiting_beats_working(self):
        self.emit("turn.started", session="a")
        self.emit("turn.started", session="b")
        self.emit("permission.required", session="b")
        self.bridge.poll()
        self.assertEqual(self.bridge.mode, "waiting")

    def test_interrupted_and_session_ended(self):
        self.emit("turn.started")
        self.bridge.poll()
        self.assertEqual(self.bridge.mode, "working")
        self.emit("interrupted")
        self.bridge.poll()
        self.assertIsNone(self.bridge.mode)
        self.emit("turn.started")
        self.bridge.poll()
        self.emit("session.ended")
        self.bridge.poll()
        self.assertIsNone(self.bridge.mode)

    # ---------- 韧性 ----------
    def test_disconnect_falls_back_silently(self):
        """断线回退：超过 stale 窗口无事件 → 清空会话、无通知。"""
        self.emit("turn.started")
        self.bridge.poll()
        self.assertEqual(self.bridge.mode, "working")
        self.clock.advance(121)
        ns = self.notices()
        self.assertEqual(ns, [])                    # 静默回退，不弹提醒
        self.assertIsNone(self.bridge.mode)

    def test_duplicate_event_ids_deduped(self):
        """适配器重发同一 event_id：只生效一次。"""
        ev = {"version": 1, "event_id": "dup-1", "source": "test",
              "session_id": "s1", "turn_id": None,
              "timestamp": iso(self.clock()), "kind": "task.completed",
              "task_label": None, "summary": None, "tool_name": None,
              "severity": "info"}
        seen = []
        for _ in range(3):
            (self.dir / "fixed.json").write_text(json.dumps(ev), "utf-8")
            seen += [n.kind for n in self.bridge.poll()]
        self.assertEqual(seen.count("task.completed"), 1)

    def test_stale_events_expired(self):
        """事件时间戳太老 → 作废删除，不产生状态。"""
        ev = {"version": 1, "event_id": "old-1", "source": "test",
              "session_id": "s1", "turn_id": None,
              "timestamp": iso(self.clock() - EVENT_MAX_AGE - 10),
              "kind": "turn.started", "task_label": None, "summary": None,
              "tool_name": None, "severity": "info"}
        (self.dir / "old.json").write_text(json.dumps(ev), "utf-8")
        ns = self.notices()
        self.assertEqual(ns, [])
        self.assertIsNone(self.bridge.mode)
        self.assertEqual(list(self.dir.glob("*.json")), [])   # 已清理

    def test_malformed_files_discarded(self):
        (self.dir / "bad.json").write_text("{not json", "utf-8")
        (self.dir / "wrongver.json").write_text(json.dumps(
            {"version": 99, "event_id": "x", "kind": "turn.started"}), "utf-8")
        self.notices()
        self.assertEqual(list(self.dir.glob("*.json")), [])
        self.assertIsNone(self.bridge.mode)

    def test_backlog_cap(self):
        """收件箱积压超限：最旧被丢弃，不无限消费。"""
        for i in range(MAX_BACKLOG + 60):
            ev = {"version": 1, "event_id": f"cap-{i}", "source": "test",
                  "session_id": "s1", "turn_id": None,
                  "timestamp": iso(self.clock()), "kind": "tool.finished",
                  "task_label": None, "summary": None, "tool_name": None,
                  "severity": "info"}
            (self.dir / f"{i:06d}-cap.json").write_text(json.dumps(ev), "utf-8")
        self.bridge.poll()
        remaining = len(list(self.dir.glob("*.json")))
        self.assertLessEqual(remaining, MAX_BACKLOG)

    def test_label_sanitized_and_truncated(self):
        self.emit("turn.started", label="A\x00B\nC" + "x" * 200)
        self.bridge.poll()
        self.assertEqual(self.bridge.label, "A B C" + "x" * 75)
        self.assertNotIn("\n", self.bridge.label)

    def test_disabled_bridge_polls_nothing(self):
        self.bridge.enabled = False
        self.emit("turn.started")
        ns = self.notices()
        self.assertEqual(ns, [])
        self.assertIsNone(self.bridge.mode)

    def test_empty_dir_is_quiet(self):
        self.assertEqual(self.notices(), [])
        self.assertIsNone(self.bridge.mode)


if __name__ == "__main__":
    unittest.main()
