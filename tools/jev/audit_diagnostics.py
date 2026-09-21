"""audit_diagnostics · Decision Boundary Audit 取证脚本（只读，不修改任何标准/素材）。

取证两项：
  A. head_width_cv 方差来源分解：把 qa_walk8 的 top-35% 头宽带拆成
     颅顶带 [0,10%) / 额带 [10%,18%) / 耳机带 [18%,30%)（qa_walk8 耳机带同口径），
     逐带算跨 8 帧 CV。若下部带 CV 大、颅顶/耳机带 CV 小，
     则方差来自发丝摆动而非头部结构 → MeasurementArtifact 证据。
  B. 交付 GIF 逐帧垂直位移：对入库的 frames3d/av_walk_r_*.gif 测
     top_y（头顶）/ sole_y（脚底基线）。若 sole 恒定且 top 恒定，
     则交付动画不含垂直 bounce → phase_consistency 事实证据。

用法：python tools/jev/audit_diagnostics.py
输出：JSON（stdout）
"""
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from qa_walk8 import keyed_mask  # noqa: E402

PNG_DIR = REPO / "characters" / "iven-pet" / "animations" / "walk" / "frames"
GIF_DIR = REPO / "frames3d"


def cv(vals):
    mean = st.mean(vals)
    return round(st.pstdev(vals) / mean, 4) if mean else 0.0


def band_max_width(fg, y0, y1):
    band = fg[y0:y1]
    return int(band.sum(axis=1).max()) if len(band) else 0


def diagnose_head_bands():
    per_frame = []
    for f in sorted(PNG_DIR.glob("walk_*.png")):
        img = Image.open(f)
        arr = np.asarray(img.convert("RGBA"))
        fg = arr[..., 3] >= 160
        ys, _ = np.where(fg)
        h = int(ys.max() - ys.min() + 1)
        y_top = int(ys.min())
        bands = {
            "skull_0_10": band_max_width(fg, y_top, y_top + int(h * 0.10)),
            "forehead_10_18": band_max_width(fg, y_top + int(h * 0.10), y_top + int(h * 0.18)),
            "earband_18_30": band_max_width(fg, y_top + int(h * 0.18), y_top + int(h * 0.30)),
            "head_0_35": band_max_width(fg, y_top, y_top + int(h * 0.35)),
        }
        per_frame.append({"frame": f.name, "h": h, **bands})
    series = {k: [r[k] for r in per_frame] for k in
              ("skull_0_10", "forehead_10_18", "earband_18_30", "head_0_35")}
    return {
        "per_frame": per_frame,
        "cv_per_band": {k: cv(v) for k, v in series.items()},
        "values_per_band": series,
    }


def diagnose_gif_vertical():
    rows = []
    for f in sorted(GIF_DIR.glob("av_walk_r_*.gif")):
        arr = np.asarray(Image.open(f).convert("RGB"))
        fg = keyed_mask(arr)
        ys, _ = np.where(fg)
        rows.append({"frame": f.name, "top_y": int(ys.min()),
                     "sole_y": int(ys.max()), "h": int(ys.max() - ys.min() + 1)})
    tops = [r["top_y"] for r in rows]
    soles = [r["sole_y"] for r in rows]
    return {
        "per_frame": rows,
        "top_y_range": [min(tops), max(tops)],
        "sole_y_range": [min(soles), max(soles)],
        "top_y_constant": len(set(tops)) == 1,
        "sole_y_constant": len(set(soles)) == 1,
    }


def diagnose_builder_replication():
    """C. 用当前 builder 代码+_build_av_walk.py 参数在内存复算构建结果，
    与交付 GIF 对比。用于证明：底部裁切（py+scaled_h > 画布底）与
    sole 检测抖动（py 逐帧不一致，违反其 docstring"脚底不上下跳"承诺）。"""
    sys.path.insert(0, str(REPO / "tools"))
    from qa_walk8 import keyed_mask  # noqa: F401  (保持与交付 GIF 同 mask 口径)

    SIZE, FOOT_Y, REF_H = 200, 194, 874

    def sole_row(arr, fg):
        h = arr.shape[0]
        band = fg[int(h * 0.75):]
        return int(h * 0.75) + int(band.sum(axis=1).argmax())

    rows = []
    for i in range(1, 9):
        im = Image.open(PNG_DIR / f"walk_0{i}.png").convert("RGBA")
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys, xs = np.where(fg)
        im = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        s = 176 / REF_H
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys2, _ = np.where(fg)
        sole = sole_row(a, fg)
        py = FOOT_Y - sole
        rows.append({"frame": f"walk_0{i}", "scaled_h": int(im.height), "sole": sole,
                     "py": int(py), "content_bottom": int(py + im.height),
                     "clipped": py + im.height > SIZE - 1})
    gif_soles = diagnose_gif_vertical()
    return {
        "per_frame": rows,
        "py_series": [r["py"] for r in rows],
        "py_jitter_px": max(r["py"] for r in rows) - min(r["py"] for r in rows),
        "scaled_h_series": [r["scaled_h"] for r in rows],
        "all_clipped": all(r["clipped"] for r in rows),
        "gif_sole_y_constant_at_canvas_edge": gif_soles["sole_y_constant"],
    }


if __name__ == "__main__":
    out = {
        "A_head_band_decomposition": diagnose_head_bands(),
        "B_delivered_gif_vertical": diagnose_gif_vertical(),
        "C_builder_replication": diagnose_builder_replication(),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
