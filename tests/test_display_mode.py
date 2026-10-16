import json
import tempfile
import unittest
from pathlib import Path

from display_mode import read_display_mode, write_display_mode


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
