"""Build-time regression fixtures; skipped in the dependency-free pet runtime suite."""
import importlib.util
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
class ActionImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'tools'))
        import action_quality
        import import_action
        cls.quality, cls.importer = action_quality, import_action

    def fixture(self, root):
        frames = root / 'frames'; frames.mkdir()
        regions = {'hair': [[9, 5, 17, 10]], 'headphones': [[5, 7, 8, 12]],
                   'clothing': [[9, 14, 13, 20]], 'prop': [[14, 14, 20, 20]]}
        im = Image.new('RGBA', (32, 32))
        draw = ImageDraw.Draw(im)
        for part, color in zip(regions, ('#ded5ef', '#33bbdd', '#8060b0', '#303040')):
            for box in regions[part]: draw.rectangle(box, fill=color)
        draw.rectangle((10, 21, 19, 25), fill='#888888')
        im.save(root / 'ref.png')
        meta = {'version': 1, 'reference_index': 0, 'frames': {}}
        for i, shift in enumerate((0, -2, 0)):
            moved = Image.new('RGBA', im.size)
            moved.alpha_composite(im, (0, shift))
            name = f'{i:03}.png'; moved.save(frames / name)
            meta['frames'][name] = {'head_width': 8, 'body_height': 14, 'ground_y': 25, 'anchor_x': 16,
                                   'foot_y': 25 + shift,
                                   'regions': {part: [[x0, y0+shift, x1, y1+shift] for x0,y0,x1,y1 in boxes]
                                               for part, boxes in regions.items()}}
        (root / 'meta.json').write_text(json.dumps(meta))
        (root / 'profile.json').write_text(json.dumps({'source':'ref.png','head_width':8,'body_height':14,'regions':regions}))
        return frames, meta, im, regions

    def test_shared_canvas_preserves_jump_and_alpha(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); frames, meta, im, regions = self.fixture(root)
            spec, report = self.importer.build_sheet(frames, 'TEST', 'none', 0, 180, None,
                                                     root/'out', root/'meta.json', root/'profile.json')
            self.assertFalse(spec['review']['approved'])
            self.assertTrue(report['automatic_checks_pass'])
            self.assertEqual([m['foot_offset'] for m in report['frames']], [0, -2, 0])
            self.assertEqual(spec['scale'], 1)
            with Image.open(root/'out/test-sheet.png') as sheet:
                self.assertEqual(sheet.crop((32,0,64,32)).getchannel('A').getbbox()[1], 3)
                self.assertEqual(sheet.crop((0,0,32,32)).getchannel('A').getbbox()[1], 5)
            self.assertTrue((root/'out/test-sheet-preview-dark.gif').exists())
            self.assertTrue((root/'out/test-sheet-contact-light.png').exists())

    def test_part_colors_catch_local_clothing_change_and_head_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder, meta, im, regions=self.fixture(root)
            changed=Image.open(folder/'001.png').convert('RGBA')
            draw=ImageDraw.Draw(changed); draw.rectangle((9,12,13,18),fill='#202020')
            meta['frames']['001.png']['head_width']=10
            frames=[(p,Image.open(p).convert('RGBA')) for p in sorted(folder.glob('*.png'))]
            frames[1]=(frames[1][0],changed)
            report=self.quality.inspect(frames,meta,im,regions)
            self.assertTrue(any('clothing' in f for f in report['findings']))
            self.assertTrue(any('head scale' in f for f in report['findings']))

    def test_new_props_use_their_own_neutral_reference(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder,meta,im,regions=self.fixture(root)
            frames=[]
            for path in sorted(folder.glob('*.png')):
                image=Image.open(path).convert('RGBA')
                for box in meta['frames'][path.name]['regions']['prop']:
                    ImageDraw.Draw(image).rectangle(box,fill='#20aacc')
                frames.append((path,image))
            meta['prop_policy']='new'
            report=self.quality.inspect(frames,meta,im,regions)
            self.assertFalse(any('prop palette' in f for f in report['findings']))
            self.assertFalse(report['approved'])
            self.assertIn('new prop design',report['prop_reference'])

    def test_unreviewed_sheet_cannot_enter_default_export(self):
        import export_comi_v2
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder,*_=self.fixture(root)
            spec,_=self.importer.build_sheet(folder,'TEST','none',0,180,None,
                                             root/'out',root/'meta.json',root/'profile.json')
            target=root/'assets/comi-v2/actions';target.mkdir(parents=True)
            (target/'test.json').write_text(json.dumps(spec))
            with patch.object(export_comi_v2,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'requires recorded visual review'):
                    export_comi_v2.export(ROOT/'assets/comi-v2/spritesheet.png',[root/'runtime'])
            self.assertFalse((root/'runtime').exists())

    def test_transparent_green_rgb_does_not_trigger_keying(self):
        frame=Image.new('RGBA',(16,16),(0,255,0,0))
        ImageDraw.Draw(frame).rectangle((4,4,10,10),fill='#aa88dd')
        self.assertEqual(self.importer.detect_key(frame),'none')

    def test_reject_invalid_durations_and_missing_annotations(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder,*_=self.fixture(root)
            with self.assertRaises(ValueError):
                self.importer.build_sheet(folder,'TEST','none',0,0,None,root/'out')
            with self.assertRaises(ValueError):
                self.importer.build_sheet(folder,'TEST','none',0,180,None,root/'out')
            self.assertFalse((root/'out').exists())

    def test_loop_seam_and_gaze_pop_are_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder,meta,im,regions=self.fixture(root)
            frames=[(p,Image.open(p).convert('RGBA')) for p in sorted(folder.glob('*.png'))]
            frames[-1]=(frames[-1][0],Image.new('RGBA',im.size,'#f0f0f0'))
            report=self.quality.inspect(frames,meta,im,regions)
            self.assertTrue(any('seam' in f for f in report['findings']))
            self.assertFalse(report['approved'])

if __name__ == '__main__': unittest.main()
