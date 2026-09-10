"""MVP 生成器：一张三视图 → 一套简化版桌宠动作帧。

只传三视图（正/侧/背，任意背景）即可生成：
    待机呼吸（压扁模拟）· 走路（侧视程序步态，左右朝向自动检测）·
    下落/落地/抓取/睡觉 · 转一圈（360°）
表情反应/真迈步循环为进阶版能力，需补充对应 Sheet（见 SOP）。

用法：
    python tools/make_pet_from_views.py --src 路径/三视图.png [--out frames3d_mvp]
                                        [--side-faces auto|left|right]
构图约定：从左到右 = 正 / 侧 / 背（可用 --order 调整，如 --order side,front,back）。
产出后用 PET_FRAMES_DIR 环境变量指向输出目录即可运行 pet.py。
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_frames3d import (  # noqa: E402
    FIT_H, FIT_W, FOOT_Y, on_canvas, rough_boxes_checker, rembg_fg,
)

CANVAS = 200


def cut_figure(img: Image.Image, box) -> Image.Image:
    """单人物裁切 → rembg（滞后阈值+深色回收+fill_holes）→ 去边 → 紧凑裁切。"""
    x0, y0, x1, y1 = box
    pad = 16
    crop = img.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))
    a = rembg_fg(crop)
    lbl, n = ndimage.label(a)
    if n > 1:
        sz = ndimage.sum(a, lbl, range(1, n + 1))
        keep = np.zeros(n + 1, bool); keep[1:] = sz >= sz.max() * 0.02
        a = keep[lbl]
    rgba = np.dstack([np.asarray(crop), a * 255]).astype(np.uint8)
    vis = rgba[..., 3] > 0
    lbl, n = ndimage.label(vis)
    if n > 1:
        sz = ndimage.sum(vis, lbl, range(1, n + 1))
        keep = np.zeros(n + 1, bool); keep[1:] = sz >= sz.max() * 0.08
        rgba[..., 3] = (keep[lbl] * 255).astype(np.uint8)
    im = Image.fromarray(rgba)
    return im.crop(im.getbbox())


def rough_boxes(img: Image.Image, gap: int = 40, min_h: int = 200):
    """任意背景通用粗定位：缩略图过 rembg（粗精度足够定框）。"""
    small = img.resize((max(160, img.width // 4), max(120, img.height // 4)), Image.LANCZOS)
    fg = rembg_fg(small)
    fg = ndimage.binary_closing(fg, iterations=2)
    lbl, n = ndimage.label(fg)
    boxes = []
    for i in ndimage.find_objects(lbl):
        if i is None:
            continue
        h = i[0].stop - i[0].start
        w = i[1].stop - i[1].start
        if h < min_h / 4 or w < 40:
            continue
        boxes.append([i[1].start * 4, i[0].start * 4, i[1].stop * 4, i[0].stop * 4])
    boxes.sort(key=lambda b: (b[1] // 400, b[0]))
    return boxes


def detect_facing(im: Image.Image) -> str:
    """侧视图朝向检测：头部区域暖色（皮肤）质心在头质心哪侧。失败默认 left。"""
    a = np.asarray(im)
    fg = a[..., 3] > 0
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    skin = (r - b > 12) & (r > 110) & fg
    ys, xs = np.where(fg)
    y0, y1 = ys.min(), ys.min() + int((ys.max() - ys.min()) * 0.45)
    head = np.zeros_like(fg)
    head[y0:y1] = fg[y0:y1]
    sk = skin & head
    sk_ys, sk_xs = np.where(sk)
    if len(sk_ys) < 80:
        return "left"
    hd_ys, hd_xs = np.where(head)
    return "left" if sk_xs.mean() < hd_xs.mean() else "right"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="三视图路径（正/侧/背 从左到右）")
    ap.add_argument("--out", default="frames3d", help="输出帧目录（默认覆盖 frames3d）")
    ap.add_argument("--order", default="front,side,back", help="从左到右的角色视图名")
    ap.add_argument("--side-faces", default="auto", choices=["auto", "left", "right"])
    args = ap.parse_args()

    img = Image.open(args.src).convert("RGB")
    boxes = rough_boxes(img)
    order = args.order.split(",")
    print(f"检测到 {len(boxes)} 个人物，期望 {len(order)} 个视图")
    if len(boxes) != len(order):
        print("!! 人物数与视图数不符，请检查素材或用 --order 调整", file=sys.stderr)
        sys.exit(1)
    figures = {name: cut_figure(img, box) for name, box in zip(order, boxes)}
    for k, v in figures.items():
        print(f"  {k}: {v.size}")

    side = figures.get("side")
    facing = detect_facing(side) if side is not None else args.side_faces
    if args.side_faces != "auto":
        facing = args.side_faces
    print("侧视图朝向:", facing)

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    for old in out.glob("*.gif"):
        old.unlink()

    front = figures.get("front")
    back = figures.get("back")

    def put(name, im, **kw):
        on_canvas(im, **kw).save(out / f"{name}.gif")

    # 待机呼吸：正面 + 压扁微变
    if front is not None:
        put("idle_0", front)
        put("idle_1", front, scale=(1.03, 0.97), dy=3)
        put("idle_2", front, dy=1)
    # 走路：侧视程序步态 8 相位（剪腿+颠步连续变化，播放 ~200ms/帧）
    if side is not None:
        from make_frames3d import stride
        phases = [36, 18, 0, -18, -36, -18, 0, 18]   # 剪腿连续相位
        l_face = facing == "left"
        for i, dxs in enumerate(phases):
            base = stride(side, dxs if l_face else -dxs)
            dyv = 3 if abs(dxs) > 20 else -4         # 触地低、过渡高（颠步）
            tl = -dxs / 36 * 3
            put(f"walk_l_{i}", base, tilt=tl if l_face else -tl, dy=dyv,
                flip=not l_face)
            put(f"walk_r_{i}", base, tilt=-tl if l_face else tl, dy=dyv,
                flip=l_face)
    # 下落/落地/抓取/睡觉：全部由正面/侧视派生
    if front is not None:
        put("fall_0", front, tilt=6)
        put("land_0", front, scale=(1.14, 0.84), dy=12)
        put("grab_0", front, tilt=-8)
        put("grab_1", front, tilt=8)
        put("sleep_0", front, scale=(1.02, 0.96), dy=4, dim=0.72)
        put("sleep_1", front, dim=0.72)
    # 转一圈：正→侧→背→侧（镜像）
    if all(v is not None for v in (front, side, back)):
        put("spin_0", front)
        put("spin_1", side, flip=(facing == "left"))
        put("spin_2", back)
        put("spin_3", side, flip=(facing != "left"))

    total = len(list(out.glob("*.gif")))
    print(f"== 完成：{total} 帧 -> {out}")
    print(f"== 运行：PET_FRAMES_DIR={out} python pet.py")


if __name__ == "__main__":
    main()
