import ast
import json
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from animation_assets import load_clips, timed_frame
from animation_behaviors import load_behaviors, performance_ticks
from display_mode import read_display_mode, display_claimed, write_display_mode
import system_notify


class AnimationTests(unittest.TestCase):
    def test_autoplay_covers_actions_and_pause_keeps_idle(self):
        tree = ast.parse((ROOT / "pet.py").read_text())
        pet_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Pet")
        namespace = {"random": __import__("random"), "time": time,
                     "performance_ticks": performance_ticks, "PLAYBACK_SPEED": 0.75}
        exec(compile(ast.Module(body=[pet_class], type_ignores=[]), "pet.py", "exec"), namespace)
        pet = namespace["Pet"].__new__(namespace["Pet"])
        pet.clips = load_clips(ROOT / "frames3d")
        pet.behaviors = load_behaviors(ROOT)
        pet.autoplay, pet._action_deck, pet._last_auto_action = True, [], None
        cycle = []
        expected = {"GREET", "BOUNCE", "HAPPY", "SHY", "CHEER", "SPIN", "WAITING", "WORK", "REVIEW", "FAILED", "STRETCH", "DOZE", "RUBIK", "THINKING", "IMPATIENT", "RELIEVED", "WALK", "YAWN", "STOMP", "CELEBRATE", "SEARCH", "TRICK_OR_TREAT", "GHOST_SHEET", "VAMPIRE_CAPE", "WITCH_SPELL", "BLACK_CAT"}
        for _ in range(len(expected)):
            pet._next_auto_action()
            cycle.append(pet.state)
            self.assertGreater(pet.state_left, 0)
        self.assertEqual(set(cycle), expected)
        self.assertNotIn("TOKEN_LOW", cycle)
        pet.autoplay = False
        pet._next_auto_action()
        self.assertEqual(pet.state, "IDLE")
        pet.autoplay = True
        pet._next_auto_action()
        self.assertNotEqual(pet.state, cycle[-1])

    def make_pet(self, clock):
        tree = ast.parse((ROOT / "pet.py").read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Pet")
        namespace = {"time": clock, "random": __import__("random"), "PLAYBACK_SPEED": 0.75,
                     "performance_ticks": performance_ticks, "timed_frame": timed_frame,
                     "LANG": "en", "status_card": lambda *args: None,
                     "control_api": __import__("control_api"),
                     "throw_physics": __import__("throw_physics"),
                     "pet_config": __import__("pet_config"),
                     "system_notify": system_notify}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "pet.py", "exec"), namespace)
        pet = namespace["Pet"].__new__(namespace["Pet"])
        pet.clips, pet.behaviors = load_clips(ROOT / "frames3d"), load_behaviors(ROOT)
        pet.host, pet._bridge_on, pet._host_action, pet._host_dwell = None, True, False, False
        pet._host_hold, pet.tick_n, pet.drag_off = 0, 100, None
        pet._bubble_persistent, pet._bubble_deadline = False, 0
        pet._anim_key = None
        pet._waiting_since = pet._waiting_source = None
        pet.last_input = 0
        pet._api_cd = pet._state_cd = 10 ** 9     # 控制接口轮询在单测中关闭
        pet._update_pending = []                  # 更新检查在单测中不触发网络
        pet.config = {"notifications": "off"}
        pet._notify_limiter = system_notify.RateLimiter()
        pet._embedded_display = False
        return pet

    def test_long_performance_keeps_full_last_frame_at_75_percent(self):
        now = [100.0]
        clock = SimpleNamespace(monotonic=lambda: now[0])
        pet = self.make_pet(clock)
        pet._start_clip("STRETCH", 4)
        expected_seconds = sum(pet.clips["STRETCH"][1]) * 4 / 750
        self.assertAlmostEqual(pet._clip_deadline, 100 + expected_seconds)
        self.assertGreater(expected_seconds, 10)
        # The first visible frame starts immediately, before the next logic step.
        self.assertEqual(pet._frame_at(now[0], 0), pet.clips["STRETCH"][0][0])
        now[0] = pet._clip_deadline - 0.01
        pet.state_left = -5  # a late/catch-up logic step must not truncate the tail
        self.assertFalse(pet._clip_finished())
        self.assertEqual(pet._frame_at(now[0], 0), pet.clips["STRETCH"][0][-1])
        before = pet._anim_t0
        pet._play_clip("STRETCH", [], 1)
        self.assertEqual(pet._anim_t0, before)
        now[0] = pet._clip_deadline
        self.assertTrue(pet._clip_finished())

    def test_idle_bridge_does_not_cancel_autonomous_work_or_waiting(self):
        pet = self.make_pet(SimpleNamespace(monotonic=lambda: 100.0))
        pet.host = SimpleNamespace(mode=None)
        for state in ("WORK", "WAITING"):
            pet._start_clip(state, 4)
            deadline = pet._clip_deadline
            pet._host_assert()
            self.assertEqual(pet.state, state)
            self.assertEqual(pet._clip_deadline, deadline)
            self.assertFalse(pet._host_action)

    def test_real_host_preempts_autoplay_but_respects_sleep_drag_and_manual(self):
        pet = self.make_pet(SimpleNamespace(monotonic=lambda: 100.0))
        pet.host = SimpleNamespace(mode="working")
        pet._start_clip("RUBIK", 5)
        pet._host_assert()
        self.assertEqual(pet.state, "WORK")
        self.assertTrue(pet._host_action)
        # Real work remains a single loop, rather than the long automatic performance.
        self.assertAlmostEqual(pet._clip_deadline - pet._anim_t0,
                               sum(pet.clips["WORK"][1]) / 750)
        for state, drag, hold in (("SLEEP", None, 0), ("GRAB", (0, 0), 0),
                                  ("RUBIK", None, 101)):
            pet._set_state(state, 100)
            pet.drag_off, pet._host_hold = drag, hold
            pet._host_assert()
            self.assertEqual(pet.state, state)

    def test_behavior_validation_and_life_actions_are_longer(self):
        config = load_behaviors(ROOT)
        clips = load_clips(ROOT / "frames3d")
        for state in ("STRETCH", "DOZE", "RUBIK"):
            shortest = sum(clips[state][1]) * config["actions"][state][0] / 750
            self.assertGreater(shortest, 10)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "animation_behaviors.json").write_text(json.dumps({
                "version": 1, "idle_seconds": [9, 2], "walk_cycles": [True, 7],
                "actions": {"STRETCH": {"cycles": [0, 9999]},
                            "RUBIK": {"cycles": [2, 4]}, "SLEEP": {"cycles": [2, 4]},
                            "TOKEN_LOW": {"cycles": [2, 4]}}}))
            parsed = load_behaviors(directory)
            self.assertEqual(parsed["idle_seconds"], (3, 5))
            self.assertEqual(parsed["walk_cycles"], (5, 8))
            self.assertEqual(parsed["actions"]["STRETCH"], (4, 6))
            self.assertEqual(parsed["actions"]["RUBIK"], (2, 4))
            self.assertNotIn("SLEEP", parsed["actions"])
            self.assertNotIn("TOKEN_LOW", parsed["actions"])

    def test_themed_sequences_only_reference_original_approved_frames(self):
        manifest = json.loads((ROOT / "frames3d/animation.json").read_text())
        clips = manifest["clips"]
        # WORK 帧 = 已批准的打板（cheer）源帧；2026-10-23 起撒欢庆祝也复用它们
        original = {frame for state in ("IDLE", "REVIEW", "SPIN", "WAITING", "BOUNCE", "FAILED", "GREET", "WORK")
                    for frame in clips[state]["frames"]}
        # Execute the pure composer without importing the build-time Pillow dependency.
        tree = ast.parse((ROOT / "tools/export_comi_v2.py").read_text())
        composer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "themed_clips")
        namespace = {}
        exec(compile(ast.Module(body=[composer], type_ignores=[]), "export_comi_v2.py", "exec"), namespace)
        rebuilt = namespace["themed_clips"](clips)
        long_performances = ("THINKING", "IMPATIENT", "TOKEN_LOW", "RELIEVED")
        life_actions = ("YAWN", "STOMP", "CELEBRATE", "SEARCH")
        for state in long_performances + life_actions:
            clip = clips[state]
            self.assertEqual(clip, rebuilt[state])
            self.assertTrue(clip["reused_frames"])
            self.assertEqual((clip["frames"][0], clip["frames"][-1]), ("idle_0", "idle_0"))
            self.assertTrue(set(clip["frames"]).issubset(original))
            self.assertGreaterEqual(sum(clip["durations"]),
                                    6000 if state in long_performances else 3000)

    def test_life_performances_do_not_repeat_or_jump_gaze_directions(self):
        clips = json.loads((ROOT / "frames3d/animation.json").read_text())["clips"]
        bundled = load_behaviors(ROOT)
        with tempfile.TemporaryDirectory() as missing:
            fallback = load_behaviors(missing)
        for state in ("YAWN", "STOMP", "CELEBRATE", "SEARCH"):
            self.assertEqual(bundled["actions"][state], (1, 1))
            self.assertEqual(fallback["actions"][state], (1, 1))
            self.assertLessEqual(max(clips[state]["durations"]), 800)
        gaze = [int(frame.split("_")[1]) for frame in clips["SEARCH"]["frames"]
                if frame.startswith("look_")]
        # Neighbours on the 16-direction ring, including the 15 -> 0 seam.
        for before, after in zip(gaze, gaze[1:]):
            self.assertIn((after - before) % 16, (0, 1, 15))
        # Celebration may wave and jump, but must not cut into working poses.
        self.assertFalse(any(f.startswith("work_") for f in clips["CELEBRATE"]["frames"]))
        failed = [int(f.split("_")[1]) for f in clips["STOMP"]["frames"]
                  if f.startswith("failed_")]
        for before, after in zip(failed, failed[1:]):
            self.assertLessEqual(abs(after - before), 1)

    def test_waiting_becomes_impatient_after_30_seconds_and_resets_for_other_source(self):
        now = [100.0]
        pet = self.make_pet(SimpleNamespace(monotonic=lambda: now[0]))
        pet.host = SimpleNamespace(mode="waiting", source="dsh")
        pet._set_state("IDLE", 100)
        pet._host_assert()
        self.assertEqual(pet.state, "WAITING")
        now[0] = 129.999
        pet._host_assert()
        self.assertEqual(pet.state, "WAITING")
        now[0] = 130
        pet._host_assert()
        self.assertEqual(pet.state, "IMPATIENT")
        self.assertTrue(pet._host_action)
        pet.host.source = "zcode"
        pet._host_assert()
        self.assertEqual(pet.state, "WAITING")
        pet.host.mode = "working"
        pet._host_assert()
        self.assertEqual(pet.state, "WORK")
        self.assertIsNone(pet._waiting_since)

    def test_work_alternates_with_thinking_and_explicit_success_is_relieved(self):
        now = [100.0]
        pet = self.make_pet(SimpleNamespace(monotonic=lambda: now[0]))
        pet._logic_step.__globals__.update(SIZE=200, _BT={"done": "Task completed"})
        pet.x, pet.y, pet._plat_cd, pet._host_poll_cd = 100, 0, 100, 100
        pet._support = lambda: (0, 200, 1000)
        pet.host = SimpleNamespace(mode="working", source="dsh")
        pet._set_state("IDLE", 100)
        pet._host_assert()
        self.assertEqual(pet.state, "WORK")
        now[0] = pet._clip_deadline + 0.01
        pet._logic_step()
        self.assertEqual(pet.state, "THINKING")
        self.assertTrue(pet._host_dwell)
        now[0] = pet._clip_deadline + 0.01
        pet._logic_step()
        self.assertEqual(pet.state, "WORK")
        pet._start_clip("THINKING")
        pet._host_dwell = True
        pet.host.mode = None
        pet.say = lambda *args, **kwargs: None
        pet._host_notice(SimpleNamespace(kind="task.completed", label=None))
        pet._host_assert()
        self.assertEqual(pet.state, "RELIEVED")
        self.assertFalse(pet._host_dwell)

    def test_embedded_lease_hides_windows_but_keeps_host_poll_and_logic_alive(self):
        now, updates = [100.0], []
        pet = self.make_pet(SimpleNamespace(monotonic=lambda: now[0]))
        globals_ = pet._loop.__globals__
        globals_.update(LOGIC_DT=0.05 / 0.75, RENDER_MS=16,
                        read_display_mode=lambda events: read_display_mode(events, now[0] * 1000),
                        display_claimed=lambda events: display_claimed(events, now[0] * 1000))
        pet.root = SimpleNamespace(withdraw=lambda: updates.append("hide"),
                                   deiconify=lambda: updates.append("show"),
                                   after=lambda *args: updates.append("scheduled"))
        pet._follow_badge = None
        pet._hide_bubble = lambda: updates.append("hide bubble")
        pet._render = lambda at: None
        pet._logic_step = pet._host_poll
        pet._logic_next, pet._display_poll_at, pet._embedded_display = now[0], 0, False
        pet._embedded_requested_at = None
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events"
            path = Path(directory) / "display.json"
            pet.host = SimpleNamespace(dir=events, poll=lambda: updates.append("poll") or [])
            # 两段式租约第一阶段：请求未 claim —— 不能隐藏（没人接手不玩失踪）
            write_display_mode(events, "embedded", now[0] * 1000, lease_ms=6000)
            pet._loop()
            self.assertFalse(pet._embedded_display)
            self.assertNotIn("hide", updates)
            # 第二阶段：网页客户端 claim（写 client_id）—— 隐藏，逻辑照常活着
            data = json.loads(path.read_text())
            data["client_id"] = "web-tab-1"
            path.write_text(json.dumps(data))
            now[0] += 0.3
            pet._loop()
            self.assertTrue(pet._embedded_display)
            self.assertIn("hide", updates)
            self.assertIn("poll", updates)
            self.assertIn("scheduled", updates)
            # 租约到期（claim 后无人续租）：回桌面
            now[0] = 130.001
            pet._loop()
            self.assertFalse(pet._embedded_display)
            self.assertIn("show", updates)
            self.assertGreater(updates.count("poll"), 1)

    def test_timeline_boundaries_and_wrap(self):
        names,durations = ("a","b","c"),(280,110,320)
        expected = [(0,"a"),(279,"a"),(280,"b"),(389,"b"),
                    (390,"c"),(709,"c"),(710,"a"),(990,"b")]
        for elapsed,name in expected:
            self.assertEqual(timed_frame(names,durations,elapsed),name)

    def test_partial_custom_manifest_rejects_missing_frames_and_bad_times(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            self.assertEqual(load_clips(folder),{})
            (folder/"idle_0.gif").write_bytes(b"fixture")
            manifest={"version":1,"clips":{
                "IDLE":{"frames":["idle_0"],"durations":[280]},
                "MISSING":{"frames":["idle_1"],"durations":[100]},
                "ZERO":{"frames":["idle_0"],"durations":[0]},
                "BOOL":{"frames":["idle_0"],"durations":[True]},
                "MISMATCH":{"frames":["idle_0"],"durations":[100,100]},
                "ESCAPE":{"frames":["../idle_0"],"durations":[100]}}}
            (folder/"animation.json").write_text(json.dumps(manifest))
            self.assertEqual(set(load_clips(folder)),{"IDLE"})

    def test_default_has_complete_clips(self):
        default=load_clips(ROOT/"frames3d")
        self.assertEqual(len(default["IDLE"][0]),6)
        self.assertEqual(len(default["WALK_r"][0]),8)
        self.assertEqual(len(default["SPIN"][0]),16)
        for names,_ in default.values():
            for name in names:
                self.assertTrue((ROOT/"frames3d"/(name+".gif")).is_file())
                self.assertTrue((ROOT/"frames3d"/(name+".png")).is_file())

    def test_pet_clip_player_and_legacy_fallback(self):
        # Load actual Pet methods without starting Tk or binding its single-instance port.
        tree=ast.parse((ROOT/"pet.py").read_text())
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=="Pet")
        namespace={"time":time,"timed_frame":timed_frame,"PLAYBACK_SPEED":0.75}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),"pet.py","exec"),namespace)
        pet=namespace["Pet"].__new__(namespace["Pet"])
        pet.clips={"IDLE":(("idle_0","idle_1"),(280,110))}
        pet._anim_key=None
        pet._play_clip("IDLE",["legacy"],1000)
        start=pet._anim_t0
        self.assertEqual(pet._frame_at(start+.300,0),"idle_0")
        self.assertEqual(pet._frame_at(start+.400,0),"idle_1")
        pet._play_clip("IDLE",["legacy"],1000)
        self.assertEqual(pet._anim_t0,start)  # repeated logic ticks cannot reset phase
        pet._play_clip("GRAB",["grab_0","grab_1"],200)
        self.assertEqual(pet._anim_key,("seq",("grab_0","grab_1"),200))


if __name__=="__main__":
    unittest.main()
