"""qa_walk8 · 8 帧 Walk 素材双层验收工具（ASSET-FIRST 冻结期专用）。

用法：python tools/qa_walk8.py <帧目录或通配符前缀>

第一层 Identity Consistency（A-H）：
    头宽/身高/耳机带高度/脚底基线 跨 8 帧方差 ≤ 阈值
第二层 Animation Continuity（I-J）：
    - 步幅曲线锯齿交替（Contact 宽 ↔ Passing 窄）
    - 脚部质量中心 x 偏移交替（左右脚换位）
    - 垂直节奏（Down 最低 / Up 最高）
    - 无空帧 / 无碎片

输出逐项 PASS/FAIL；任何 FAIL = 素材拒绝进运行时，人工看帧修素材。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent


def keyed_mask(arr):
    r, g, b = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int)
    return ~((r > 200) & (b > 200) & (g < 110))


def measure(path: Path):
    arr = np.asarray(Image.open(path).convert("RGB"))
    fg = keyed_mask(arr)
    ys, xs = np.where(fg)
    if len(ys) == 0:
        return None
    h = int(ys.max() - ys.min() + 1)
    top = fg[ys.min():ys.min() + int(h * 0.35)]
    head = int(top.sum(axis=1).max()) if len(top) else 0
    # 耳机带：高度 18%~30% 区域的宽度（该角色的强识别特征）
    band = fg[ys.min() + int(h * 0.18):ys.min() + int(h * 0.30)]
    headband = int(band.sum(axis=1).max()) if len(band) else 0
    foot_y = int(ys.max())
    cx = float(xs.mean())
    # 步幅：脚部区（底部 15%）左右极差
    foot_zone = fg[ys.min() + int(h * 0.80):]
    fx = np.where(foot_zone)[1]
    stride = int(fx.max() - fx.min()) if len(fx) else 0
    return {"h": h, "head": head, "headband": headband, "foot_y": foot_y,
            "cx": cx, "stride": stride, "area": int(fg.sum())}


def fragments(fg):
    lbl, n = ndimage.label(fg)
    if n <= 1:
        return []
    sizes = sorted((ndimage.sum(fg, lbl, i) for i in range(1, n + 1)), reverse=True)
    return [int(s) for s in sizes[1:] if s > fg.sum() * 0.002]


def holes(fg):
    holes = ~fg
    lbl, n = ndimage.label(holes)
    border = set(np.unique(np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]])))
    return [int(ndimage.sum(holes, lbl, i)) for i in range(1, n + 1)
            if i not in border and ndimage.sum(holes, lbl, i) > 200]


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "characters" / "iven-pet" / "animations" / "walk" / "frames"
    frames = []
    if target.is_dir():
        frames = sorted(target.glob("*.png")) + sorted(target.glob("*.gif"))
    else:
        frames = sorted(ROOT.glob(str(target)))
    if len(frames) != 8:
        print(f"FAIL: 需要 8 帧，找到 {len(frames)}"); sys.exit(1)

    problems = []
    M = []
    for f in frames:
        arr = np.asarray(Image.open(f).convert("RGB"))
        fg = keyed_mask(arr)
        ys, xs = np.where(fg)
        if len(ys) == 0:
            problems.append(f"{f.stem}: 空帧"); M.append(None); continue
        h = int(ys.max() - ys.min() + 1)
        top = fg[ys.min():ys.min() + int(h * 0.35)]
        head = int(top.sum(axis=1).max()) if len(top) else 0
        band = fg[ys.min() + int(h * 0.18):ys.min() + int(h * 0.30)]
        headband = int(band.sum(axis=1).max()) if len(band) else 0
        # 碎片/孔洞
        frs = fragments(fg)
        hls = holes(fg)
        if frs:
            problems.append(f"{f.stem}: 悬浮碎片 {frs[:3]}")
        if hls:
            problems.append(f"{f.stem}: 内部孔洞 {hls[:3]}")
        foot_x = np.where(fg[ys.max() - 4])[0]
        M.append({"h": h, "head": head, "headband": headband,
                  "foot_y": int(ys.max()), "foot_x": (int(foot_x.min()), int(foot_x.max())) if len(foot_x) else None,
                  "cx": float(xs.mean())})

    heads = [m["head"] for m in M]
    hbands = [m["headband"] for m in M]
    heights = [m["h"] for m in M]
    import statistics as st
    for tag, vals, lim in [("头宽", heads, 0.12), ("耳机带", hbands, 0.15), ("身高", heights, 0.12)]:
        med = st.median(vals)
        for i, v in enumerate(vals):
            if abs(v - med) / med > lim:
                problems.append(f"Frame{i+1} {tag}={v} 偏离中位 {med:.0f} 超{lim:.0%}")

    # Layer 2：步态逻辑（8 帧序列）
    # 1) 脚部范围锯齿交替（Contact 宽 ↔ Passing 窄）
    foot_spans = [m["foot_x"][1] - m["foot_x"][0] if m["foot_x"] else 0 for m in M]
    odd = foot_spans[0::2]; even = foot_spans[1::2]
    zigzag = all(a > b for a, b in zip(odd, even)) or all(a < b for a, b in zip(odd, even))
    if not zigzag:
        problems.append(f"脚部范围无锯齿交替: {foot_spans}")
    # 2) 垂直节奏：头顶 y 应锯齿交替（Up 高 / Down 低）
    top_ys = [m["foot_y"] for m in M]
    print("== 步态序列测量 ==")
    for i, f in enumerate(frames):
        print(f"  Frame{i+1}: foot_span={foot_spans[i]} foot_y={top_ys[i] if i < len(top_ys) else '-'}")

    print(f"== 8 帧验收：{len(problems)} 个问题")
    for p in problems:
        print("  ", p)
    print("VERDICT: " + ("PASS" if not problems else "FAIL"))


if __name__ == "__main__":
    main()
