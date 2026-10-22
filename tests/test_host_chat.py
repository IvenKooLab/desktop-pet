"""host_chat 对话文件协议测试：请求/回复往返、清洗、串号丢弃、过期清理。"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import host_chat


class HostChatCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_with_mood(self):
        req_id = host_chat.write_request(self.dir, "  在吗\x1b[31m ")
        self.assertTrue(req_id.startswith("pet-"))
        raw = json.loads((self.dir / f"request-{req_id}.json").read_text())
        self.assertEqual(raw["version"], 1)
        self.assertEqual(raw["text"], "在吗 [31m")           # 控制字符已清洗为空格
        (self.dir / f"reply-{req_id}.json").write_text(json.dumps(
            {"version": 1, "id": req_id, "ok": True,
             "text": "在的呀\n[表情:happy]", "mood": "happy"}), encoding="utf-8")
        reply = host_chat.read_reply(self.dir, req_id)
        self.assertEqual(reply["ok"], True)
        self.assertEqual(reply["mood"], "happy")
        self.assertEqual(reply["text"], "在的呀\n[表情:happy]")  # 保留换行，控制字符清洗
        self.assertFalse((self.dir / f"reply-{req_id}.json").exists(),
                         "回复读取后即消费删除")

    def test_text_truncated_to_limit(self):
        req_id = host_chat.write_request(self.dir, "长" * 3000)
        raw = json.loads((self.dir / f"request-{req_id}.json").read_text())
        self.assertEqual(len(raw["text"]), host_chat.MAX_TEXT)

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):
            host_chat.write_request(self.dir, "   \n  ")

    def test_missing_or_foreign_reply_is_none(self):
        req_id = host_chat.write_request(self.dir, "在吗")
        self.assertIsNone(host_chat.read_reply(self.dir, req_id))
        (self.dir / f"reply-{req_id}.json").write_text(json.dumps(
            {"version": 1, "id": "other", "ok": True, "text": "x"}))
        self.assertIsNone(host_chat.read_reply(self.dir, req_id))

    def test_malformed_reply_discarded(self):
        req_id = host_chat.write_request(self.dir, "在吗")
        (self.dir / f"reply-{req_id}.json").write_text("{not json")
        self.assertIsNone(host_chat.read_reply(self.dir, req_id))
        self.assertIsNone(host_chat.read_reply(self.dir, None))

    def test_cleanup_ttls(self):
        now = time.time()
        old_req = host_chat.write_request(self.dir, "旧的")
        os.utime(self.dir / f"request-{old_req}.json", (now - 1000, now - 1000))
        old_reply = self.dir / "reply-old.json"
        old_reply.write_text("{}")
        os.utime(old_reply, (now - 400, now - 400))
        fresh_reply = self.dir / "reply-fresh.json"
        fresh_reply.write_text("{}")
        host_chat.cleanup(self.dir, now=now)
        self.assertFalse((self.dir / f"request-{old_req}.json").exists())
        self.assertFalse(old_reply.exists())
        self.assertTrue(fresh_reply.exists())


if __name__ == "__main__":
    unittest.main()
