"""改名兼容垫片测试：旧路径脚本（iven_*）必须与新版（comi_*）行为一致。

v2.0 把角色从 Iven 改名 Comi，脚本随之改名，但老用户的宿主配置
（ZCode hooks / Codex / OpenCode / 自定义脚本）仍指向旧路径——
垫片让这些配置在 git pull 之后立即恢复工作，无需手动改配置。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class LegacyShimCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, HOME=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, script, stdin_text=""):
        return subprocess.run(
            [sys.executable, str(script)],
            input=stdin_text, capture_output=True, text=True, timeout=20,
            env=self.env)

    def test_zcode_legacy_hook_writes_event(self):
        """旧路径 iven_hook.py 收到 ZCode Hook stdin → 收件箱出现统一事件。"""
        bridge = tempfile.mkdtemp()
        env = dict(self.env, COMI_BRIDGE_DIR=bridge)
        payload = json.dumps({"session_id": "shim-1", "hook_event_name": "UserPromptSubmit",
                              "prompt": "旧路径垫片自测"})
        proc = subprocess.run([sys.executable, str(REPO / "adapters/zcode/iven_hook.py")],
                              input=payload, capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        events = [json.loads(p.read_text(encoding="utf-8"))
                  for p in sorted(Path(bridge).glob("*.json"))]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "turn.started")
        self.assertEqual(events[0]["source"], "zcode")
        self.assertEqual(events[0]["session_id"], "shim-1")

    def test_opencode_and_codex_shims_delegate(self):
        """opencode/codex 适配器是长驻/连网进程，垫片只做静态委托校验。"""
        import ast
        for shim, target in (("adapters/opencode/iven_opencode.py", "comi_opencode.py"),
                             ("adapters/codex/iven_codex.py", "comi_codex.py")):
            source = (REPO / shim).read_text(encoding="utf-8")
            self.assertIn(f'with_name("{target}")', source, shim)
            self.assertTrue((REPO / shim).with_name(target).is_file(),
                            f"{target} 不存在，垫片会指向空")

    def test_cli_legacy_shim_state(self):
        """旧路径 iven_cli.py state 与 comi_cli.py 行为一致（读状态快照）。"""
        home = Path(self.tmp.name)
        (home / ".iven-pet").mkdir()
        (home / ".iven-pet" / "state.json").write_text(
            json.dumps({"version": 1, "state": "IDLE"}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(REPO / "tools/iven_cli.py"), "state"],
            capture_output=True, text=True, timeout=20, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('"IDLE"', proc.stdout)

    def test_shims_delegate_without_duplicating_modules(self):
        """垫片必须是纯委托：不得自带映射逻辑（防止新旧语义分叉）。"""
        for shim in ("adapters/zcode/iven_hook.py", "adapters/codex/iven_codex.py",
                     "adapters/opencode/iven_opencode.py", "tools/iven_cli.py"):
            source = (REPO / shim).read_text(encoding="utf-8")
            self.assertIn("runpy.run_path", source, shim)
            self.assertNotIn("EVENT_MAP", source, f"{shim} 不应自带映射表")


if __name__ == "__main__":
    unittest.main()
