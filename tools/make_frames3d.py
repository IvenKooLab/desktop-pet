"""素材预处理 v3：从豆包 3D 手办设定图切出桌宠全套动作帧。

输入 assets/src/：
    views_clean.png   正/侧/背三视图（干净版）
    actions.png       6 姿势表情Sheet（上排：张手开心 / 跳跃；下排：眨眼害羞 / 挥手 / 举板欢呼 / 抱板微笑）

流程：
    1) 局部梯度洪泛抠背景（渐变棚拍背景免疫；软阴影被渐进吃掉）
    2) 连通域分框切片
    3) 去蓝边（边缘像素颜色替换为内部色）+ 1px 内缩硬边
    4) 拼贴预览 assets/cut/preview.png（人工检查）—— python make_frames3d.py
    5) 合成 200x200 动作帧 GIF → frames3d/   —— python make_frames3d.py --frames

构建期依赖 Pillow/numpy/scipy；运行时（pet.py）零第三方依赖。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"
CUT = ROOT / "assets" / "cut"
FRAMES = ROOT / "frames3d"

CANVAS = 200          # 运行时画布
FOOT_Y = 194          # 脚底线
FIT_H, FIT_W = 176, 168   # 单帧角色适配盒

# --- 1) 抠背景 -------------------------------------------------------------
def flood_bg(rgb: np.ndarray, tol: int = 13) -> np.ndarray:
    """从四边洪泛：相邻像素色差 < tol 才扩散，另加颜色闸门。

    实测：棚拍背景 G-R ≥ +14（青蓝），角色全身 G-R ≤ 0（紫/白/肤）——
    G-R/B-G 双通道规则可硬分背景；软阴影两条件都过，会被渐进吃掉。
    """
    r = rgb[..., 0].astype(int); g = rgb[..., 1].astype(int); b = rgb[..., 2].astype(int)
    color_bg = (g - r >= 8) & (b - g >= 5)
    d = np.full(rgb.shape[:2], 255, np.int32)
    dl = np.abs(np.diff(rgb, axis=1)).sum(2)          # (x-1,x)
    dr = np.abs(np.diff(rgb, axis=1)).sum(2)
    du = np.abs(np.diff(rgb, axis=0)).sum(2)
    dd = np.abs(np.diff(rgb, axis=0)).sum(2)
    d[:, 1:] = np.minimum(d[:, 1:], dl); d[:, :-1] = np.minimum(d[:, :-1], dr)
    d[1:, :] = np.minimum(d[1:, :], du); d[:-1, :] = np.minimum(d[:-1], dd)
    passable = color_bg & (d < tol)
    seed = np.zeros(rgb.shape[:2], bool)
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    bg = ndimage.binary_propagation(seed & passable, mask=passable)
    return ~bg

def defringe(rgba: np.ndarray) -> np.ndarray:
    """边缘带像素颜色替换为内部颜色均值，去掉蓝底色晕；再 1px 内缩成硬边。"""
    fg = rgba[..., 3] > 0
    inner = ndimage.binary_erosion(fg, iterations=3)
    band = fg & ~inner
    rgbf = rgba[..., :3].astype(float) * inner[..., None]
    norm = ndimage.uniform_filter(inner.astype(float), 9)
    blur = np.stack([ndimage.uniform_filter(rgbf[..., c], 9) for c in range(3)], -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        edge_rgb = np.where(norm[..., None] > 0, blur / np.maximum(norm[..., None], 1e-6), rgba[..., :3])
    out = rgba.copy()
    out[..., :3][band] = np.clip(edge_rgb[band], 0, 255).astype(np.uint8)
    out[..., 3] = ndimage.binary_erosion(fg, iterations=1) * 255
    return out

def cut_sheet(path: Path, tol: int = 13, gap: int = 60, min_h: int = 120):
    """整张 Sheet → [裁好的 RGBA 姿势图]（按连通域合并框）。

    gap: 框间合并距离——actions 里板与手有缝要合并，views 三视图间距小要拆开。
    min_h: 框最小高度，滤掉「豆包AI生成」水印等文字条。
    """
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img).astype(np.uint8)
    fg = flood_bg(rgb, tol)
    fg = ndimage.binary_closing(fg, iterations=2)
    # 小噪点清理
    lbl, n = ndimage.label(fg)
    sizes = ndimage.sum(fg, lbl, range(1, n + 1))
    keep = np.zeros(n + 1, bool); keep[1:] = sizes > 4000
    fg = keep[lbl]
    # 分框：在 1/4 缩图上做合并
    small = ndimage.zoom(fg.astype(float), 0.25) > 0.5
    lbl, n = ndimage.label(small)
    boxes = []
    for i in ndimage.find_objects(lbl):
        if i is None:
            continue
        h = i[0].stop - i[0].start; w = i[1].stop - i[1].start
        if h * w < 100:
            continue
        boxes.append([i[1].start * 4, i[0].start * 4, i[1].stop * 4, i[0].stop * 4])
    # 合并互相重叠/贴近的框（手举板可能被浅色缝分隔）
    merged = True
    while merged:
        merged = False
        out = []
        while boxes:
            b = boxes.pop()
            for o in out:
                if not (b[2] + gap < o[0] or o[2] + gap < b[0] or b[3] + gap < o[1] or o[3] + gap < b[1]):
                    o[0], o[1] = min(o[0], b[0]), min(o[1], b[1])
                    o[2], o[3] = max(o[2], b[2]), max(o[3], b[3])
                    merged = True
                    break
            else:
                out.append(b)
        boxes = out
    boxes = [b for b in boxes if b[3] - b[1] >= min_h]
    boxes.sort(key=lambda b: (b[1] // 400, b[0]))
    cuts = []
    for b in boxes:
        x0, y0, x1, y1 = [max(v, 0) for v in b]
        tile = rgb[y0:y1, x0:x1]
        mask = fg[y0:y1, x0:x1]
        rgba = np.dstack([tile, mask * 255]).astype(np.uint8)
        rgba = defringe(rgba)
        im = Image.fromarray(rgba)
        bbox = im.getbbox()
        cuts.append(im.crop(bbox))
    return cuts

# --- 2) 姿势工具 -----------------------------------------------------------
def fit(im: Image.Image, box=(FIT_W, FIT_H)) -> Image.Image:
    im = im.copy()
    im.thumbnail(box, Image.LANCZOS)
    return im

def on_canvas(im: Image.Image, dy=0, scale=(1, 1), tilt=0, dim=1.0) -> Image.Image:
    """fit 后贴到 200x200 品红画布，底对齐 FOOT_Y；scale=(w,h) 压拉伸，tilt 角度，dim 压暗。"""
    im = fit(im)
    if scale != (1, 1):
        im = im.resize((max(1, int(im.width * scale[0])), max(1, int(im.height * scale[1]))), Image.LANCZOS)
    if tilt:
        im = im.rotate(tilt, resample=Image.BICUBIC, expand=True)
    if dim != 1.0:
        a = im.getchannel("A")
        im = ImageEnhance.Brightness(im).enhance(dim)
        im.putalpha(a)
    # 运行时按纯品红色键透明：半透明像素会与品红混成粉边，先二值化成硬边
    a = im.getchannel("A").point(lambda v: 255 if v >= 160 else 0)
    im = im.copy()
    im.putalpha(a)
    cv = Image.new("RGB", (CANVAS, CANVAS), (255, 0, 255))
    cv.paste(im, ((CANVAS - im.width) // 2, FOOT_Y - im.height + dy), im)
    return cv

def mirror(im: Image.Image) -> Image.Image:
    return im.transpose(Image.FLIP_LEFT_RIGHT)

# --- 3) 主流程 -------------------------------------------------------------
def load_cuts():
    CUT.mkdir(exist_ok=True)
    views = cut_sheet(SRC / "views_clean.png", gap=14)
    acts = cut_sheet(SRC / "actions.png", gap=60)
    assert len(views) == 3, f"views 应切出 3 视图，实际 {len(views)}"
    assert len(acts) == 6, f"actions 应切出 6 姿势，实际 {len(acts)}"
    names_v = ["front", "side", "back"]
    names_a = ["happy", "jump", "shy", "wave", "cheer", "hug"]  # 阅读序：上排2+下排4
    out = {}
    for im, n in zip(views, names_v):
        im.save(CUT / f"{n}.png"); out[n] = im
    for im, n in zip(acts, names_a):
        im.save(CUT / f"{n}.png"); out[n] = im
    return out

def preview(cuts):
    cols = 4; cell = 220
    rows = (len(cuts) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (255, 0, 255))
    dr = ImageDraw.Draw(sheet)
    for i, (n, im) in enumerate(cuts.items()):
        x, y = (i % cols) * cell, (i // cols) * cell
        t = fit(im, (200, 200))
        sheet.paste(t, (x + (cell - t.width) // 2, y + (cell - t.height) // 2), t)
        dr.text((x + 6, y + 4), n, fill=(255, 255, 0))
    sheet.save(CUT / "preview.png")
    print("preview ->", CUT / "preview.png")

def build_frames(cuts):
    FRAMES.mkdir(exist_ok=True)
    g = {}
    def put(name, im, **kw):
        g[name] = on_canvas(im, **kw)

    # idle：抱板微笑 + 呼吸压扁
    put("idle_0", cuts["hug"])
    put("idle_1", cuts["hug"], scale=(1.03, 0.97), dy=3)
    # walk：侧视摇摆（原侧视朝左）
    side = fit(cuts["side"])
    put("walk_0", side)
    put("walk_1", side, dy=-4, tilt=5)
    put("walk_2", side, dy=1)
    put("walk_3", side, tilt=-5)
    for i in range(4):
        (FRAMES / f"walk_l_{i}.gif").unlink(missing_ok=True)
        on_canvas(side, dy=[0, -4, 1, 0][i], tilt=[0, 5, 0, -5][i]).save(FRAMES / f"walk_l_{i}.gif")
        on_canvas(mirror(side), dy=[0, -4, 1, 0][i], tilt=[0, -5, 0, 5][i]).save(FRAMES / f"walk_r_{i}.gif")
    # grab：张手开心左右挣扎
    put("grab_0", cuts["happy"], tilt=-8)
    put("grab_1", cuts["happy"], tilt=8)
    # fall / jump
    put("fall_0", cuts["jump"])
    # land：大幅压扁
    put("land_0", cuts["hug"], scale=(1.14, 0.84), dy=12)
    # sleep：害羞眨眼压暗
    put("sleep_0", cuts["shy"], scale=(1.02, 0.96), dy=4, dim=0.72)
    put("sleep_1", cuts["shy"], dim=0.72)
    # greet：挥手
    put("greet_0", cuts["wave"])
    # cheer：举板欢呼 + 小跳
    put("cheer_0", cuts["cheer"])
    put("cheer_1", cuts["cheer"], dy=-6)
    # spin：正→右侧→背→左侧
    put("spin_0", cuts["front"])
    put("spin_1", mirror(fit(cuts["side"])))
    put("spin_2", cuts["back"])
    put("spin_3", fit(cuts["side"]))

    for name, im in g.items():
        im.save(FRAMES / f"{name}.gif")
    print(f"{len(list(FRAMES.glob('*.gif')))} frames -> {FRAMES}")

if __name__ == "__main__":
    cuts = load_cuts()
    if "--frames" in sys.argv:
        build_frames(cuts)
    else:
        preview(cuts)
