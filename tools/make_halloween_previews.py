"""Render transparent Halloween demonstrations from shipped sprites, at runtime speed."""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('TRICK_OR_TREAT', 'GHOST_SHEET', 'VAMPIRE_CAPE', 'WITCH_SPELL', 'BLACK_CAT')


def save_transparent(frames, durations, path):
    # A shared palette prevents costume/skin colours changing between GIF frames.
    strip = Image.new('RGB', (frames[0].width * len(frames), frames[0].height))
    for index, frame in enumerate(frames):
        strip.paste(frame.convert('RGB'), (index * frame.width, 0))
    palette = strip.quantize(colors=255)
    encoded = []
    for frame in frames:
        indexed = frame.convert('RGB').quantize(palette=palette, dither=Image.Dither.NONE)
        output = Image.new('P', frame.size)
        output.putpalette([0, 0, 0] + palette.getpalette()[:765])
        output.putdata([colour + 1 if alpha >= 128 else 0
                        for colour, alpha in zip(indexed.tobytes(), frame.getchannel('A').tobytes())])
        encoded.append(output)
    encoded[0].save(path, save_all=True, append_images=encoded[1:], duration=durations,
                    loop=0, disposal=2, transparency=0, background=0, optimize=False)
    with Image.open(path) as decoded:
        total = 0
        for index in range(decoded.n_frames):
            decoded.seek(index)
            assert decoded.convert('RGBA').getpixel((0, 0))[3] == 0
            total += decoded.info['duration']
        assert total == sum(durations)


def main():
    manifest = json.loads((ROOT / 'frames3d/animation.json').read_text())
    output = ROOT / 'docs/previews'
    clips = {}
    for name in NAMES:
        clip = manifest['clips'][name]
        frames = [Image.open(ROOT / 'frames3d' / (stem + '.png')).convert('RGBA') for stem in clip['frames']]
        durations = [round(ms / .75 / 10) * 10 for ms in clip['durations']]
        save_transparent(frames, durations, output / ('halloween-' + name.lower() + '.gif'))
        clips[name] = (frames, durations)
    # Five clips play side by side; the shorter cat performance rests at its neutral pose.
    total = max(sum(durations) for _, durations in clips.values())
    overview, timing = [], []
    for time in range(0, total, 40):
        canvas = Image.new('RGBA', (200 * len(NAMES), 200))
        for column, name in enumerate(NAMES):
            frames, durations = clips[name]
            phase, index = time, 0
            while index < len(frames)-1 and phase >= durations[index]:
                phase -= durations[index]; index += 1
            canvas.alpha_composite(frames[index], (column * 200, 0))
        overview.append(canvas)
        timing.append(min(40, total-time))
    save_transparent(overview, timing, output / 'halloween.gif')
    print('PASS: five transparent clips and overview, original runtime timing')


if __name__ == '__main__':
    main()
