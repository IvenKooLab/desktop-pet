"""构建 av_walk 真素材帧：characters/iven-pet/animations/walk/frames/walk_01..08.png
→ frames3d/av_walk_{l,r}_{00..07}.gif（200x200 品红画布，脚底线锚定，左向=镜像）。
锚定规则：每帧以"脚底基线行"（脚步区最宽行）对齐 FOOT_Y，保证脚底不上下跳。
"""
import numpy as np
from PIL import Image
from pathlib import Path

SRC = Path('characters/iven-pet/animations/walk/frames')
OUT = Path('frames3d')
SIZE = 200
FOOT_Y = 194
# 统一缩放基准：以最高帧身高为 176px 基准，8 帧共用同一比例（禁止逐帧缩放）
REF_H = 874


def sole_row(arr, fg):
    """脚底基线行 = 底部 25% 区域内最宽行（平贴地面的鞋底）。"""
    h = arr.shape[0]
    band = fg[int(h * 0.75):]
    widths = band.sum(axis=1)
    return int(h * 0.75) + int(widths.argmax())


def build():
    ims, soles, tops = [], [], []
    for i in range(1, 9):
        im = Image.open(SRC / f'walk_{i:02d}.png').convert('RGBA')
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys, xs = np.where(fg)
        im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        # 统一比例缩放（高度基准 REF_H，禁止逐帧适配）
        s = REF_H and (176 / REF_H)
        w = max(1, round(im.width * s))
        h = max(1, round(im.height * s))
        im = im.resize((w, h), Image.LANCZOS)
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys, _ = np.where(fg)
        sole = sole_row(a, fg)
        ims.append((im, sole, int(ys.min())))
        print(f'F{i}: h={im.height} sole={sole}')
    for i, (im, sole, _) in enumerate(ims):
        for d, flip in (('r', False), ('l', True)):
            x = im
            if flip:
                x = x.transpose(Image.FLIP_LEFT_RIGHT)
                sole = sole
            a = np.asarray(x).copy()
            a[..., 3] = np.where(a[..., 3] >= 128, 255, 0).astype(np.uint8)
            x = Image.fromarray(a, 'RGBA')
            cv = Image.new('RGB', (SIZE, SIZE), (255, 0, 255))
            px = (SIZE - x.width) // 2
            py = FOOT_Y - sole
            cv.paste(x, (px, py), x)
            cv.save(OUT / f'av_walk_{d}_{i:02d}.gif')
    print(f'{8 * 2} GIF -> {OUT}')


if __name__ == '__main__':
    build()
