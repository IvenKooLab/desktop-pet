"""import_action · 新动作素材一键打包（原始帧 → assets/iven-v2/actions 的 sheet 包）。

输入一个帧目录（PNG 序列，绿幕/品红底或已透明），产出与 little-breaks 同构的
<name>.png + <name>.json 动作 sheet：

    python tools/import_action.py --frames-dir pet-work/raw/yawn --name YAWN
    python tools/import_action.py --frames-dir ... --name WAVE_BYE --ms 180
    python tools/import_action.py --frames-dir ... --key magenta   # 默认自动检测

步骤（均可关）：
    1. 色键抠像（自动检测绿幕/品红；--key none 跳过，要求帧已带 alpha）
    2. alpha 边缘收缩 1px（--erode 0 关闭；只对色键过的帧默认开启，去残边）
    3. 自动裁切到角色包围盒，量脚底线/中心
    4. 统一缩放：最高帧对齐 idle_0 的角色高度（两端比例一致的硬约束）
    5. 排成单行 sheet，写 <name>.png + <name>.json（含 sha256）
    6. 配色体检：与 idle_0 的不透明像素均色对比，偏差大即警告（不阻断）

产物默认落在 pet-work/import/（本地过程目录，不直接发布）；目测验收后
mv 进 assets/iven-v2/actions/，再跑全量导出与注册（见 docs/ASSET_RECIPE.md）。

依赖 Pillow（构建期工具；运行时仍纯标准库）。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PAD = 6                    # sheet 单元格内边距
PALETTE_WARN = 40.0        # 与 idle_0 均色的欧氏距离警告阈值


def detect_key(frame):
    """看四角像素判断底色：绿 / 品红 / 无（已透明）。"""
    width, height = frame.size
    corners = [frame.getpixel(p) for p in ((1, 1), (width - 2, 1),
                                           (1, height - 2), (width - 2, height - 2))]
    solid = [c[:3] for c in corners if len(c) >= 3]
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


def mean_color(frame):
    """不透明像素均色（R,G,B）。"""
    return frame.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))[:3]


def build_sheet(frames_dir, name, key, erode, ms, durations, out_dir):
    paths = sorted(p for p in Path(frames_dir).iterdir()
                   if p.suffix.lower() == ".png")
    if not paths:
        raise SystemExit(f"帧目录没有 PNG：{frames_dir}")
    if name != name.upper() or not name.isidentifier():
        raise SystemExit("动作名需为大写标识符（如 WAVE_BYE）")
    cropped = []
    keyed_any = False
    for path in paths:
        frame = Image.open(path)
        key_kind = key if key != "auto" else detect_key(frame)
        frame, did = key_out(frame, key_kind)
        keyed_any = keyed_any or did
        if did and erode:
            frame.putalpha(frame.getchannel("A").filter(ImageFilter.MinFilter(3)))
        box = content_bbox(frame)
        if box is None:
            raise SystemExit(f"{path.name} 抠像后没有内容，检查 --key 设置")
        cropped.append((path, frame.crop(box)))
    # 目标角色高度 = idle_0 的内容高度（角色比例一致的硬约束）
    reference = Image.open(ROOT / "frames3d/idle_0.png").convert("RGBA")
    ref_box = content_bbox(reference)
    target_h = ref_box[3] - ref_box[1]
    tallest = max(box.height for _, box in cropped)
    factor = round(target_h / tallest, 3)
    # 单行布局：单元格 = 最高帧 + 上下留白，角色底对齐（脚底线一致）
    cell_w = max(box.width for _, box in cropped) + PAD * 2
    cell_h = tallest + PAD * 2
    sheet = Image.new("RGBA", (cell_w * len(cropped), cell_h), (0, 0, 0, 0))
    columns, centers = [0], []
    for index, (_, box) in enumerate(cropped):
        x0 = index * cell_w
        sheet.alpha_composite(box, (x0 + (cell_w - box.width) // 2,
                                    cell_h - PAD - box.height))
        columns.append(x0 + cell_w)
        centers.append(x0 + cell_w // 2)
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = out_dir / f"{name.lower()}-sheet.png"
    sheet.save(sheet_path)
    # 配色体检（对照 idle_0 的不透明均色；只警告不阻断，人工把关造型）
    ref_mean = mean_color(reference.crop(ref_box))
    for path, box in cropped:
        mean = mean_color(box)
        delta = sum((a - b) ** 2 for a, b in zip(mean, ref_mean)) ** 0.5
        if delta > PALETTE_WARN:
            print(f"[配色警告] {path.name} 与 idle_0 均色偏差 {delta:.0f}"
                  f"（> {PALETTE_WARN:.0f}），人工核对后再发布", file=sys.stderr)
    if not durations:
        durations = [ms] * len(cropped)
    if len(durations) != len(cropped):
        raise SystemExit(f"--durations 需要 {len(cropped)} 个值")
    spec = {
        "source": sheet_path.name,
        "sha256": hashlib.sha256(sheet_path.read_bytes()).hexdigest(),
        "columns": columns,
        "rows": [0, cell_h],
        "centers": centers,
        "baselines": [cell_h - PAD],
        "scale": factor,
        "actions": [{"name": name, "durations": durations}],
    }
    spec_path = out_dir / f"{name.lower()}-sheet.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "frames": len(cropped),
        "keyed": keyed_any,
        "scale": factor,
        "char_height_px": round(tallest * factor),
        "sheet": str(sheet_path),
        "spec": str(spec_path),
        "next": [
            "1. 目测 sheet：角色比例/配色/透明边缘是否与 Iven 一致",
            "2. 通过后把两个文件 mv 进 assets/iven-v2/actions/",
            "3. 全量导出（需 Pillow）：python tools/export_iven_v2.py",
            "4. 注册：animation_behaviors(.json/.py DEFAULT_ACTIONS) + "
            "pet.py 菜单与状态分支 + IvenPet.swift 菜单/ActionDeck/BehaviorPolicy",
            "5. 回归：python -m unittest discover -s tests && "
            "zsh tools/build_macos.sh && IvenPet --self-test",
        ],
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True,
                        help="原始帧目录（PNG 序列）")
    parser.add_argument("--name", required=True, help="动作名（大写标识符，如 WAVE_BYE）")
    parser.add_argument("--key", choices=["auto", "green", "magenta", "none"],
                        default="auto", help="底色类型（默认按四角自动检测）")
    parser.add_argument("--erode", type=int, choices=(0, 1), default=1,
                        help="色键后 alpha 边缘收缩 1px（默认开）")
    parser.add_argument("--ms", type=int, default=160, help="统一每帧毫秒（默认 160）")
    parser.add_argument("--durations", default=None,
                        help="逐帧毫秒，逗号分隔（优先于 --ms）")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "pet-work/import",
                        help="输出目录（默认 pet-work/import，验收后再发布）")
    args = parser.parse_args()
    durations = ([int(v) for v in args.durations.split(",")]
                 if args.durations else None)
    build_sheet(args.frames_dir, args.name, args.key, args.erode,
                args.ms, durations, args.out)


if __name__ == "__main__":
    main()
