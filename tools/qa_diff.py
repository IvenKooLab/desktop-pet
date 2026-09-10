"""逐帧回归自检：成品帧 vs 源切图 的像素级对比。

原理：把每帧的源切图 alpha 按管线同样的方式（fit 168x176 盒 + 可选缩放/旋转/
偏移）铺到 200x200，再与成品 GIF 的前景 mask 对齐搜索最佳偏移，统计
「源里有、成品里没了」的像素占比（lost%）——空洞/变白/被啃都会现形。

用法：python tools/qa_diff.py

注：scale≠1（压扁/缩放）的帧会产生 5~10% 的对齐/二值化方法学假阳性
（qa_diff 直通 resize+>96 二值化，与管线的预乘+≥160 不同），
此类帧以 qa_frames 数值 + 双底色目检为准。
"""
import math
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent if (Path := __import__("pathlib").Path) else None
CUT = ROOT / "assets" / "cut"
FRAMES = ROOT / "frames3d"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_frames3d import stride  # noqa: E402  # walk 剪腿复现（与构建端同公式）

# 帧 -> (源切图, dy, dx, scale_w, scale_h, tilt[, flip[, shear_dx]])
#   shear_dx: walk 帧的剪腿错位量（构建端 stride() 在全分辨率切图上先行施加）
MAP = {
    "idle_0": ("idleb_0", 0, 0, 1, 1, 0), "idle_1": ("idleb_1", 0, 0, 1, 1, 0),
    "idle_2": ("idleb_2", 0, 0, 1, 1, 0),

    "fast_l_0": ("fl_a", 0, 0, 1, 1, 0), "fast_l_1": ("fl_b", -4, 0, 1, 1, 0),
    "fast_r_0": ("fr_a", 0, 0, 1, 1, 0), "fast_r_1": ("fr_b", -4, 0, 1, 1, 0),
    "bounce_0": ("card_4", 0, 0, 1, 1, 0), "bounce_1": ("card_2", 0, 0, 1, 1, 0),
    "happy_0": ("card_6", 0, 0, 1, 1, 0), "happy_1": ("card_6", -8, 0, 1, 1, 0),
    "shy_0": ("card_1", 0, 0, 1, 1, 0),
    "sleep_0": ("card_3", 4, 0, 1.02, 0.96, 0), "sleep_1": ("card_2", 0, 0, 1, 1, 0),
    "greet_0": ("card_6", 0, 0, 1, 1, 0),
    "cheer_0": ("card_7", 0, 0, 1, 1, 0), "cheer_1": ("card_6", -6, 0, 1, 1, 0),
    "grab_0": ("card_4", 0, 0, 1, 1, -8, False), "grab_1": ("card_2", 0, 0, 1, 1, 8, False),
    "land_0": ("wl_contact", 12, 0, 1.14, 0.84, 0),
    "fall_0": ("fl_a", 0, 0, 1, 1, 0),
    "spin_0": ("front", 0, 0, 0.88, 0.88, 0), "spin_1": ("side", 0, 0, 0.88, 0.88, 0, True),
    "spin_2": ("back", 0, 0, 0.88, 0.88, 0), "spin_3": ("side", 0, 0, 0.88, 0.88, 0, False),
}

# walk 24 相位（程序步态）：与 make_frames3d.build_frames 同公式逐帧登记
#   u=cos(2πk/N)，dxs=28u（左右共用，右向后翻转），dy=round(6u²-4)，tilt=∓2.5u
for _k in range(24):
    _u = math.cos(2 * math.pi * _k / 24)
    MAP[f"walk_l_{_k}"] = ("side", round(6 * _u * _u - 4), 0, 1, 1, -2.5 * _u,
                           False, 28 * _u)
    MAP[f"walk_r_{_k}"] = ("side", round(6 * _u * _u - 4), 0, 1, 1, 2.5 * _u,
                           True, 28 * _u)

FOOT_Y = 194
FIT_W, FIT_H = 168, 176


def fit_mask(im: Image.Image, sw: float, sh: float, tilt: float, flip: bool = False,
             shear_dx: float = 0.0) -> np.ndarray:
    im = im.copy()
    if shear_dx:                                  # walk 剪腿：全分辨率上先行施加（同构建端）
        im = stride(im, shear_dx)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    im.thumbnail((FIT_W, FIT_H), Image.LANCZOS)
    if (sw, sh) != (1, 1):
        im = im.resize((max(1, int(im.width * sw)), max(1, int(im.height * sh))), Image.LANCZOS)
    if tilt:
        im = im.rotate(tilt, resample=Image.BICUBIC, expand=True)
    return np.asarray(im)[..., 3] > 96


def main():
    report = []
    for gif, entry in sorted(MAP.items()):
        src, dy, dx0, sw, sh, tilt = entry[:6]
        flip = entry[6] if len(entry) > 6 else False
        shear = entry[7] if len(entry) > 7 else 0.0
        fpath = FRAMES / f"{gif}.gif"
        spath = CUT / f"{src}.png"
        arr = np.asarray(Image.open(fpath).convert("RGB"))
        r, g, b = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int)
        gmask = ~((r > 200) & (b > 200) & (g < 110))
        cut = Image.open(spath)
        smask = fit_mask(cut, sw, sh, tilt, flip, shear)
        h, w = smask.shape
        best_lost = 1.0
        for ddx in range(-6, 7, 2):
            for ddy in range(-8, 7, 2):
                x0 = (200 - w) // 2 + dx0 + ddx
                y0 = FOOT_Y - h + dy + ddy
                if x0 < 0 or y0 < 0 or x0 + w > 200 or y0 + h > 200:
                    continue
                place = np.zeros((200, 200), bool)
                place[y0:y0 + h, x0:x0 + w] = smask
                inter = (place & gmask).sum()
                lost = 1 - inter / max(1, place.sum())
                best_lost = min(best_lost, lost)
        report.append((best_lost, gif))
    report.sort(reverse=True)
    print("== 成品 vs 源切图 像素回归（lost% 越大丢得越多）")
    bad = 0
    for lost, gif in report:
        flag = "  <-- 丢块" if lost > 0.03 else ""
        if lost > 0.03:
            bad += 1
        print(f"  {gif:12s} lost={lost*100:5.1f}%{flag}")
    print(f"== {len(report)} 帧检查完，{bad} 帧超 3% 阈值" if bad else "== 全部通过（无超 3%）")


if __name__ == "__main__":
    main()
