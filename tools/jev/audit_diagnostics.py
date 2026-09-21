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
    """C. 导入真实 builder（tools/_build_av_walk.py）复算构建落位，与交付 GIF 对比。
    证明：接地线逐帧恒定（F2 已修）且内容不越画布底（F1 已修）。
    直接 import builder 而非复制其算法，避免诊断与实现漂移。"""
    sys.path.insert(0, str(REPO / "tools"))
    import _build_av_walk as builder

    SIZE, FOOT_Y = builder.SIZE, builder.FOOT_Y
    s = builder.TARGET_H / builder.REF_H
    rows = []
    for i in range(1, 9):
        im = Image.open(PNG_DIR / f"walk_0{i}.png").convert("RGBA")
        a = np.asarray(im)
        fg = a[..., 3] > 96
        ys, xs = np.where(fg)
        im = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        a = np.asarray(im).copy()
        a[..., 3] = np.where(a[..., 3] >= 128, 255, 0).astype(np.uint8)
        fg = a[..., 3] > 0
        sole = builder.sole_row(a, fg)
        py = FOOT_Y - sole
        rows.append({"frame": f"walk_0{i}", "scaled_h": int(im.height), "sole": sole,
                     "py": int(py), "content_bottom": int(py + im.height - 1),
                     "clipped": py + im.height - 1 > SIZE - 1})
    gif_v = diagnose_gif_vertical()
    return {
        "per_frame": rows,
        "ground_line_series": gif_v["per_frame"] and
                              [r["sole_y"] for r in gif_v["per_frame"]],
        "py_series": [r["py"] for r in rows],
        "ground_line_jitter_px": max(r["content_bottom"] for r in rows)
                                 - min(r["content_bottom"] for r in rows),
        "clipped_frames": sum(1 for r in rows if r["clipped"]),
    }


def diagnose_size_consistency():
    """D. F4 尺寸一致性取证（只读，不产生产物、不改生产 builder）。

    1) 全族 GIF 测量：各动画族的人物高/接地线/内容宽（runtime 1:1 显示，
       pet.py 无 zoom/subsample → GIF 像素 = 上屏像素）。
    2) REF_H=874 来源：原始 Sheet（walk/source/walk_sheet_8f.png）人物 bbox
       @ mx<245 = 874px —— REF_H 量在"Sheet 人物（含边界晕环）"上，
       而 builder 消费的是抠图切图（762~764px）→ 单位错配。
    3) 头身比同源性：idle vs av_walk 的 top35% 头宽/身高比（同角色验证）。
    4) A/B 模拟（纯内存，经真实 builder 数学）：
       A=现状 REF_H=874；B=REF_H=当前切图最高身高（alpha>96 口径）。
       各自输出：渲染高/foot line/top 余量/宽/是否裁切/与 idle 盒差。
    """
    sys.path.insert(0, str(REPO / "tools"))
    import _build_av_walk as builder
    from qa_walk8 import keyed_mask

    fam_files = {}
    for f in sorted(GIF_DIR.glob("*.gif")):
        s = f.stem
        if s.startswith("av_walk"):
            fam = s[:-3]
        elif s.startswith("fast") or s.startswith("walk"):
            fam = s[:6]
        else:
            fam = s.split("_")[0]
        fam_files.setdefault(fam, []).append(f)

    def gif_box(path):
        arr = np.asarray(Image.open(path).convert("RGB"))
        fg = keyed_mask(arr)
        ys, xs = np.where(fg)
        return {"h": int(ys.max() - ys.min() + 1), "foot": int(ys.max()),
                "top": int(ys.min()), "w": int(xs.max() - xs.min() + 1)}

    families = {}
    for fam, files in sorted(fam_files.items()):
        boxes = [gif_box(f) for f in files]
        families[fam] = {
            "n": len(files),
            "h": sorted({b["h"] for b in boxes}),
            "foot": sorted({b["foot"] for b in boxes}),
            "w_max": max(b["w"] for b in boxes),
            "top": sorted({b["top"] for b in boxes}),
        }

    # REF_H 来源：Sheet 人物 bbox（含晕环口径）
    sheet = PNG_DIR.parent / "source" / "walk_sheet_8f.png"
    sheet_ref = None
    if sheet.exists():
        a = np.asarray(Image.open(sheet).convert("RGB")).astype(int)
        mx = a.max(axis=2)
        n, sw = 8, a.shape[1] / 8
        hs = []
        for i in range(n):
            ys, _ = np.where((mx < 245)[:, int(i * sw):int((i + 1) * sw)])
            hs.append(int(ys.max() - ys.min() + 1))
        sheet_ref = {"per_strip": hs, "max": max(hs),
                     "note": "REF_H=874 = Sheet 人物 bbox(mx<245) 最高值；切图后剩 762~764"}

    # 头身比同源性：同 mask 同口径测头宽/身高
    def head_ratio(gif_name):
        arr = np.asarray(Image.open(GIF_DIR / gif_name).convert("RGB"))
        fg = keyed_mask(arr)
        ys, _ = np.where(fg)
        h = int(ys.max() - ys.min() + 1)
        band = fg[ys.min():ys.min() + int(h * 0.35)]
        head = int(band.sum(axis=1).max())
        return round(head / h, 4)

    ratios = {name: head_ratio(name) for name in
              ("idle_0.gif", "fall_0.gif", "av_walk_r_00.gif", "av_walk_r_04.gif")}

    # A/B 模拟：走真实 builder 数学（裁切>96 → 缩放 → 二值化≥128 → 内容末行锚）
    def simulate(ref_h):
        s = builder.TARGET_H / ref_h
        out = []
        for i in range(1, 9):
            im = Image.open(PNG_DIR / f"walk_0{i}.png").convert("RGBA")
            a = np.asarray(im)
            fg = a[..., 3] > 96
            ys, xs = np.where(fg)
            im = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))),
                           Image.LANCZOS)
            a = np.asarray(im).copy()
            a[..., 3] = np.where(a[..., 3] >= 128, 255, 0).astype(np.uint8)
            fg = a[..., 3] > 0
            ys, xs = np.where(fg)
            sole = builder.sole_row(a, fg)
            py = builder.FOOT_Y - sole
            out.append({"frame": i - 1, "h": int(im.height),
                        "top": int(py + int(ys.min())), "foot": int(builder.FOOT_Y),
                        "w": int(xs.max() - xs.min() + 1),
                        "clipped": bool(py + im.height - 1 > 199 or py + int(ys.min()) < 0)})
        return {
            "ref_h": ref_h, "scale": round(s, 5), "frames": out,
            "h_series": sorted({o["h"] for o in out}),
            "top_series": [o["top"] for o in out],
            "w_max": max(o["w"] for o in out),
            "any_clip": any(o["clipped"] for o in out),
        }

    src_heights = []
    for i in range(1, 9):
        a = np.asarray(Image.open(PNG_DIR / f"walk_0{i}.png").convert("RGBA"))
        ys, _ = np.where(a[..., 3] > 96)
        src_heights.append(int(ys.max() - ys.min() + 1))
    ref_b = max(src_heights)

    return {
        "families": families,
        "sheet_ref_height": sheet_ref,
        "head_height_ratio": ratios,
        "sim_A_current_REF_H_874": simulate(874),
        "sim_B_ref_h_current_max_cut": simulate(ref_b),
        "sim_B_ref_h_value": ref_b,
        "runtime_scaling": "pet.py 无 zoom/subsample/resize —— GIF 1:1 上屏",
        "system_fit_box": "tools/make_frames3d.py:36 FIT_H,FIT_W = 176,168",
    }

if __name__ == "__main__":
    out = {
        "A_head_band_decomposition": diagnose_head_bands(),
        "B_delivered_gif_vertical": diagnose_gif_vertical(),
        "C_builder_replication": diagnose_builder_replication(),
        "D_size_consistency": diagnose_size_consistency(),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
