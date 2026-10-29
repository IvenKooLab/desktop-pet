"""pet_config 单元测试：默认回落、往返、位置校验与坐标系标记。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pet_config


class PetConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_missing_file_returns_defaults(self):
        cfg = pet_config.load(self.tmp / "none.json")
        self.assertEqual(cfg["notifications"], "auto")
        self.assertTrue(cfg["remember_position"])
        self.assertIsNone(cfg["position"])

    def test_corrupt_file_returns_defaults(self):
        path = self.tmp / "config.json"
        path.write_text("{not json", encoding="utf-8")
        cfg = pet_config.load(path)
        self.assertEqual(cfg["notifications"], "auto")

    def test_round_trip(self):
        path = self.tmp / "config.json"
        cfg = {"notifications": "always", "update_check": "off",
               "remember_position": False,
               "position": {"x": 120, "y": 80, "cs": "topleft"},
               "unknown_field": "dropped"}
        self.assertTrue(pet_config.save(cfg, path))
        loaded = pet_config.load(path)
        self.assertEqual(loaded["notifications"], "always")
        self.assertEqual(loaded["update_check"], "off")
        self.assertFalse(loaded["remember_position"])
        self.assertEqual(loaded["position"], {"x": 120, "y": 80, "cs": "topleft"})
        self.assertNotIn("unknown_field", loaded)      # 未知字段不落盘

    def test_invalid_values_normalized(self):
        path = self.tmp / "config.json"
        path.write_text(json.dumps(
            {"notifications": "yolo", "update_check": "yolo",
             "remember_position": "yes",
             "position": {"x": 5, "y": 5, "cs": "middle"}}), encoding="utf-8")
        cfg = pet_config.load(path)
        self.assertEqual(cfg["notifications"], "auto")  # 非法回落默认
        self.assertEqual(cfg["update_check"], "auto")
        self.assertTrue(cfg["remember_position"])
        self.assertIsNone(cfg["position"])              # 未知坐标系丢弃

    def test_welcome_flag_defaults_false_and_round_trips(self):
        """首次启动的玩法提示只弹一次：welcomed 默认 false，写入后保持 true。"""
        path = self.tmp / "config.json"
        self.assertFalse(pet_config.load(path)["welcomed"])
        cfg = pet_config.load(path)
        cfg["welcomed"] = True
        self.assertTrue(pet_config.save(cfg, path))
        self.assertTrue(pet_config.load(path)["welcomed"])
        # 非法值回落默认，不会把"已提示"误判成已展示
        path.write_text('{"welcomed": "yes"}', encoding="utf-8")
        self.assertFalse(pet_config.load(path)["welcomed"])

    def test_valid_position_clamps_and_rejects(self):
        pos = pet_config.valid_position(
            {"x": 1850, "y": 400, "cs": "topleft"}, 1920, 1080, 200, "topleft")
        self.assertEqual(pos["x"], 1920 - 100)          # 部分出界夹回屏幕内
        self.assertIsNone(pet_config.valid_position(
            {"x": 5000, "y": 400, "cs": "topleft"}, 1920, 1080, 200, "topleft"))  # 完全离屏
        self.assertIsNone(pet_config.valid_position(
            {"x": 100, "y": 100, "cs": "bottomleft"}, 1920, 1080, 200, "topleft"))
        self.assertIsNone(pet_config.valid_position(
            {"x": -5000, "y": 400, "cs": "topleft"}, 1920, 1080, 200, "topleft"))
        self.assertIsNone(pet_config.valid_position(None, 1920, 1080, 200, "topleft"))


if __name__ == "__main__":
    unittest.main()
