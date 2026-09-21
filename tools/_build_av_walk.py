"""构建 av_walk 真素材帧：characters/iven-pet/animations/walk/frames/walk_01..08.png
→ frames3d/av_walk_{l,r}_{00..07}.gif（200x200 品红画布，脚底线锚定，左向=镜像）。
锚定规则：每帧以"内容末行"（真实接地线）对齐 FOOT_Y，保证脚底不上下跳。
缩放规则：统一比例 = TARGET_H / 实测切图最高身高（measure_ref_h），禁止逐帧适配。
"""
import numpy as np
from PIL import Image
from pathlib import Path

SRC = Path('characters/iven-pet/animations/walk/frames')
OUT = Path('frames3d')
SIZE = 200
FOOT_Y = 194
TARGET_H = 176   # 系统统一角色高度（make_frames3d.py:36 FIT_H=176）


def measure_ref_h():
    """缩放基准 = 本 builder 实际消费工件的最高帧身高（逐帧实测）。

    F4 教训（docs/JEV_BOUNDARY_AUDIT.md）：旧版 REF_H=874 硬编码量在
    原始 Sheet 人物 bbox 上（walk_sheet_8f.png strip8 @ mx<245 = 874px，
    含抗锯齿晕环），而本 builder 消费的是 rembg+defringe 后的切图
    （762~764px）→ 角色缩到 154px，比全套动画小 12.5%。
    语义纪律：缩放基准必须与实际输入工件同源——每次构建时对 8 张切图
    实测 alpha>96 bbox 高、取最高帧，禁止引用任何 Sheet/历史魔法数。
    """
    heights = []
    for i in range(1, 9):
        im = Image.open(SRC / f'walk_{i:02d}.png').convert('RGBA')
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys, _ = np.where(fg)
        heights.append(int(ys.max() - ys.min() + 1))
    return max(heights)


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
    ref_h = measure_ref_h()
    s = TARGET_H / ref_h
    print(f'ref_h={ref_h} (实测切图最高身高) scale={s:.5f} -> TARGET_H={TARGET_H}')
    ims = []
    for i in range(1, 9):
        im = Image.open(SRC / f'walk_{i:02d}.png').convert('RGBA')
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys, xs = np.where(fg)
        im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        # 统一比例缩放（基准=实测切图最高身高，禁止逐帧适配）
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
