"""collect_evidence · 从仓库真实素材测得结构化证据，供 Jev 决策。

用法：
    python tools/jev/collect_evidence.py                # 默认 walk 资产
    python tools/jev/collect_evidence.py -o out.json    # 写入文件

测量口径全部复用既有验收工具（tools/qa_walk8.py）的定义，不发明新标准：
    - 高度/头宽：可见像素 mask，top 35% 最大行宽 = 头宽
    - 碎片：非最大连通域且 > 0.2% 主域面积
    - 孔洞：封闭背景域 > 200px
    - leg_reposition：脚部跨度奇偶锯齿交替（qa_walk8 Layer2 同款）
    - phase_consistency：身高序列奇偶锯齿交替（Down 低 / Up 高）
    - fps_match：animation.json fps 与 pet.py 8 帧 av_walk 分支 round(1000/12) 交叉核对
"""
import json
import re
import statistics as st
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from qa_walk8 import fragments as find_fragments  # noqa: E402
from qa_walk8 import holes as find_holes  # noqa: E402

WALK_DIR = ROOT / "characters" / "iven-pet" / "animations" / "walk"
RUNTIME_DIR = ROOT / "frames3d"


def fg_mask(img: Image.Image) -> np.ndarray:
    """前景 mask：RGBA 用 alpha≥160（与运行时 on_canvas 二值化同口径），
    无 alpha 的品红键控画布用 qa_walk8.keyed_mask。"""
    if img.mode in ("RGBA", "LA", "PA"):
        arr = np.asarray(img.convert("RGBA"))
        return arr[..., 3] >= 160
    arr = np.asarray(img.convert("RGB"))
    r, g, b = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int)
    return ~((r > 200) & (b > 200) & (g < 110))


def measure_frame(path: Path) -> dict:
    fg = fg_mask(Image.open(path))
    ys, xs = np.where(fg)
    if len(ys) == 0:
        return {"empty": True}
    h = int(ys.max() - ys.min() + 1)
    top = fg[ys.min():ys.min() + int(h * 0.35)]
    head = int(top.sum(axis=1).max()) if len(top) else 0
    # 步幅：脚底基线行（同 qa_walk8：ys.max()-4 单行）左右跨度
    foot_row = fg[ys.max() - 4]
    fx = np.where(foot_row)[0]
    stride = int(fx.max() - fx.min()) if len(fx) else 0
    # 标注徽章：落在底部 12% 带内的非主连通域（GPT 历史坑：图下方的 "1 Contact" 标签）
    lbl_area = fg.sum()
    comps = []
    from scipy import ndimage
    lbl, n = ndimage.label(fg)
    if n > 1:
        sizes = [(i, int(ndimage.sum(fg, lbl, i))) for i in range(1, n + 1)]
        sizes.sort(key=lambda t: -t[1])
        for i, s in sizes[1:]:
            if s <= lbl_area * 0.002:
                continue
            iy, ix = np.where(lbl == i)
            comps.append((i, s, int(iy.min()), int(iy.max())))
    badge_band = ys.min() + int(h * 0.88)
    badges = sum(1 for _, _, y0, _ in comps if y0 >= badge_band)
    frag = len([1 for _, _, y0, _ in comps if y0 < badge_band])
    return {"empty": False, "h": h, "head": head, "stride": stride,
            "badges": badges, "fragments": frag,
            "holes": len(find_holes(fg))}


def zigzag(values) -> bool:
    odd, even = values[0::2], values[1::2]
    return (all(a > b for a, b in zip(odd, even))
            or all(a < b for a, b in zip(odd, even)))


def cv(values) -> float:
    mean = st.mean(values)
    return round(st.pstdev(values) / mean, 4) if mean else 1.0


def collect() -> dict:
    anim = json.loads((WALK_DIR / "animation.json").read_text(encoding="utf-8"))
    frames = sorted((WALK_DIR / "frames").glob("walk_*.png"))

    M = [measure_frame(f) for f in frames]
    heights = [m["h"] for m in M if not m.get("empty")]
    heads = [m["head"] for m in M if not m.get("empty")]
    strides = [m["stride"] for m in M if not m.get("empty")]

    # 运行时 GIF 盘点（左右镜像各 8）
    lefts = sorted(RUNTIME_DIR.glob("av_walk_l_*.gif"))
    rights = sorted(RUNTIME_DIR.glob("av_walk_r_*.gif"))
    gif_load = True
    for gif in lefts + rights:
        try:
            with Image.open(gif) as im:
                im.verify()
        except Exception:
            gif_load = False

    # fps_match：animation.json 的 fps 与 pet.py 8 帧分支 round(1000/12) 交叉核对
    pet_src = (ROOT / "pet.py").read_text(encoding="utf-8")
    runtime_ms = re.search(r"self\._walk_period\[d\] = round\(1000 / (\d+)\)", pet_src)
    fps_match = bool(runtime_ms) and int(runtime_ms.group(1)) == anim.get("fps")

    holes_total = sum(m["holes"] for m in M if not m.get("empty"))
    badges_total = sum(m["badges"] for m in M if not m.get("empty"))
    frag_total = sum(m["fragments"] for m in M if not m.get("empty"))

    return {
        "project": "desktop-pet/iven-pet walk",
        "asset": {
            "walk_frames_total": len(frames),
            "left_frames": len(lefts),
            "right_frames": len(rights),
            "fps": anim.get("fps", 0),
        },
        "visual_quality": {
            "height_cv": cv(heights),
            "head_width_cv": cv(heads),
            "badges": badges_total,
            "holes": holes_total,
            "fragments": frag_total,
        },
        "motion_quality": {
            "leg_reposition": zigzag(strides),
            "phase_consistency": zigzag(heights),
        },
        "runtime": {
            "gif_load": gif_load and len(lefts) == 8 and len(rights) == 8,
            "fps_match": fps_match,
            # 语义：本采集过程中帧/GIF 加载零异常；完整 GUI 冒烟由 tools/smoke.py 负责
            "runtime_error": not (gif_load and all(not m.get("empty") for m in M)),
        },
        "_measured": {
            "frames": [f.name for f in frames],
            "heights": heights,
            "head_widths": heads,
            "strides": strides,
        },
    }


def main():
    out = None
    if "-o" in sys.argv:
        out = Path(sys.argv[sys.argv.index("-o") + 1])
    ev = collect()
    text = json.dumps(ev, indent=2, ensure_ascii=False)
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"evidence written → {out}")
    print(text)


if __name__ == "__main__":
    main()
