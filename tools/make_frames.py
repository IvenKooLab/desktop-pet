"""素材预处理：把 460×460 头像加工成桌宠帧（GIF）。

用法（需 Pillow）：
    python tools/make_frames.py assets/avatar_raw.png

产出：
    frames/pet.gif        128×128 主体帧（抠背景 + 保留贴纸白边）
    frames/pet_small.gif  96×96 小尺寸版
构建期依赖 Pillow；运行时（pet.py）零第三方依赖。
"""
import sys
from pathlib import Path

from PIL import Image


def remove_bg(img: Image.Image, tol: int = 42) -> Image.Image:
    """按四角平均色抠背景，返回 RGBA。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(p) for p in [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]]
    br = sum(c[0] for c in corners) // 4
    bg = sum(c[1] for c in corners) // 4
    bb = sum(c[2] for c in corners) // 4
    out = rgb.convert("RGBA")
    px = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if abs(r - br) + abs(g - bg) + abs(b - bb) < tol * 3:
                px[x, y] = (r, g, b, 0)
    return out


def main(src: str) -> None:
    out_dir = Path(__file__).resolve().parents[1] / "frames"
    out_dir.mkdir(exist_ok=True)

    img = Image.open(src).convert("RGB")
    cut = remove_bg(img)
    # 收紧到内容包围盒，四周留 4px 呼吸边
    bbox = cut.getbbox()
    cut = cut.crop(bbox)
    cut = cut.resize((128, 128), Image.LANCZOS)

    # 贴上品红衬底（tkinter 运行时用 -transparentcolor 抠掉）
    for name, side in (("pet.gif", 128), ("pet_small.gif", 96)):
        canvas = Image.new("RGB", (side + 8, side + 8), (255, 0, 255))
        actor = cut.resize((side, side), Image.LANCZOS).convert("RGB")
        canvas.paste(actor, (4, 4))
        canvas.save(out_dir / name, format="GIF")
        print(f"{out_dir / name}  {canvas.size}")

    print("frames ready.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "assets/avatar_raw.png")
