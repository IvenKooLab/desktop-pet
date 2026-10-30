"""Shipped seasonal artwork must not reintroduce the oversized/cropped sprite bug."""
import hashlib
import json
from pathlib import Path
import unittest

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('TRICK_OR_TREAT', 'GHOST_SHEET', 'VAMPIRE_CAPE', 'WITCH_SPELL', 'BLACK_CAT')


@unittest.skipIf(Image is None, 'Pillow required for artwork checks')
class SeasonalArtworkTests(unittest.TestCase):
    def test_registered_frames_fit_and_share_neutral_endpoints(self):
        manifest = json.loads((ROOT/'frames3d/animation.json').read_text())
        for name in NAMES:
            with self.subTest(action=name):
                clip = manifest['clips'][name]
                self.assertGreaterEqual(len(clip['frames']), 15)
                images = []
                for stem in clip['frames']:
                    with Image.open(ROOT/'frames3d'/f'{stem}.png') as image:
                        image = image.convert('RGBA')
                    self.assertEqual(image.size, (200, 200))
                    box = image.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
                    self.assertIsNotNone(box)
                    self.assertGreater(min(box[:2]), 1)
                    self.assertLess(max(box[2:]), 199)
                    images.append(image)
                first = images[0].getchannel('A').point(lambda a: 255 if a > 128 else 0).getbbox()
                self.assertLessEqual(first[3]-first[1], 150)
                self.assertGreaterEqual(first[1], 48)
                self.assertEqual(images[0].tobytes(), images[-1].tobytes())
                self.assertEqual(len(images), len(clip['durations']))

    def test_registered_sources_match_review_and_rebuild_recipe(self):
        folder = ROOT/'assets/comi-v2/actions'
        recipe = json.loads((folder/'halloween-source/build.json').read_text())
        self.assertEqual({action['name'] for action in recipe['actions']}, set(NAMES))
        for action in recipe['actions']:
            source = folder/'halloween-source'/action['source']
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), action['source_sha256'])
            spec = json.loads((folder/(action['name'].lower()+'-sheet.json')).read_text())
            self.assertEqual(spec['sha256'], spec['review']['source_sha256'])
            self.assertEqual(hashlib.sha256((folder/spec['source']).read_bytes()).hexdigest(), spec['sha256'])
            self.assertEqual(spec['scale'], 1)

    def test_new_performances_keep_the_slower_shared_timelines(self):
        manifest = json.loads((ROOT/'frames3d/animation.json').read_text())
        recipe = json.loads((ROOT/'assets/comi-v2/actions/halloween-source/build.json').read_text())
        for action in recipe['actions']:
            clip = manifest['clips'][action['name']]
            self.assertEqual(clip['durations'], [cell['duration_ms'] for cell in action['cells']])
            seconds = sum(clip['durations']) / .75 / 1000
            self.assertGreaterEqual(seconds, 8)
            self.assertLessEqual(seconds, 9)


if __name__ == '__main__':
    unittest.main()
