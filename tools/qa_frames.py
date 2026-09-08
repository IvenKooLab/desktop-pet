"""全帧质量自检：数值异常检测 + 双底色接触表输出。

检查项（对 frames3d/*.gif）：
    1. 悬浮碎片：前景中被主连通域分离的、面积 > 总面积 0.3% 的碎块
       （耳机梁被啃碎/切图残渣的典型特征）
    2. 内部孔洞：完全被前景包围的透明区域，面积 > 总面积 1%（头发掏空等）
    3. 尺寸一致性：头宽/身高与全帧中位数偏差 > 15%

用法：python tools/qa_frames.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
FRAMES = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "frames3d"


def keyed(rgb_arr):
    """品红色键 → 前景 mask。"""
    r, g, b = rgb_arr[..., 0].astype(int), rgb_arr[..., 1].astype(int), rgb_arr[..., 2].astype(int)
    return ~((r > 200) & (b > 200) & (g < 110))


def on_bg(rgb_arr, mask, bg):
    tile = Image.new("RGB", rgb_arr.shape[1::-1], bg)
    tile.paste(Image.fromarray(rgb_arr), (0, 0), Image.fromarray((mask * 255).astype("uint8")))
    return tile


def main():
    files = sorted(FRAMES.glob("*.gif"))
    if not files:
        print("no frames"); sys.exit(1)
    problems, stats = [], {}
    for f in files:
        arr = np.asarray(Image.open(f).convert("RGB"))
        fg = keyed(arr)
        ys, xs = np.where(fg)
        if len(xs) == 0:
            problems.append(f"{f.stem}: 空帧！"); continue
        area = int(fg.sum())
        # 1) 悬浮碎片
        lbl, n = ndimage.label(fg)
        sizes = sorted((ndimage.sum(fg, lbl, range(1, n + 1))).tolist(), reverse=True)
        frags = [int(s) for s in sizes[1:] if s > area * 0.003]
        if frags:
            problems.append(f"{f.stem}: 悬浮碎片 {len(frags)} 块 {frags[:3]}")
        # 2) 内部孔洞
        holes = ~fg
        lbl, n = ndimage.label(holes)
        border = set(np.unique(np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]])))
        h_sizes = [int(ndimage.sum(holes, lbl, i)) for i in range(1, n + 1) if i not in border]
        big_holes = [s for s in h_sizes if s > area * 0.01]
        if big_holes:
            problems.append(f"{f.stem}: 内部孔洞 {len(big_holes)} 个 {sorted(big_holes, reverse=True)[:3]}")
        # 3) 尺寸
        h = ys.max() - ys.min() + 1
        top = fg[ys.min():ys.min() + int(h * 0.35)]
        head = int(top.sum(axis=1).max()) if len(top) else 0
        stats[f.stem] = (head, h)

    heads = np.array([v[0] for v in stats.values()])
    hh = np.array([v[1] for v in stats.values()])
    med_head, med_h = np.median(heads), np.median(hh)
    for name, (head, h) in stats.items():
        if abs(head - med_head) / med_head > 0.15:
            problems.append(f"{name}: 头宽 {head} 偏离中位 {med_head:.0f} 超15%")
        if name not in ("land_0",) and abs(h - med_h) / med_h > 0.15:
            problems.append(f"{name}: 高 {h} 偏离中位 {med_h:.0f} 超15%")  # land_0 压扁系设计意图

    print(f"== 数值自检：{len(files)} 帧，中位头宽 {med_head:.0f}，中位高 {med_h:.0f}")
    if problems:
        print("== 发现问题：")
        for p in problems:
            print("  ", p)
    else:
        print("== 数值自检全部通过")

    # 接触表：上排深底、下排浅底
    names = sorted(stats)
    cols, cell = 7, 230
    rows = (len(names) + cols - 1) // cols
    for row, bgc in enumerate([(28, 28, 36), (246, 246, 246)]):
        sheet = Image.new("RGB", (cols * cell, rows * cell), bgc)
        dr = ImageDraw.Draw(sheet)
        for i, n in enumerate(names):
            arr = np.asarray(Image.open(FRAMES / f"{n}.gif").convert("RGB"))
            mask = keyed(arr)
            tile = on_bg(arr, mask, bgc)
            x, y = (i % cols) * cell, (i // cols) * cell
            sheet.paste(tile.resize((cell - 20, cell - 20), Image.LANCZOS), (x + 10, y + 15))
            dr.text((x + 8, y + 2), n, fill=(90, 220, 90) if row else (120, 200, 255))
        out = ROOT / "assets" / "cut" / f"qa_sheet_{'dark' if row == 0 else 'light'}.png"
        sheet.save(out)
    print("== 接触表 -> assets/cut/qa_sheet_dark.png / qa_sheet_light.png")


if __name__ == "__main__":
    main()
