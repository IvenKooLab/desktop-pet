"""逐帧回归自检：成品帧 vs 源切图 的像素级对比。

原理：把每帧的源切图 alpha 按管线同样的方式（fit 168x176 盒 + 可选缩放/旋转/
偏移）铺到 200x200，再与成品 GIF 的前景 mask 对齐搜索最佳偏移，统计
「源里有、成品里没了」的像素占比（lost%）——空洞/变白/被啃都会现形。

用法：python tools/qa_diff.py
"""
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent if (Path := __import__("pathlib").Path) else None
CUT = ROOT / "assets" / "cut"
FRAMES = ROOT / "frames3d"

# 帧 -> (源切图, dy, dx, scale_w, scale_h, tilt)
MAP = {
    "idle_0": ("idleb_0", 0, 0, 1, 1, 0), "idle_1": ("idleb_1", 0, 0, 1, 1, 0),
    "idle_2": ("idleb_2", 0, 0, 1, 1, 0),
    "walk_l_0": ("wl_contact", 0, 0, 1, 1, 0), "walk_l_1": ("wl_pass", -4, 0, 1, 1, 0),
    "walk_l_2": ("wl_contact", 0, 0, 1, 1, 0), "walk_l_3": ("wl_pass", -3, 0, 1, 1, 0),
    "walk_r_0": ("wr_contact", 0, 0, 1, 1, 0), "walk_r_1": ("wr_pass", -4, 0, 1, 1, 0),
    "walk_r_2": ("wr_contact", 0, 0, 1, 1, 0), "walk_r_3": ("wr_pass", -3, 0, 1, 1, 0),
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

FOOT_Y = 194
FIT_W, FIT_H = 168, 176


def fit_mask(im: Image.Image, sw: float, sh: float, tilt: float, flip: bool = False) -> np.ndarray:
    im = im.copy()
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
        fpath = FRAMES / f"{gif}.gif"
        spath = CUT / f"{src}.png"
        arr = np.asarray(Image.open(fpath).convert("RGB"))
        r, g, b = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int)
        gmask = ~((r > 200) & (b > 200) & (g < 110))
        cut = Image.open(spath)
        smask = fit_mask(cut, sw, sh, tilt, flip)
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
