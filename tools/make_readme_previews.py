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

def main():
    manifest = json.loads((ROOT / 'frames3d/animation.json').read_text())
    output = ROOT / 'docs/previews'
    output.mkdir(parents=True, exist_ok=True)
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
