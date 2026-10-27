"""改名与兼容层测试：Comi 品牌一致性 + 旧数据/旧环境变量仍可用。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import comi_home  # noqa: E402


class BrandTests(unittest.TestCase):
    def test_no_stale_iven_branding_in_public_docs(self):
        """源码与公开文档只应在新旧对照/兼容说明里出现旧名，不能有残留的品牌文案。

        CHANGELOG.md 与 README 的"改名/升级"段落是有意保留的对照说明，因此只
        检查源码与 README 的常规文案；旧名允许出现在兼容路径（~/.iven-pet、
        IVEN_*、iven-bridge）的说明中。
        """
        for name in ("pet.py", "native/macos/ComiPet.swift", "docs/API.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("IvenPet", text, f"{name} 仍残留 IvenPet")
        # README 正文不该再把角色叫 Iven；"1.x 曾叫 Iven"这类改名说明允许保留
        for name in ("README.md", "README.en.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            text = text.replace("IvenKooLab", "").replace("ivenkoolab", "")
            for compat in ("~/.iven-pet", "IVEN_", "iven-bridge", "iven-v2",
                           "iven-pet", "IvenPet.app", "IvenPet.exe"):
                text = text.replace(compat, "")
            text = text.replace("她叫 Iven", "").replace("was called Iven", "")
            self.assertNotIn("Iven", text, f"{name} 仍残留旧角色名 Iven")
        # 更新日志允许对照，但必须已经写明新名字
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("Comi（可米）", changelog)

    def test_app_and_adapter_paths_renamed(self):
        self.assertTrue((ROOT / "native/macos/ComiPet.swift").is_file())
        self.assertFalse((ROOT / "native/macos/IvenPet.swift").exists())
        self.assertTrue((ROOT / "adapters/dsh/comi-bridge/index.js").is_file())
        self.assertTrue((ROOT / "assets/comi-v2/spritesheet.png").is_file())
        self.assertTrue((ROOT / "tools/comi_cli.py").is_file())

    def test_adapter_package_name_and_entry(self):
        spec = json.loads((ROOT / "adapters/dsh/comi-bridge/package.json").read_text())
        self.assertEqual(spec["name"], "comi-bridge")
        patch = (ROOT / "adapters/dsh/comi-bridge/cordis.patch.yml").read_text()
        self.assertIn("comi-bridge", patch)
        self.assertNotIn("iven-bridge", patch)

    def test_version_file_matches_release_notes(self):
        version = (ROOT / "VERSION").read_text().strip()
        self.assertTrue((ROOT / f"docs/releases/v{version}.md").is_file(),
                        f"缺少 docs/releases/v{version}.md（CI 会失败）")
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertIn(f"## [{version}]", changelog)


class CompatibilityTests(unittest.TestCase):
    def test_env_falls_back_to_legacy_names(self):
        for name, legacy in (("COMI_BRIDGE_DIR", "IVEN_BRIDGE_DIR"),
                             ("COMI_CHAT_DIR", "IVEN_CHAT_DIR"),
                             ("COMI_API_DIR", "IVEN_API_DIR")):
            with self.subTest(name=name):
                saved = {key: os.environ.pop(key, None) for key in (name, legacy)}
                try:
                    os.environ[legacy] = "/tmp/legacy-path"
                    self.assertEqual(comi_home.env(name), "/tmp/legacy-path")
                    os.environ[name] = "/tmp/new-path"
                    self.assertEqual(comi_home.env(name), "/tmp/new-path")
                finally:
                    for key in (name, legacy):
                        os.environ.pop(key, None)
                        if saved[key] is not None:
                            os.environ[key] = saved[key]

    def test_data_dir_prefers_existing_legacy_directory(self):
        """旧 ~/.iven-pet 存在时继续用它，老用户数据不丢。"""
        home = Path(tempfile.mkdtemp())
        saved_home = os.environ.get("HOME")
        saved_override = os.environ.pop("COMI_HOME", None)
        try:
            os.environ["HOME"] = str(home)
            (home / ".iven-pet").mkdir()
            self.assertEqual(comi_home.data_dir(), home / ".iven-pet")
            (home / ".comi-pet").mkdir()
            self.assertEqual(comi_home.data_dir(), home / ".comi-pet")
        finally:
            if saved_home is not None:
                os.environ["HOME"] = saved_home
            if saved_override is not None:
                os.environ["COMI_HOME"] = saved_override

    def test_comi_home_override_wins(self):
        saved = os.environ.get("COMI_HOME")
        try:
            os.environ["COMI_HOME"] = "/tmp/comi-override"
            self.assertEqual(comi_home.data_dir(), Path("/tmp/comi-override"))
        finally:
            os.environ.pop("COMI_HOME", None)
            if saved is not None:
                os.environ["COMI_HOME"] = saved


if __name__ == "__main__":
    unittest.main()
