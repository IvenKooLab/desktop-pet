import json
import tempfile
import unittest
from pathlib import Path

from display_mode import read_display_mode, display_claimed, write_display_mode


class DisplayModeTests(unittest.TestCase):
    def test_embedded_request_is_leased_and_expiry_returns_to_desktop(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "custom-events"
            self.assertEqual(read_display_mode(events, 100000), "desktop")
            self.assertTrue(write_display_mode(events, "embedded", 100000))
            payload = json.loads((Path(directory) / "display.json").read_text())
            self.assertNotIn("client_id", payload)
            self.assertEqual(payload["lease_until"], 130000)
            self.assertEqual(read_display_mode(events, 129999), "embedded")
            self.assertEqual(read_display_mode(events, 130000), "desktop")
            self.assertTrue(write_display_mode(events, "desktop", 100001))
            self.assertEqual(read_display_mode(events, 100002), "desktop")

    def test_short_confirm_window_lease(self):
        """桌宠端内嵌请求用 6 秒确认窗口租约（claim 前不隐藏的两段式协议）。"""
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events"
            self.assertTrue(write_display_mode(events, "embedded", 100000,
                                               lease_ms=6000))
            payload = json.loads((Path(directory) / "display.json").read_text())
            self.assertEqual(payload["lease_until"], 106000)
            self.assertEqual(read_display_mode(events, 105999), "embedded")
            self.assertEqual(read_display_mode(events, 106000), "desktop")
            # 非法/超上限的 lease_ms 落回默认 30 秒
            self.assertTrue(write_display_mode(events, "embedded", 100000,
                                               lease_ms=99999))
            payload = json.loads((Path(directory) / "display.json").read_text())
            self.assertEqual(payload["lease_until"], 130000)

    def test_claimed_requires_live_client_id(self):
        """隐藏条件：租约有效且 client_id 已写（有客户端真的接手）。"""
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events"
            path = Path(directory) / "display.json"
            self.assertTrue(write_display_mode(events, "embedded", 100000,
                                               lease_ms=6000))
            self.assertFalse(display_claimed(events, 101000),
                             "unclaimed request lease must not hide the pet")
            data = json.loads(path.read_text())
            data["client_id"] = "web-tab-1"
            path.write_text(json.dumps(data))
            self.assertTrue(display_claimed(events, 101000))
            data["client_id"] = ""
            path.write_text(json.dumps(data))
            self.assertFalse(display_claimed(events, 101000))
            data["client_id"] = "x" * 129
            path.write_text(json.dumps(data))
            self.assertFalse(display_claimed(events, 101000))
            self.assertFalse(display_claimed(events, 200000),
                             "expired lease is never claimed")

    def test_invalid_or_long_lease_never_hides_pet(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events"
            path = Path(directory) / "display.json"
            good = {"version": 1, "mode": "embedded", "owner": "dsh", "lease_until": 125000}
            for replacement in ({"owner": "unknown"}, {"lease_until": True},
                                {"lease_until": 135001}, {"lease_until": float("nan")},
                                {"lease_until": float("inf")}, {"version": 2}):
                path.write_text(json.dumps(dict(good, **replacement)))
                self.assertEqual(read_display_mode(events, 100000), "desktop")
            path.write_text("{" * 4096)
            self.assertEqual(read_display_mode(events, 100000), "desktop")
            path.write_text("[]")
            self.assertEqual(read_display_mode(events, 100000), "desktop")


if __name__ == "__main__":
    unittest.main()
