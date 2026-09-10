"""素材预处理 v3：从豆包 3D 手办设定图切出桌宠全套动作帧。

输入 assets/src/：
    views_clean.png   正/侧/背三视图（干净版）
    walk_cycle.png    走路循环 4 相位（checker/rembg 模式）
    fastwalk.png      小短腿快走 4 相位
    idle_breathe.png  待机呼吸 3 帧
    actions_lib.png   八宫格动作库（点击弹跳/开心/害羞等）
    views_blueprint.png 标注版留档

流程：
    1) 抠背景：rembg AI 抠图（新代素材，滞后阈值+深色回收+fill_holes）
       或 颜色闸门+局部梯度洪泛（青蓝渐变棚拍底）
    2) 连通域分框切片
    3) 去边（边缘像素替换为内部色）+ 内缩硬边
    4) 拼贴预览 assets/cut/preview.png（人工检查）—— python make_frames3d.py
    5) 合成 200x200 动作帧 GIF → frames3d/   —— python make_frames3d.py --frames

构建期依赖 Pillow/numpy/scipy；运行时（pet.py）零第三方依赖。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
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

def defringe(rgba: np.ndarray, glow_cut: int = 8, band: int = 5) -> np.ndarray:
    """切掉渲染图自带的辉光软边 + 边缘带重着色。

    豆包渲染在角色轮廓外有一圈 3~10px 灰紫辉光，颜色闸门只能吃掉一半，
    剩下的会变成紫描边——这里把 alpha 整体内缩 glow_cut 像素彻底切掉，
    再把新边缘带（band 像素宽）颜色替换为更深的内部色，消除残余色晕。
    """
    fg = rgba[..., 3] > 0
    inner = ndimage.binary_erosion(fg, iterations=glow_cut + band)
    band_px = fg & ~inner
    rgbf = rgba[..., :3].astype(float) * inner[..., None]
    win = band * 2 + 9
    norm = ndimage.uniform_filter(inner.astype(float), win)
    blur = np.stack([ndimage.uniform_filter(rgbf[..., c], win) for c in range(3)], -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        edge_rgb = np.where(norm[..., None] > 1e-3, blur / np.maximum(norm[..., None], 1e-6), rgba[..., :3])
    out = rgba.copy()
    out[..., :3][band_px] = np.clip(edge_rgb[band_px], 0, 255).astype(np.uint8)
    out[..., 3] = ndimage.binary_erosion(fg, iterations=glow_cut) * 255
    return out

def remove_thin(fg: np.ndarray, t: int = 7) -> np.ndarray:
    """去掉 mask 中的细笔画（地面椭圆圈/虚线/水印等）。

    横、竖两个方向各做「腐蚀+按原 mask 回灌」：任一方向厚度 < t 的结构
    都保不住核（椭圆上下弧死于竖腐蚀、侧弧与虚线死于横腐蚀），
    腿/场记板/头发等实体两个方向都厚，完好保留。
    """
    v = ndimage.binary_propagation(
        ndimage.binary_erosion(fg, structure=np.ones((t, 1), bool)), mask=fg)
    hz = ndimage.binary_propagation(
        ndimage.binary_erosion(fg, structure=np.ones((1, t), bool)), mask=fg)
    return v & hz

def checker_fg(rgb: np.ndarray, tol: int = 13, hole_min: int = 1500) -> np.ndarray:
    """假透明棋盘格/纯白底：中性浅色规则从四边洪泛 + 掏空修复。

    发丝高光本身接近中性浅白，纯颜色规则必然把头发掏空（洞经轮廓抗锯齿
    细颈与外界连通）。修复：闭运算剪断细颈 → 掏空处变成封闭洞 →
    只回填面积 > hole_min 的洞（手臂与身体间的窄缝是小洞，保持透明）。
    注意：本模式不做 remove_thin——小尺寸 Sheet 上耳机梁等斜向细结构
    会被 7px 腐蚀啃碎；棋盘格/卡片边框靠颜色规则即可吃掉。
    """
    mx = rgb.max(2).astype(int)
    mn = rgb.min(2).astype(int)
    cand = ((mx - mn) <= 6) & (mn >= 195)
    seed = np.zeros(cand.shape, bool)
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    bg = ndimage.binary_propagation(seed & cand, mask=cand)
    fg = ~bg
    fg = ndimage.binary_closing(fg, iterations=6)
    outside = np.zeros(cand.shape, bool)
    outside[0, :] = outside[-1, :] = outside[:, 0] = outside[:, -1] = True
    bg2 = ~fg
    lbl, n = ndimage.label(bg2)
    border = set(np.unique(np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]])))
    sizes = ndimage.sum(bg2, lbl, range(1, n + 1))
    for i in range(1, n + 1):
        if i not in border and sizes[i - 1] > hole_min:
            fg |= lbl == i
    return fg

_REMBG_SESSION = None

def rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        from rembg import new_session
        _REMBG_SESSION = new_session("u2net")
    return _REMBG_SESSION

def rembg_fg(img: Image.Image, thresh: int = 127) -> np.ndarray:
    """AI 抠图（u2net）：浅色角色×浅色背景的颜色规则终结者。

    白发×白底时 u2net 给白发区输出低 alpha（20~100），单阈值二值化会把
    头发成片砍掉——改用滞后阈值：alpha≥140 为确定前景，≥25 为候选，
    从确定前景传播生长；白发连着身体被拉回，远离角色的背景噪声被弃。
    """
    from rembg import remove
    out = remove(img, session=rembg_session())
    alpha = np.asarray(out)[..., 3]
    strong = alpha >= 140
    weak = alpha >= 25
    fg = ndimage.binary_propagation(strong, mask=weak)
    # 深色部件回收：u2net 偶发丢手持深色道具（场记板）。角色近旁的深蓝紫
    # 像素（板/鞋/发影）必然属于角色——浅色棋盘格背景在颜色上天然排除
    rgb = np.asarray(img.convert("RGB")).astype(int)
    mx = rgb.max(2)
    dark = (mx < 140) & (rgb[..., 2] >= rgb[..., 0]) & (mx >= 60)
    near = ndimage.binary_dilation(fg, iterations=35)
    fg = fg | (dark & near)
    # 场记板白色条纹/发丝高光是板框/头发包围的封闭区，fill_holes 回填
    # （露出源图本来颜色）；深底验收需确认手臂贴身处的窄缝未被误填
    return ndimage.binary_fill_holes(fg)

def rough_boxes_checker(rgb: np.ndarray, gap: int, min_h: int):
    """checker 底的粗定位：中性浅色规则取反 → 连通域 → 合并框。

    只用于确定人物位置（供逐个 rembg），不要求 mask 精确。
    """
    mx = rgb.max(2).astype(int)
    mn = rgb.min(2).astype(int)
    fg = ~(((mx - mn) <= 6) & (mn >= 195))
    lbl, n = ndimage.label(fg)
    sizes = ndimage.sum(fg, lbl, range(1, n + 1))
    keep = np.zeros(n + 1, bool); keep[1:] = sizes > 4000
    fg = keep[lbl]
    small = ndimage.zoom(fg.astype(float), 0.25) > 0.5
    lbl, n = ndimage.label(small)
    boxes = []
    for i in ndimage.find_objects(lbl):
        if i is None:
            continue
        if (i[0].stop - i[0].start) * (i[1].stop - i[1].start) < 100:
            continue
        boxes.append([i[1].start * 4, i[0].start * 4, i[1].stop * 4, i[0].stop * 4])
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
    return boxes


def blend_poses(im_a: Image.Image, im_b: Image.Image, w_b: float = 0.4) -> Image.Image:
    """两张 RGBA 姿势图对齐底心后按权重混合（w_b = b 的权重）。

    覆盖归一化合成：A 独有区显示 A 本色、B 独有区显示 B 本色、重叠区加权
    平均（动态模糊感）——不会把品红混进角色（对比直接 RGB blend 的粉边鬼影）。
    """
    W = max(im_a.width, im_b.width)
    H = max(im_a.height, im_b.height)
    ca = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cb = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ca.paste(im_a, ((W - im_a.width) // 2, H - im_a.height), im_a)
    cb.paste(im_b, ((W - im_b.width) // 2, H - im_b.height), im_b)
    fa = np.asarray(ca).astype(np.float32)
    fb = np.asarray(cb).astype(np.float32)
    aa = fa[..., 3:] / 255.0
    ab = fb[..., 3:] / 255.0
    num = fa[..., :3] * aa * (1 - w_b) + fb[..., :3] * ab * w_b
    den = aa * (1 - w_b) + ab * w_b
    rgb = np.where(den > 1e-3, num / np.maximum(den, 1e-6), 255.0)
    out_a = np.maximum(fa[..., 3], fb[..., 3])           # 剪影取并集
    out = np.dstack([np.clip(rgb, 0, 255), out_a]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")

def cut_single(path: Path) -> Image.Image:
    """单人物原图直接过 rembg（模型满视野，细节最完整）。

    组件过滤阈值降到 2%：手持场记板与手指连接处 alpha 低、易断开成
    独立组件，8% 阈值会把板整块误删。
    """
    img = Image.open(path).convert("RGB")
    a = rembg_fg(img)
    lbl, n = ndimage.label(a)
    if n > 1:
        sz = ndimage.sum(a, lbl, range(1, n + 1))
        keep = np.zeros(n + 1, bool); keep[1:] = sz >= sz.max() * 0.02
        a = keep[lbl]
    rgba = np.dstack([np.asarray(img), a * 255]).astype(np.uint8)
    rgba = defringe(rgba, glow_cut=2)
    im = Image.fromarray(rgba)
    return im.crop(im.getbbox())

def cut_sheet(path: Path, tol: int = 13, gap: int = 60, min_h: int = 120,
              bg: str = "blue", glow_cut: int = 8):
    """整张 Sheet → [裁好的 RGBA 姿势图]（按连通域合并框）。

    gap: 框间合并距离——actions 里板与手有缝要合并，views 三视图间距小要拆开。
    min_h: 框最小高度，滤掉「豆包AI生成」水印等文字条。
    rembg 模式：u2net 内部只看 320x320，整张喂入则小人物只分到几十像素、
    鞋子必糊——必须先粗定位、逐个人物裁出单独过模型。
    """
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img).astype(np.uint8)
    if bg == "rembg":
        cuts = []
        for (x0, y0, x1, y1) in rough_boxes_checker(rgb, gap=gap, min_h=min_h):
            pad = 16
            crop = img.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))
            a = rembg_fg(crop)
            lbl, n = ndimage.label(a)              # 只留主组件 + 面积≥8% 的部件，滤渣点
            if n > 1:
                sz = ndimage.sum(a, lbl, range(1, n + 1))
                keep = np.zeros(n + 1, bool); keep[1:] = sz >= sz.max() * 0.08
                a = keep[lbl]
            rgba = np.dstack([np.asarray(crop), a * 255]).astype(np.uint8)
            rgba = defringe(rgba, glow_cut=2)
            a2 = rgba[..., 3] > 0                  # defringe 腐蚀会切断细颈，再滤一次
            lbl, n = ndimage.label(a2)
            if n > 1:
                sz = ndimage.sum(a2, lbl, range(1, n + 1))
                keep = np.zeros(n + 1, bool); keep[1:] = sz >= sz.max() * 0.08
                rgba[..., 3] = (keep[lbl] * 255).astype(np.uint8)
            im = Image.fromarray(rgba)
            cuts.append(im.crop(im.getbbox()))
        return cuts
    if bg == "checker":
        fg = checker_fg(rgb)
        glow_cut = min(glow_cut, 3)          # 描边已被颜色规则吃掉，只做浅内缩
    else:
        fg = flood_bg(rgb, tol)
        fg = ndimage.binary_closing(fg, iterations=2)
        fg = remove_thin(fg)                 # 地面椭圆圈/虚线/水印
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
        rgba = defringe(rgba, glow_cut=glow_cut)
        im = Image.fromarray(rgba)
        bbox = im.getbbox()
        cuts.append(im.crop(bbox))
    return cuts

# --- 2) 姿势工具 -----------------------------------------------------------
def _pm(im: Image.Image) -> Image.Image:
    """预乘 alpha：透明像素 RGB 归零，重采样时底色才不会混入边缘（防紫描边）。"""
    arr = np.asarray(im.convert("RGBA")).copy()
    a = arr[..., 3:].astype(np.float32) / 255.0
    arr[..., :3] = np.clip(arr[..., :3].astype(np.float32) * a, 0, 255)
    return Image.fromarray(arr, "RGBA")

def _unpm(im: Image.Image) -> Image.Image:
    """预乘还原为直色 + alpha 二值化（运行时品红色键需要硬边）。"""
    arr = np.asarray(im.convert("RGBA")).astype(np.float32)
    a = arr[..., 3:] / 255.0
    rgb = np.clip(arr[..., :3] / np.maximum(a, 1e-4), 0, 255)
    rgb = np.where(a > 0.01, rgb, 0.0)
    out = np.dstack([rgb, np.where(arr[..., 3] >= 160, 255, 0)]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")

def fit(im: Image.Image, box=(FIT_W, FIT_H)) -> Image.Image:
    """预乘空间缩放（仅预览/外部用；管线内由 on_canvas 统一处理）。"""
    im = _pm(im).copy()
    im.thumbnail(box, Image.LANCZOS)
    return _unpm(im)

def stride(im: Image.Image, dx: int, hip: float = 0.70, feather: float = 0.08) -> Image.Image:
    """伪步态：下半身按行横向渐变错位（剪腿），越靠脚位移越大。

    接缝藏在帽衫下摆处并垂直羽化，配合 bob/tilt 组成走路循环。
    dx>0 脚向右错位（用于朝左行走的后蹬相位），dx<0 反向。
    """
    arr = np.asarray(im.convert("RGBA")).astype(np.float32)
    h = arr.shape[0]
    y0 = int(h * hip)
    fz = max(4, int(h * feather))
    shifted = arr.copy()
    for y in range(y0 + fz, h):
        t = (y - y0) / max(1, h - y0)
        d = int(round(dx * t))
        if d:
            row = arr[y]
            r = np.zeros_like(row)
            if d > 0:
                r[:, d:] = row[:, :-d]
            else:
                r[:, :d] = row[:, -d:]
            shifted[y] = r
    a = np.zeros((h, 1, 1), np.float32)
    a[y0:y0 + fz, :, :] = np.linspace(0.0, 1.0, fz).reshape(fz, 1, 1)
    out = np.clip(arr * (1 - a) + shifted * a, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")

def on_canvas(im: Image.Image, dy=0, dx=0, scale=(1, 1), tilt=0, dim=1.0, flip=False) -> Image.Image:
    """fit 后贴到 200x200 品红画布，底对齐 FOOT_Y。

    全部重采样（缩放/旋转）在预乘空间进行，杜绝蓝底/黑填充混入边缘。
    scale=(w,h) 压拉伸，tilt 角度，dy/dx 上下/左右偏移，dim 压暗，flip 水平镜像。
    """
    im = _pm(im)
    im.thumbnail((FIT_W, FIT_H), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if scale != (1, 1):
        im = im.resize((max(1, int(im.width * scale[0])), max(1, int(im.height * scale[1]))),
                       Image.LANCZOS)
    if tilt:
        im = im.rotate(tilt, resample=Image.BICUBIC, expand=True)
    im = _unpm(im)
    if dim != 1.0:
        arr = np.asarray(im).copy()
        arr[..., :3] = np.clip(arr[..., :3].astype(np.float32) * dim, 0, 255).astype(np.uint8)
        im = Image.fromarray(arr, "RGBA")
    cv = Image.new("RGB", (CANVAS, CANVAS), (255, 0, 255))
    cv.paste(im, ((CANVAS - im.width) // 2 + dx, FOOT_Y - im.height + dy), im)
    # 清除孤立小色块：GIF 调色板量化会把细连接路径键断，浮出碎片；
    # 角色本体是大连通域，<150px 的孤岛必是渣点
    arr = np.asarray(cv).copy()
    r, g, b = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int)
    fg = ~((r > 200) & (b > 200) & (g < 110))
    lbl, n = ndimage.label(fg)
    if n > 1:
        sz = ndimage.sum(fg, lbl, range(1, n + 1))
        for i in range(1, n + 1):
            if sz[i - 1] < 150:
                arr[lbl == i] = (255, 0, 255)
    return Image.fromarray(arr, "RGB")

# --- 3) 主流程 -------------------------------------------------------------
def load_cuts():
    CUT.mkdir(exist_ok=True)
    views = cut_sheet(SRC / "views_clean.png", gap=14)
    walks = cut_sheet(SRC / "walk_cycle.png", gap=14, bg="rembg")
    fasts = cut_sheet(SRC / "fastwalk.png", gap=40, bg="rembg")
    idles = cut_sheet(SRC / "idle_breathe.png", gap=40, bg="rembg")
    cards = cut_sheet(SRC / "actions_lib.png", gap=30, bg="rembg")
    wr_contact_s = cut_single(SRC / "wr_contact_single.png")
    wr_pass_s = cut_single(SRC / "wr_pass_single.png")
    assert len(views) == 3, f"views 应切出 3 视图，实际 {len(views)}"
    assert len(walks) == 4, f"walk_cycle 应切出 4 步态，实际 {len(walks)}"
    assert len(fasts) == 4, f"fastwalk 应切出 4 步态，实际 {len(fasts)}"
    assert len(idles) == 3, f"idle_breathe 应切出 3 帧，实际 {len(idles)}"
    assert len(cards) == 8, f"actions_lib 应切出 8 卡，实际 {len(cards)}"
    names_v = ["front", "side", "back"]
    names_w = ["wl_contact", "wl_pass", "wr_pass", "wr_contact"]  # 左：接触/过渡，右：过渡/接触
    names_f = ["fl_a", "fl_b", "fr_a", "fr_b"]
    out = {}
    for im, n in zip(views, names_v):
        im.save(CUT / f"{n}.png"); out[n] = im
    for im, n in zip(walks, names_w):
        im.save(CUT / f"{n}.png"); out[n] = im
    for im, n in zip(fasts, names_f):
        im.save(CUT / f"{n}.png"); out[n] = im
    for i, im in enumerate(idles):
        im.save(CUT / f"idleb_{i}.png"); out[f"idleb_{i}"] = im
    for i, im in enumerate(cards):
        im.save(CUT / f"card_{i}.png"); out[f"card_{i}"] = im
    wr_contact_s.save(CUT / "wrs_contact.png"); out["wrs_contact"] = wr_contact_s
    wr_pass_s.save(CUT / "wrs_pass.png"); out["wrs_pass"] = wr_pass_s
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

    # idle：呼吸三帧（豆包待机呼吸Sheet）
    for i in range(3):
        put(f"idle_{i}", cuts[f"idleb_{i}"])
    # walk：单张侧视图 + 程序化关节步态（8 相位，参数化任意帧数零鬼影）。
    # 实测结论：走路循环 Sheet 的各姿势是独立渲染、镜头角度不一致，
    # 混合补间=双曝光鬼影、硬切=视角闪烁——都不是连贯动画，弃用。
    # （待办：豆包重出"同镜头连续相位"Sheet 后可换回真帧路线）
    side = cuts["side"]
    phases = [28, 14, 0, -14, -28, -14, 0, 14]           # 剪腿连续相位
    l_face = True                                        # views_clean 侧视为左向
    for i, dxs in enumerate(phases):
        base = stride(side, dxs if l_face else -dxs)
        contact = abs(dxs) > 20
        dyv = 2 if contact else -4                       # 触地低、过渡高（颠步）
        tl = -dxs / 28 * 2.5
        put(f"walk_l_{i}", base, tilt=tl, dy=dyv)
        put(f"walk_r_{i}", base, tilt=-tl, dy=dyv, flip=True)
    # 小短腿快走（RUN）
    put("fast_l_0", cuts["fl_a"])
    put("fast_l_1", cuts["fl_b"], dy=-4)
    put("fast_r_0", cuts["fr_a"])
    put("fast_r_1", cuts["fr_b"], dy=-4)
    # 点击弹跳：抬腿跳 + 眯眼笑
    put("bounce_0", cuts["card_4"])
    put("bounce_1", cuts["card_2"])
    # 开心反应：张嘴欢呼 + 跳起
    put("happy_0", cuts["card_6"])
    put("happy_1", cuts["card_6"], dy=-8)
    # 害羞反应：眨眼
    put("shy_0", cuts["card_1"])
    # 以下动作全部改用新Sheet素材——旧蓝底Sheet人物比例差 ~25%，彻底退役。
    # grab：挣扎 = 弹跳姿势左右倾斜
    put("grab_0", cuts["card_4"], tilt=-8)
    put("grab_1", cuts["card_2"], tilt=8)
    # fall：快走俯冲姿势当坠落（蜷腿扑腾感）
    put("fall_0", cuts["fl_a"])
    # land：走路接触帧大幅压扁
    put("land_0", cuts["wl_contact"], scale=(1.14, 0.84), dy=12)
    # sleep：眯眼笑两帧压暗（闭眼=睡觉）
    put("sleep_0", cuts["card_3"], scale=(1.02, 0.96), dy=4, dim=0.72)
    put("sleep_1", cuts["card_2"], dim=0.72)
    # greet：开心打板（上线演出）
    put("greet_0", cuts["card_6"])
    # cheer：举板欢呼 + 小跳
    put("cheer_0", cuts["card_7"])
    put("cheer_1", cuts["card_6"], dy=-6)
    # spin：正→右侧→背→左侧（views_clean 人物偏大 ~20%，缩放对齐新Sheet）
    put("spin_0", cuts["front"], scale=(0.88, 0.88))
    put("spin_1", cuts["side"], scale=(0.88, 0.88), flip=True)
    put("spin_2", cuts["back"], scale=(0.88, 0.88))
    put("spin_3", cuts["side"], scale=(0.88, 0.88))

    for name, im in g.items():
        im.save(FRAMES / f"{name}.gif")
    print(f"{len(list(FRAMES.glob('*.gif')))} frames -> {FRAMES}")

if __name__ == "__main__":
    cuts = load_cuts()
    if "--frames" in sys.argv:
        build_frames(cuts)
    else:
        preview(cuts)
