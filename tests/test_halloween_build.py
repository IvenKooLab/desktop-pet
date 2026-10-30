"""Regression checks for staged artwork export, not claims of visual approval."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Pillow is a build-time dependency: pip install -r requirements-dev.txt")
class HalloweenBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import build_halloween_actions
        cls.builder = build_halloween_actions

    def fixture(self, directory):
        root = Path(directory)
        atlas = Image.new("RGBA", (80, 40))
        draw = ImageDraw.Draw(atlas)
        draw.rectangle((14, 10, 25, 29), fill="#aa77cc")
        draw.rectangle((54, 6, 65, 25), fill="#aa77cc")
        atlas.save(root / "sheet.png")
        config = {"version": 1, "actions": [{"name": "TEST", "source": "sheet.png",
                  "source_sha256": hashlib.sha256((root / "sheet.png").read_bytes()).hexdigest(),
                  "scale": 2, "expected_frames": 2,
                  "cells": [{"box": [0, 0, 40, 40], "anchor_x": 20, "ground_y": 30, "duration_ms": 120},
                            {"box": [40, 0, 80, 40], "anchor_x": 20, "ground_y": 30, "duration_ms": 180}]}]}
        path = root / "config.json"
        path.write_text(json.dumps(config))
        return root, config, path

    def test_one_scale_preserves_jump_and_png_gif_transparency(self):
        with tempfile.TemporaryDirectory() as d:
            root, config, path = self.fixture(d)
            manifest, reports = self.builder.build(path, root / "out")
            images = []
            for i in range(2):
                with Image.open(root / "out" / f"test_{i}.png") as image:
                    images.append(image.convert("RGBA"))
            boxes = [im.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox() for im in images]
            self.assertEqual(boxes[0][1]-boxes[1][1], 8)
            self.assertEqual(boxes[0][3]-boxes[0][1], boxes[1][3]-boxes[1][1])
            self.assertEqual({m["scale"] for m in reports["TEST"]["frames"]}, {2})
            self.assertEqual(manifest["clips"]["TEST"]["durations"], [120, 180])
            self.assertEqual(images[0].getpixel((0, 0))[3], 0)
            with Image.open(root / "out/test_0.gif") as image:
                gif = image.convert("RGBA")
            self.assertEqual(gif.getpixel((0, 0))[3], 0)
            self.assertEqual(gif.getpixel((100, 170))[3], 255)
            self.assertFalse(reports["TEST"]["approved"])
            self.assertTrue((root / "out/test-preview-dark.gif").is_file())
            self.assertTrue((root / "out/test-contact-light.png").is_file())

    def test_reject_hash_mismatch_before_output(self):
        with tempfile.TemporaryDirectory() as d:
            root, config, path = self.fixture(d)
            config["actions"][0]["source_sha256"] = "0" * 64
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "source_sha256 mismatch"):
                self.builder.build(path, root / "out")
            self.assertFalse((root / "out").exists())

    def test_missing_art_and_runtime_clipping_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root, config, path = self.fixture(d)
            action = config["actions"][0]
            action["cells"][1]["box"] = [0, 0, 8, 8]
            action["cells"][1]["anchor_x"] = 4
            action["cells"][1]["ground_y"] = 8
            action["cells"][0]["ground_y"] = 0
            action["expected_frames"] = 3
            path.write_text(json.dumps(config))
            _, reports = self.builder.build(path, root / "out")
            findings = reports["TEST"]["findings"]
            self.assertTrue(any("missing artwork" in f for f in findings))
            self.assertTrue(any("clips runtime" in f for f in findings))
            self.assertTrue(any("expected_frames" in f for f in findings))
            self.assertFalse(reports["TEST"]["automatic_checks_pass"])

    def test_local_anchors_are_respected_without_silhouette_recentering(self):
        with tempfile.TemporaryDirectory() as d:
            root, config, path = self.fixture(d)
            config["actions"][0]["cells"][1]["anchor_x"] = 18
            path.write_text(json.dumps(config))
            _, reports = self.builder.build(path, root / "out")
            offsets = [f["offset"] for f in reports["TEST"]["frames"]]
            self.assertEqual(offsets[1][0]-offsets[0][0], 4)

    def test_normalized_sheet_reproduces_exact_exported_pixels(self):
        with tempfile.TemporaryDirectory() as d:
            root, config, path = self.fixture(d)
            manifest, _ = self.builder.build(path, root / "out")
            sheets = root / "out/sheets"
            spec = json.loads((sheets / "test-sheet.json").read_text())
            image_path = sheets / spec["source"]
            self.assertEqual(spec["sha256"], hashlib.sha256(image_path.read_bytes()).hexdigest())
            self.assertFalse(spec["review"]["approved"])
            self.assertEqual(spec["scale"], 1)
            self.assertEqual(spec["actions"][0]["durations"], manifest["clips"]["TEST"]["durations"])
            self.assertTrue((sheets / spec["review"]["report"]).is_file())
            with Image.open(image_path) as atlas:
                for index, name in enumerate(manifest["clips"]["TEST"]["frames"]):
                    x0, x1 = spec["columns"][index:index+2]
                    cell = atlas.crop((x0, 0, x1, 200)).convert("RGBA")
                    reproduced = Image.new("RGBA", (200, 200))
                    reproduced.alpha_composite(cell, (round(100-(spec["centers"][index]-x0)*spec["scale"]),
                                                      round(193-spec["baselines"][0]*spec["scale"])))
                    with Image.open(root / "out" / f"{name}.png") as frame:
                        self.assertEqual(reproduced.tobytes(), frame.convert("RGBA").tobytes())


if __name__ == "__main__":
    unittest.main()
