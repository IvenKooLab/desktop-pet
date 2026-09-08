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

    # 按视角分类比较：侧视帧（walk/fast/侧spin）头宽天然比正面窄 ~15%，
    # 混用同一中位数会把正常侧视帧误报；压扁帧(land_0)属设计意图白名单
    # 按视角聚成正面/侧视两类，取各自头宽中位数；
    # 头宽贴近任一类别中位数即通过（混合姿势如 fall=侧视帧、倾斜变体天然兼容），
    # 真破损（整块缺失/比例崩坏）会与两类中位都偏离。land_0 压扁系设计意图白名单。
    classes = {}
    for name, (head, h) in stats.items():
        side = any(k in name for k in ("walk_", "fast_", "spin_1", "spin_3"))
        classes.setdefault("side" if side else "front", []).append((name, head, h))
    med = {c: (float(np.median([v[1] for v in vs])), float(np.median([v[2] for v in vs])))
           for c, vs in classes.items()}
    for c, (mh0, mhh0) in sorted(med.items()):
        print(f"  [{c}] 中位头宽 {mh0:.0f} 中位高 {mhh0:.0f}  x{len(classes[c])}")
    ref_head = [v[0] for v in med.values()]
    med_h = float(np.median([v[1] for v in stats.values()]))
    for name, (head, h) in stats.items():
        if ref_head and min(abs(head - m) / m for m in ref_head) > 0.15:
            problems.append(f"{name}: 头宽 {head} 偏离两类中位 {ref_head} 超15%")
        if name not in ("land_0",) and abs(h - med_h) / med_h > 0.15:
            problems.append(f"{name}: 高 {h} 偏离中位 {med_h:.0f} 超15%")

    print(f"== 数值自检：{len(files)} 帧，分类中位头宽 {[round(m) for m in ref_head]}")
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
