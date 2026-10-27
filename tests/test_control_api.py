"""control_api 单元测试：请求校验、回复往返、TTL 清理、状态快照。"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import control_api


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = 1_800_000_000.0

    def test_say_request_round_trip(self):
        rid = control_api.write_request(self.tmp, "say", text="你好 Comi",
                                        now=self.now, request_id="r1")
        self.assertEqual(rid, "r1")
        (path, obj), = control_api.poll_requests(self.tmp)
        spec = control_api.parse_request(obj)
        self.assertEqual(spec["action"], "say")
        self.assertEqual(spec["text"], "你好 Comi")

    def test_play_whitelist(self):
        ok = control_api.parse_request(
            {"version": 1, "id": "a", "action": "play", "state": "CHEER"},
            allowed_states={"CHEER", "WORK"})
        self.assertEqual(ok["state"], "CHEER")
        builtin = control_api.parse_request(
            {"version": 1, "id": "a", "action": "play", "state": "SLEEP"})
        self.assertEqual(builtin["state"], "SLEEP")
        bad = control_api.parse_request(
            {"version": 1, "id": "a", "action": "play", "state": "HACK"},
            allowed_states={"CHEER"})
        self.assertIsNone(bad)

    def test_invalid_requests_rejected(self):
        self.assertIsNone(control_api.parse_request({"version": 2, "id": "a", "action": "say", "text": "x"}))
        self.assertIsNone(control_api.parse_request({"version": 1, "id": "", "action": "say", "text": "x"}))
        self.assertIsNone(control_api.parse_request({"version": 1, "id": "a", "action": "rm -rf"}))
        self.assertIsNone(control_api.parse_request({"version": 1, "id": "a", "action": "say", "text": "   "}))
        self.assertIsNone(control_api.parse_request("not a dict"))
        # 控制字符替换为空格（与 host_chat 同口径），首尾清洗
        spec = control_api.parse_request(
            {"version": 1, "id": "a", "action": "say", "text": "hi\x00\x1f!\x7f"})
        self.assertEqual(spec["text"], "hi  !")


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_reply_consumed_on_read(self):
        control_api.write_reply(self.tmp, "r9", {"ok": True, "shown": True})
        reply = control_api.read_reply(self.tmp, "r9")
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["id"], "r9")
        self.assertEqual(reply["version"], 1)
        self.assertIsNone(control_api.read_reply(self.tmp, "r9"))

    def test_reply_id_mismatch_ignored(self):
        control_api.write_reply(self.tmp, "r9", {"ok": True})
        path = self.tmp / "reply-r9.json"
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj["id"] = "other"
        path.write_text(json.dumps(obj), encoding="utf-8")
        self.assertIsNone(control_api.read_reply(self.tmp, "r9"))


class CleanupTests(unittest.TestCase):
    def test_cleanup_removes_stale_files_only(self):
        tmp = Path(tempfile.mkdtemp())
        now = time.time()
        fresh_req = tmp / "request-keep.json"
        stale_req = tmp / "request-old.json"
        fresh_reply = tmp / "reply-keep.json"
        stale_reply = tmp / "reply-old.json"
        for p in (fresh_req, fresh_reply):
            p.write_text("{}", encoding="utf-8")
        for p, age in ((stale_req, 2000), (stale_reply, 400)):
            p.write_text("{}", encoding="utf-8")
            stamp = now - age
            import os
            os.utime(p, (stamp, stamp))
        removed = control_api.cleanup(tmp, now=now)
        self.assertEqual(removed, 2)
        self.assertTrue(fresh_req.exists())
        self.assertTrue(fresh_reply.exists())
        self.assertFalse(stale_req.exists())
        self.assertFalse(stale_reply.exists())


class StateTests(unittest.TestCase):
    def test_state_round_trip(self):
        tmp = Path(tempfile.mkdtemp()) / "state.json"
        snap = {"state": "WORK", "x": 100, "y": 200, "display": "desktop",
                "following": "dsh", "host_mode": "working",
                "updated": "2026-10-22T10:00:00+0800"}
        self.assertTrue(control_api.write_state(tmp, snap))
        loaded = control_api.read_state(tmp)
        self.assertEqual(loaded["state"], "WORK")
        self.assertEqual(loaded["version"], 1)

    def test_state_bad_file_returns_none(self):
        tmp = Path(tempfile.mkdtemp()) / "state.json"
        tmp.write_text("garbage", encoding="utf-8")
        self.assertIsNone(control_api.read_state(tmp))


if __name__ == "__main__":
    unittest.main()
