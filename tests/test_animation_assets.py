import ast
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from animation_assets import load_clips, timed_frame


class AnimationTests(unittest.TestCase):
    def test_autoplay_covers_actions_and_pause_keeps_idle(self):
        tree = ast.parse((ROOT / "pet.py").read_text())
        pet_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Pet")
        namespace = {"random": __import__("random")}
        exec(compile(ast.Module(body=[pet_class], type_ignores=[]), "pet.py", "exec"), namespace)
        pet = namespace["Pet"].__new__(namespace["Pet"])
        pet.clips = load_clips(ROOT / "frames3d")
        pet.autoplay, pet._action_deck, pet._last_auto_action = True, [], None
        cycle = []
        for _ in range(12):
            pet._next_auto_action()
            cycle.append(pet.state)
            self.assertGreater(pet.state_left, 0)
        self.assertEqual(set(cycle), {"GREET", "BOUNCE", "CHEER", "SPIN", "WAITING", "WORK", "REVIEW", "FAILED", "STRETCH", "DOZE", "RUBIK", "WALK"})
        pet.autoplay = False
        pet._next_auto_action()
        self.assertEqual(pet.state, "IDLE")
        pet.autoplay = True
        pet._next_auto_action()
        self.assertNotEqual(pet.state, cycle[-1])

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
