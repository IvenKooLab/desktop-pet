"""import_action · 新动作素材一键打包（原始帧 → assets/iven-v2/actions 的 sheet 包）。

输入一个帧目录（PNG 序列，绿幕/品红底或已透明），产出与 little-breaks 同构的
<name>.png + <name>.json 动作 sheet：

    python tools/import_action.py --frames-dir pet-work/raw/yawn --name YAWN
    python tools/import_action.py --frames-dir ... --name WAVE_BYE --ms 180
    python tools/import_action.py --frames-dir ... --key magenta   # 默认自动检测

固定画幅导入：标注头宽、地面坐标与身体/道具颜色区域，使用同一相机标定。
不按逐帧包围盒裁切或对齐，不自动缩边。保留跳跃高度和左右位移。
输出 sheet/JSON、QA 报告、深浅背景静态与动画预览；所有输出仅为待验收候选。

依赖 Pillow（构建期工具；运行时仍纯标准库）。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter
from action_quality import inspect, render_review, validate_annotations

ROOT = Path(__file__).resolve().parent.parent
PAD = 6                    # sheet 单元格内边距
PALETTE_WARN = 40.0        # 与 idle_0 均色的欧氏距离警告阈值


def detect_key(frame):
    """看四角像素判断底色：绿 / 品红 / 无（已透明）。"""
    width, height = frame.size
    corners = [frame.getpixel(p) for p in ((1, 1), (width - 2, 1),
                                           (1, height - 2), (width - 2, height - 2))]
    solid = [c[:3] for c in corners if len(c) >= 3 and (len(c) < 4 or c[3] >= 192)]
    if not solid:
        return "none"
    r, g, b = (sum(ch) / len(solid) for ch in zip(*solid))
    if g > 140 and g > r * 1.4 and g > b * 1.4:
        return "green"
    if r > 140 and b > 140 and g < r * 0.7 and g < b * 0.7:
        return "magenta"
    return "none"


def key_out(frame, key):
    """色键 → alpha。返回 (RGBA 帧, 是否做了键控)。"""
    frame = frame.convert("RGBA")
    if key == "none":
        return frame, False
    r, g, b, a = frame.split()
    if key == "green":
        mr = r.point(lambda v: 255 if v < 130 else 0)
        mg = g.point(lambda v: 255 if v > 140 else 0)
        mb = b.point(lambda v: 255 if v < 130 else 0)
    else:                                        # magenta
        mr = r.point(lambda v: 255 if v > 150 else 0)
        mg = g.point(lambda v: 255 if v < 110 else 0)
        mb = b.point(lambda v: 255 if v > 150 else 0)
    background = ImageChops.multiply(ImageChops.multiply(mr, mg), mb)
    frame.putalpha(ImageChops.multiply(a, ImageChops.invert(background)))
    return frame, True


def content_bbox(frame):
    """alpha>8 的内容包围盒；全空返回 None。"""
    alpha = frame.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    return alpha.getbbox()


def build_sheet(frames_dir, name, key, erode, ms, durations, out_dir,
                annotations=None, reference_profile=None):
    paths = sorted(p for p in Path(frames_dir).iterdir() if p.suffix.lower() == ".png")
    if not paths:
        raise ValueError("帧目录没有 PNG")
    if name != name.upper() or not name.isidentifier():
        raise ValueError("动作名需为大写标识符")
    durations = [ms] * len(paths) if durations is None else durations
    if len(durations) != len(paths) or any(type(d) is not int or d <= 0 for d in durations):
        raise ValueError("每帧必须有正整数毫秒时长")
    if annotations is None or reference_profile is None:
        raise ValueError("需要 --annotations 和 --reference-profile；不再按最高帧猜测比例")
    meta = json.loads(Path(annotations).read_text())
    profile = json.loads(Path(reference_profile).read_text())
    frames, keyed_any, original_alphas = [], False, []
    size = None
    for path in paths:
        frame = Image.open(path).convert("RGBA")
        if size is not None and frame.size != size:
            raise ValueError("所有帧必须是相同画幅；禁止逐帧裁切输入")
        size = frame.size
        frame, did = key_out(frame, key if key != "auto" else detect_key(frame))
        keyed_any |= did
        original_alphas.append(frame.getchannel("A").getbbox())
        if did and erode:
            frame.putalpha(frame.getchannel("A").filter(ImageFilter.MinFilter(3)))
        if content_bbox(frame) is None:
            raise ValueError(f"{path.name}: 抠像后没有内容")
        frames.append((path, frame))
    ref_index = validate_annotations(frames, meta)
    anchor = meta["frames"][paths[ref_index].name]
    ref_path = (Path(reference_profile).parent / profile["source"]).resolve()
    reference = Image.open(ref_path).convert("RGBA")
    if type(profile.get("head_width")) not in (int, float) or not 0 < profile["head_width"] <= reference.width:
        raise ValueError("参考角色 head_width 必须为画幅内的正数")
    factor = profile["head_width"] / anchor["head_width"]
    # Whole source canvases stay intact. One reference anchor and scale apply to ALL poses.
    w, h = size
    sheet = Image.new("RGBA", (w * len(frames), h), (0, 0, 0, 0))
    for index, (_, frame) in enumerate(frames):
        sheet.alpha_composite(frame, (index * w, 0))
    if type(profile.get("body_height")) not in (int, float) or not 0 < profile["body_height"] <= reference.height:
        raise ValueError("参考角色 body_height 必须为画幅内的正数")
    report = inspect(frames, meta, reference, profile["regions"],
                     profile["body_height"] / profile["head_width"])
    if erode:
        report["findings"].append("Explicit erosion enabled: inspect lost hair/fabric alpha")
        report["automatic_checks_pass"] = False
    # Detect clipping after the SAME transform used by the runtime exporter.
    for path, frame in frames:
        box = content_bbox(frame)
        target = [100 + (box[0] - anchor["anchor_x"]) * factor,
                  193 + (box[1] - anchor["ground_y"]) * factor,
                  100 + (box[2] - anchor["anchor_x"]) * factor,
                  193 + (box[3] - anchor["ground_y"]) * factor]
        if target[0] < 0 or target[1] < 0 or target[2] > 200 or target[3] > 200:
            report["findings"].append(f"{path.name}: calibrated pose clips runtime 200px canvas")
            report["automatic_checks_pass"] = False
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = name.lower() + "-sheet"
    sheet_path = out_dir / (stem + ".png")
    sheet.save(sheet_path)
    spec = {"source": sheet_path.name,
            "sha256": hashlib.sha256(sheet_path.read_bytes()).hexdigest(),
            "columns": [w * i for i in range(len(frames) + 1)], "rows": [0, h],
            "centers": [w * i + anchor["anchor_x"] for i in range(len(frames))],
            "baselines": [anchor["ground_y"]], "scale": factor,
            "actions": [{"name": name, "durations": durations}],
            "review": {"approved": False, "report": stem + "-qa.json"}}
    (out_dir / (stem + ".json")).write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    report["source_sha256"] = spec["sha256"]
    report["reference_sha256"] = hashlib.sha256(ref_path.read_bytes()).hexdigest()
    report["calibration"] = {"scale": factor, "anchor_x": anchor["anchor_x"],
                             "ground_y": anchor["ground_y"], "method": "shared-head-width-and-fixed-ground"}
    (out_dir / (stem + "-qa.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    render_review(frames, durations, out_dir, stem)
    print(json.dumps({"ok": True, "approved": False,
                      "automatic_checks_pass": report["automatic_checks_pass"],
                      "findings": report["findings"], "sheet": str(sheet_path)}, ensure_ascii=False))
    return spec, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True,
                        help="原始帧目录（PNG 序列）")
    parser.add_argument("--name", required=True, help="动作名（大写标识符，如 WAVE_BYE）")
    parser.add_argument("--key", choices=["auto", "green", "magenta", "none"],
                        default="auto", help="底色类型（默认按四角自动检测）")
    parser.add_argument("--erode", type=int, choices=(0, 1), default=0,
                        help="显式启用色键后缩边（默认关闭，保护绒毛/发丝）")
    parser.add_argument("--ms", type=int, default=160, help="统一每帧毫秒（默认 160）")
    parser.add_argument("--durations", default=None,
                        help="逐帧毫秒，逗号分隔（优先于 --ms）")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "pet-work/import",
                        help="输出目录（默认 pet-work/import，验收后再发布）")
    parser.add_argument("--annotations", type=Path, required=True, help="逐帧身体标尺、地面与分部位区域")
    parser.add_argument("--reference-profile", type=Path, required=True, help="已批准参考图的标尺与分部位区域")
    args = parser.parse_args()
    durations = ([int(v) for v in args.durations.split(",")]
                 if args.durations else None)
    build_sheet(args.frames_dir, args.name, args.key, args.erode,
                args.ms, durations, args.out, args.annotations, args.reference_profile)


if __name__ == "__main__":
    main()
