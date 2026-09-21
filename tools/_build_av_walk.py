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
# 注意：REF_H 是"写作时最高源帧身高"。源素材重切后会变化（874→当前 763），
# 不同步更新的表现 = 人物相对全套动画变小（审计发现 F4，修否待 owner 决策）
REF_H = 874
TARGET_H = 176


def sole_row(arr, fg):
    """脚底基线行 = 内容最末行（真实接地线）。

    步行各姿态至少一只鞋贴地 → 全图最低不透明像素即接地线，
    逐帧取该行对齐 FOOT_Y 即"脚底不上下跳"。
    旧版"底部 25% 最宽行"是鞋面/脚背的偶然宽扫描线：不同步姿选中不同行
    （实测 py 55~64 抖动 9px），且锚行比内容底部高 9~18px → 贴图越界被画布
    静默裁切（F1/F2 审计结论，见 docs/JEV_BOUNDARY_AUDIT.md）。
    注意：必须在 alpha 二值化之后的 mask 上取（与最终贴图同 mask），
    否则半透明边缘行会让锚点与可见内容不一致。
    """
    rows = np.where(fg.any(axis=1))[0]
    return int(rows[-1])


def build():
    ims = []
    for i in range(1, 9):
        im = Image.open(SRC / f'walk_{i:02d}.png').convert('RGBA')
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys, xs = np.where(fg)
        im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        # 统一比例缩放（高度基准 REF_H，禁止逐帧适配）
        s = TARGET_H / REF_H
        w = max(1, round(im.width * s))
        h = max(1, round(im.height * s))
        im = im.resize((w, h), Image.LANCZOS)
        # 先二值化再定锚：锚点 mask 与最终贴图 mask 完全一致
        a = np.asarray(im).copy()
        a[..., 3] = np.where(a[..., 3] >= 128, 255, 0).astype(np.uint8)
        fg = a[..., 3] > 0
        sole = sole_row(a, fg)
        ims.append((Image.fromarray(a, 'RGBA'), sole))
        print(f'F{i}: h={im.height} sole={sole} py={FOOT_Y - sole} '
              f'content=[{FOOT_Y - sole},{FOOT_Y - sole + im.height - 1}]')
    for i, (im, sole) in enumerate(ims):
        for d, flip in (('r', False), ('l', True)):
            x = im.transpose(Image.FLIP_LEFT_RIGHT) if flip else im
            cv = Image.new('RGB', (SIZE, SIZE), (255, 0, 255))
            px = (SIZE - x.width) // 2
            py = FOOT_Y - sole
            cv.paste(x, (px, py), x)
            cv.save(OUT / f'av_walk_{d}_{i:02d}.gif')
    print(f'{8 * 2} GIF -> {OUT}')


if __name__ == '__main__':
    build()
