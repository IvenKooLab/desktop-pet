"""右键菜单结构测试：顶层保持精简，动作走分类子菜单（dsh-pet 风格）。

不启动 Tk（CI 无显示），改为静态解析 pet.py 的 _bind 与 Swift 的菜单源码，
断言"顶层项数有限 + 动作只在子菜单里"这一结构约束。
"""
import ast
from collections import defaultdict
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from animation_assets import load_clips  # noqa: E402

TOP_LEVEL_LIMIT = 12        # 顶层菜单项上限（含分隔符与标题行）
GROUPS = ("动作", "陪伴", "语言", "关于与更新")
HALLOWEEN = ("TRICK_OR_TREAT", "GHOST_SHEET", "VAMPIRE_CAPE", "WITCH_SPELL", "BLACK_CAT")


def pet_menu_source():
    tree = ast.parse((ROOT / "pet.py").read_text())
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "Pet")
    bind = next(node for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name == "_bind")
    return ast.get_source_segment((ROOT / "pet.py").read_text(), bind)


def build_tk_actions(clips, language):
    """Execute the production action-menu block with a minimal non-GUI Menu."""
    class Menu:
        def __init__(self, *_args, **_kwargs):
            self.items = []

        def add_command(self, **kwargs):
            self.items.append(kwargs)

        def add_cascade(self, **kwargs):
            self.items.append(kwargs)

        def add_separator(self):
            self.items.append({"separator": True})

    tree = ast.parse((ROOT / "pet.py").read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Pet")
    bind = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_bind")
    start = next(index for index, node in enumerate(bind.body)
                 if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "actions" for t in node.targets))
    end = next(index for index, node in enumerate(bind.body[start:], start)
               if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and any(keyword.arg == "menu" and isinstance(keyword.value, ast.Name) and keyword.value.id == "actions"
                       for keyword in node.value.keywords))
    played = []
    pet = SimpleNamespace(clips=clips, frames={}, _menu_text=lambda zh, en: zh if language == "zh" else en,
                          _menu_clip=played.append, _to_sleep=lambda: None)
    scope = {"self": pet, "tk": SimpleNamespace(Menu=Menu), "menu": Menu(),
             "_T": defaultdict(str), "LANG": language}
    exec(compile(ast.Module(body=bind.body[start:end+1], type_ignores=[]), "pet.py", "exec"), scope)
    return scope["actions"], played


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

    def test_holidays_contain_actions_directly_and_playback(self):
        for language in ("zh", "en"):
            with self.subTest(language=language):
                actions, played = build_tk_actions({name: True for name in HALLOWEEN}, language)
                holidays_label = "节日" if language == "zh" else "Holidays"
                holidays = next(item["menu"] for item in actions.items if item.get("label") == holidays_label)
                self.assertEqual(len(holidays.items), len(HALLOWEEN))
                self.assertTrue(all("menu" not in item for item in holidays.items))
                for item in holidays.items:
                    item["command"]()
                self.assertEqual(played, list(HALLOWEEN))

    def test_holidays_are_hidden_when_no_seasonal_clips_exist(self):
        actions, _ = build_tk_actions({"STRETCH": True}, "zh")
        self.assertFalse(any(item.get("label") == "节日" for item in actions.items))
        life = next(item["menu"] for item in actions.items if item.get("label") == "生活小动作")
        self.assertEqual([item["label"] for item in life.items], ["伸懒腰"])


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

    def test_holidays_direct_actions_match_tk(self):
        start = self.source.index("private func actionsSubmenu()")
        actions = self.source[start:self.source.index("return actions", start)]
        life = actions[actions.index("let life = NSMenu()"):actions.index("let holidays = NSMenu()")]
        holidays = actions[actions.index("let holidays = NSMenu()") :]
        for state in HALLOWEEN:
            self.assertNotIn(f'"{state}"', life)
            self.assertIn(f'"{state}"', holidays)
        for connection in ("holidays.addItem(clipItem(title, action))", "holidaysItem.submenu = holidays",
                           "actions.addItem(holidaysItem)"):
            self.assertIn(connection, holidays)
        self.assertNotIn("let halloween = NSMenu()", holidays)
        self.assertIn('"节日":"Holidays"', self.source)


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
