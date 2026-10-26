"""update_check 单元测试：版本解析/比较、跳转 tag 解析、失败静默与注入。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_check


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(update_check.parse_version("v1.0.1"), (1, 0, 1))
        self.assertEqual(update_check.parse_version("1.0.10"), (1, 0, 10))
        self.assertEqual(update_check.parse_version(" 2 "), (2,))
        for bad in ("", "v", "abc", "1..2", "1.0-beta", None, 3):
            self.assertIsNone(update_check.parse_version(bad), bad)

    def test_compare(self):
        cases = [
            ("1.0.2", "1.0.1", True),
            ("v1.0.1", "1.0.1", False),
            ("1.0.10", "1.0.9", True),      # 数字比较，不是字符串
            ("1.1", "1.0.9", True),
            ("1.0", "1.0.0", False),        # 缺失段补零
            ("0.9", "1.0", False),
            ("bad", "1.0", False),          # 非法宁可不说
        ]
        for latest, current, expected in cases:
            self.assertEqual(update_check.is_newer(latest, current), expected,
                             f"{latest} vs {current}")

    def test_tag_parse(self):
        self.assertEqual(update_check.parse_tag(
            "https://github.com/IvenKooLab/desktop-pet/releases/tag/v1.0.1"), "1.0.1")
        self.assertEqual(update_check.parse_tag(
            "https://github.com/IvenKooLab/desktop-pet/releases/tag/1.2.3"), "1.2.3")
        self.assertIsNone(update_check.parse_tag(
            "https://github.com/IvenKooLab/desktop-pet/releases"))
        self.assertIsNone(update_check.parse_tag(None))


class FetchTests(unittest.TestCase):
    def test_success(self):
        seen = []

        def fetch(url, timeout):
            seen.append((url, timeout))
            return ("https://github.com/IvenKooLab/desktop-pet/"
                    "releases/tag/v1.2.3")
        self.assertEqual(update_check.latest_release(fetch=fetch, timeout=3),
                         ("1.2.3", update_check.RELEASES_URL))
        self.assertEqual(seen[0][0], update_check.RELEASES_URL)

    def test_network_failure_is_silent(self):
        def fetch(url, timeout):
            raise OSError("offline")
        self.assertIsNone(update_check.latest_release(fetch=fetch))

    def test_malformed_redirect_is_silent(self):
        def fetch(url, timeout):
            return "https://github.com/IvenKooLab/desktop-pet/releases"
        self.assertIsNone(update_check.latest_release(fetch=fetch))

    def test_download_url(self):
        self.assertEqual(update_check.download_url(), update_check.RELEASES_URL)


class CurrentVersionTests(unittest.TestCase):
    def test_reads_version_file(self):
        directory = Path(tempfile.mkdtemp())
        (directory / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        self.assertEqual(update_check.current_version(directory), "1.0.1")

    def test_missing_or_invalid_returns_none(self):
        directory = Path(tempfile.mkdtemp())
        self.assertIsNone(update_check.current_version(directory))
        (directory / "VERSION").write_text("not-a-version", encoding="utf-8")
        self.assertIsNone(update_check.current_version(directory))


if __name__ == "__main__":
    unittest.main()
