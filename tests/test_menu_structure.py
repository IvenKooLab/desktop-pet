"""右键菜单结构测试：顶层保持精简，动作走分类子菜单（dsh-pet 风格）。

不启动 Tk（CI 无显示），改为静态解析 pet.py 的 _bind 与 Swift 的菜单源码，
断言"顶层项数有限 + 动作只在子菜单里"这一结构约束。
"""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from animation_assets import load_clips  # noqa: E402

TOP_LEVEL_LIMIT = 12        # 顶层菜单项上限（含分隔符与标题行）
GROUPS = ("动作", "陪伴", "语言", "关于与更新")


def pet_menu_source():
    tree = ast.parse((ROOT / "pet.py").read_text())
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "Pet")
    bind = next(node for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name == "_bind")
    return ast.get_source_segment((ROOT / "pet.py").read_text(), bind)


class TkMenuStructureTests(unittest.TestCase):
    def setUp(self):
        self.source = pet_menu_source()

    def test_top_level_stays_compact(self):
        # 顶层只允许 menu.add_* 出现在这些变量上（分类容器各自独立）
        top_calls = re.findall(r"^\s{8}menu\.add_(\w+)", self.source, re.M)
        # 顶层不含逐个动作：menu.add_command 只应出现在标题/说话/对话/睡觉/退出
        self.assertLessEqual(len(top_calls), TOP_LEVEL_LIMIT,
                             f"顶层菜单项过多：{len(top_calls)}")
        self.assertIn("cascade", top_calls)

    def test_actions_live_in_submenus(self):
        # 每个动作剪辑名都必须挂在子菜单变量上，而不是顶层 menu
        for state in ("THINKING", "STRETCH", "RUBIK", "YAWN", "CELEBRATE"):
            self.assertNotIn(f'menu.add_command(label=self._menu_text("{state}"',
                             self.source)
            self.assertNotIn(f'menu.add_command(label=title', self.source)

    def test_group_names_present(self):
        for group in GROUPS:
            self.assertIn(group, self.source, f"缺少分组：{group}")

    def test_empty_submenus_are_skipped(self):
        # 工作/生活分组按实际素材计数决定是否挂出，避免空子菜单
        self.assertIn("work_count", self.source)
        self.assertIn("life_count", self.source)


class SwiftMenuStructureTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "native/macos/ComiPet.swift").read_text()
        start = self.source.index("func contextMenu() -> NSMenu {")
        self.body = self.source[start:self.source.index("\n    }\n", start)]

    def test_sections_are_submenus(self):
        for builder in ("actionsSubmenu", "companionSubmenu", "aboutSubmenu"):
            self.assertIn(builder, self.body, f"缺少分组构建器：{builder}")

    def test_no_flat_action_list(self):
        self.assertNotIn('("苦思冥想","THINKING")', self.body,
                         "顶层菜单不应平铺动作列表")
        self.assertLessEqual(self.body.count("menu.addItem("), TOP_LEVEL_LIMIT,
                             "顶层 item 过多")


class MenuCoversClipTests(unittest.TestCase):
    def test_every_autoplay_action_is_reachable(self):
        clips = load_clips(ROOT / "frames3d")
        source = (ROOT / "pet.py").read_text()
        # 自动轮播里的动作（behaviors actions）都必须能在菜单分组里点到
        import json
        behaviors = json.loads((ROOT / "animation_behaviors.json").read_text())
        for state in behaviors["actions"]:
            self.assertIn(f'("{state}"', source,
                          f"菜单缺少可点播的动作：{state}")
            self.assertIn(state, clips, f"动作 {state} 没有对应素材")


if __name__ == "__main__":
    unittest.main()
