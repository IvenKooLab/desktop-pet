"""切分 8 条带 → 逐条 rembg → 8 个人物切图（用后即删的临时脚本）。"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_frames3d import rembg_fg  # noqa: E402

SRC = Path('characters/iven-pet/animations/walk/source/walk_sheet_8f.png')
OUT = Path('assets/cut')

img = Image.open(SRC).convert('RGB')
W, H = img.size
n = 8
strip_w = W / n
figures = []
for i in range(n):
    x0 = max(0, int(i * strip_w) - 10)
    x1 = min(W, int((i + 1) * strip_w) + 10)
    crop = img.crop((x0, 0, x1, H))
    a = rembg_fg(crop)
    lbl, nn = ndimage.label(a)
    if nn > 1:
        sz = np.bincount(lbl.ravel())
        keep = np.zeros(len(sz), bool)
        keep[1:] = sz[1:] >= sz.max() * 0.08
        a = keep[lbl]
    rgba = np.dstack([np.asarray(crop), a * 255]).astype(np.uint8)
    vis = rgba[..., 3] > 0
    lb2, nn2 = ndimage.label(vis)
    if nn2 > 1:
        sz2 = np.bincount(lb2.ravel())
        keep2 = np.zeros(len(sz2), bool)
        keep2[1:] = sz2[1:] >= sz2.max() * 0.08
        rgba[..., 3] = (keep2[lb2] * 255).astype(np.uint8)
    im = Image.fromarray(rgba)
    fig = im.crop(im.getbbox())
    figures.append(fig)
    outdir = Path('characters/iven-pet/animations/walk/frames')
    outdir.mkdir(parents=True, exist_ok=True)
    fig.save(outdir / f'walk_{i+1:02d}.png')
    print(f'strip {i}: fg {int(a.sum())}px figure {im.size} -> walk_{i+1:02d}.png')

cell = 300
sheet = Image.new('RGB', (4 * cell, 2 * cell), (245, 245, 245))
dr = ImageDraw.Draw(sheet)
for i, im in enumerate(figures):
    t = im.copy()
    t.thumbnail((cell - 16, cell - 24))
    sheet.paste(t, ((i % 4) * cell + 8, (i // 4) * cell + 22), t)
    dr.text(((i % 4) * cell + 10, (i // 4) * cell + 6), f'F{i+1}', fill=(60, 60, 160))
sheet.save(OUT / 'walk8_film.png')

anim = {
    "name": "walk",
    "fps": 12,
    "loop": True,
    "facing": "right",
    "anchor": "foot_center",
    "frames": [f"walk_{i+1:02d}.png" for i in range(8)],
    "source": "sheet",
}
(OUT.parent / 'characters' / 'iven-pet' / 'animations' / 'walk' / 'animation.json').write_text(
    __import__('json').dumps(anim, ensure_ascii=False, indent=2), encoding='utf-8')
print('animation.json ok')
