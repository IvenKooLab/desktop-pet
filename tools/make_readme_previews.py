"""Rebuild README GIFs from the shipped PNGs and animation.json (Pillow required)."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

PLAYBACK_SPEED = 0.75

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    'little-breaks': [('STRETCH', 1), ('DOZE', 1), ('RUBIK', 1)],
    'idle-look': [('IDLE', 2), ('SPIN', 1)],
    'reactions': [('GREET', 1), ('BOUNCE', 1), ('CHEER', 1)],
    'action-cycle': [('IDLE', 2), ('WAITING', 1), ('IDLE', 2), ('WORK', 1),
                     ('IDLE', 2), ('REVIEW', 1), ('IDLE', 2), ('FAILED', 1)],
}

def make_profile_preview(manifest, output):
    """Export shipped transparent sprites directly, without a matte or captions."""
    sprites, durations = [], []
    bounds = None
    for state, repeats in GROUPS['reactions']:
        clip = manifest['clips'][state]
        for _ in range(repeats):
            for name, duration in zip(clip['frames'], clip['durations']):
                sprite = Image.open(ROOT / 'frames3d' / (name + '.png')).convert('RGBA')
                box = sprite.getbbox()
                if box:
                    bounds = box if bounds is None else (min(bounds[0], box[0]), min(bounds[1], box[1]),
                                                        max(bounds[2], box[2]), max(bounds[3], box[3]))
                sprites.append(sprite)
                durations.append(round(duration / PLAYBACK_SPEED / 10) * 10)
    # One shared crop preserves size and placement throughout the animation.
    crop = (max(0, bounds[0]-8), max(0, bounds[1]-8),
            min(sprites[0].width, bounds[2]+8), min(sprites[0].height, bounds[3]+8))
    sprites = [sprite.crop(crop) for sprite in sprites]
    strip = Image.new('RGB', (sprites[0].width*len(sprites), sprites[0].height))
    for i, sprite in enumerate(sprites):
        strip.paste(sprite.convert('RGB'), (i*sprite.width, 0))
    palette = strip.quantize(colors=255)
    frames = []
    for sprite in sprites:
        indexed = sprite.convert('RGB').quantize(palette=palette, dither=Image.Dither.NONE)
        alpha = sprite.getchannel('A').tobytes()
        frame = Image.new('P', sprite.size)
        frame.putpalette([0, 0, 0]+palette.getpalette()[:765])
        frame.putdata([color+1 if opacity >= 128 else 0
                       for color, opacity in zip(indexed.tobytes(), alpha)])
        frames.append(frame)
    path = output / 'profile-reactions.gif'
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, disposal=2, transparency=0, background=0, optimize=False)
    with Image.open(path) as decoded:
        total = 0
        assert decoded.is_animated
        for i in range(decoded.n_frames):
            decoded.seek(i)
            rgba = decoded.convert('RGBA')
            assert rgba.getpixel((0, 0))[3] == 0, 'Background must stay transparent'
            assert rgba.getchannel('A').getextrema() == (0, 255)
            total += decoded.info['duration']
        assert total == sum(durations)
    print(f'{path.relative_to(ROOT)}: transparent, {frames[0].size}, {total}ms')


def main():
    manifest = json.loads((ROOT / 'frames3d/animation.json').read_text())
    output = ROOT / 'docs/previews'
    output.mkdir(parents=True, exist_ok=True)
    make_profile_preview(manifest, output)
    for title, playlist in GROUPS.items():
        frames, durations = [], []
        for state, repeats in playlist:
            clip = manifest['clips'][state]
            for _ in range(repeats):
                for name, duration in zip(clip['frames'], clip['durations']):
                    canvas = Image.new('RGB', (280, 252), '#eef0f6')
                    sprite = Image.open(ROOT / 'frames3d' / (name + '.png')).convert('RGBA')
                    canvas.paste(sprite, (40, 16), sprite)
                    draw = ImageDraw.Draw(canvas)
                    draw.text((140, 232), state.replace('_', ' '), fill='#51456e', anchor='mm')
                    frames.append(canvas)
                    durations.append(round(duration / PLAYBACK_SPEED / 10) * 10)
        path = output / (title + '.gif')
        frames[0].save(path, save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, disposal=2, optimize=False)
        with Image.open(path) as decoded:
            assert decoded.is_animated and decoded.info['loop'] == 0
            total = 0
            for index in range(decoded.n_frames):
                decoded.seek(index)
                assert decoded.size == (280, 252)
                total += decoded.info['duration']
            assert total == sum(durations)
        print(f'{path.relative_to(ROOT)}: {path.stat().st_size:,} bytes, {total}ms')

if __name__ == '__main__':
    main()
