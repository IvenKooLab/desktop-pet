"""system_notify 单元测试：门控矩阵、限流、文本口径（不发真实通知）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import system_notify


class GateTests(unittest.TestCase):
    def test_matrix(self):
        cases = [
            # (kind, hidden, mode) -> expected
            ("permission.required", True, "auto", True),
            ("permission.required", False, "auto", False),
            ("turn.failed", True, "auto", True),
            ("task.completed", True, "auto", True),
            ("turn.ended", True, "auto", False),        # 非一次性任务事件
            ("tool.started", True, "always", False),    # 不在通知白名单
            ("task.completed", False, "always", True),
            ("task.completed", True, "off", False),
            ("task.completed", False, "off", False),
        ]
        for kind, hidden, mode, expected in cases:
            self.assertEqual(system_notify.gate(kind, hidden, mode), expected,
                             f"{kind} hidden={hidden} mode={mode}")

    def test_rate_limiter(self):
        limiter = system_notify.RateLimiter(min_interval=8.0)
        self.assertTrue(limiter.allow(100.0))
        self.assertFalse(limiter.allow(100.5))
        self.assertFalse(limiter.allow(107.9))
        self.assertTrue(limiter.allow(108.0))


class TextTests(unittest.TestCase):
    def test_notify_text_covers_kinds_with_label(self):
        self.assertEqual(system_notify.notify_text("permission.required", "运行测试"),
                         "等你确认权限：运行测试")
        self.assertIn("Task completed", system_notify.notify_text(
            "task.completed", None, zh=False))
        self.assertEqual(system_notify.notify_text("turn.failed", None), "出问题了")

    def test_label_truncated(self):
        text = system_notify.notify_text("task.completed", "标" * 300)
        self.assertLessEqual(len(text), 80 + 10)


class SendTests(unittest.TestCase):
    def test_send_dispatches_and_never_raises(self):
        sent = []

        def fake(title, body, platform=None, hwnd=None):
            sent.append((title, body, platform))
            return True

        original = system_notify.send
        system_notify.send = fake
        try:
            self.assertTrue(system_notify.send("Iven", "hi", platform="darwin"))
        finally:
            system_notify.send = original
        self.assertEqual(sent, [("Iven", "hi", "darwin")])

    def test_unknown_platform_returns_false(self):
        self.assertFalse(system_notify.send("t", "b", platform="plan9"))


if __name__ == "__main__":
    unittest.main()
