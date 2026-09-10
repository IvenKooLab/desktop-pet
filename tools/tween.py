"""过程补帧（确定性插帧）：在两帧动作之间生成中间帧。

三层处理（纯 numpy/PIL，确定性，无任何模型依赖）：
    1) 分段比例渐变扭曲——两帧的头带/身高比例差异按 t 插值，
       把两帧各自向"中间比例"变形（视角/姿势差表现为柔和的体态渐变）
    2) 覆盖归一化混合——预乘空间加权，角色不与背景混色、无粉边鬼影
    3) 水平运动模糊——沿行走方向的子像素拖影，读作快速迈步

用法：
    from tween import tween_frame
    mid = tween_frame(frame_a, frame_b, 0.5)   # t=0 返回 a，t=1 返回 b
"""
import numpy as np
from PIL import Image

CANVAS = 200


def _canvas_rgba(arr_rgb, mask):
    cv = np.zeros((CANVAS, CANVAS, 4), np.float32)
    cv[..., :3] = arr_rgb
    cv[..., 3] = mask * 255.0
    return cv


def _align_bottom(arr_rgba, dx=0):
    """贴到 200x200 透明画布底边中心，返回画布数组。"""
    h, w = arr_rgba.shape[:2]
    cv = np.zeros((CANVAS, CANVAS, 4), np.float32)
    x0 = max(0, (CANVAS - w) // 2 + dx)
    y0 = max(0, CANVAS - h)
    cv[y0:y0 + h, x0:x0 + w] = arr_rgba
    return cv


def _band_resize(arr_rgba: np.ndarray, total_h_target: int):
    """按'头部带/身体带'两段分别垂直缩放后拼接（水平随动）。支持 float 输入。"""
    h, w = arr_rgba.shape[:2]
    hem = max(1, int(h * 0.62))
    top = arr_rgba[:hem]
    bot = arr_rgba[hem:]
    th = max(1, int(total_h_target * (hem / h)))
    bh = max(1, total_h_target - th)

    def rs(band, nh):
        im = Image.fromarray(np.clip(band, 0, 255).astype(np.uint8), "RGBA")
        return np.asarray(im.resize((w, nh), Image.LANCZOS)).astype(np.float32)

    return np.concatenate([rs(top, th), rs(bot, bh)], axis=0)


def _warp_toward(arr: np.ndarray, ref: np.ndarray, t: float) -> np.ndarray:
    """把 arr 的头带高度/总高向 ref 的对应值插值 t（t=0 不变，t=1 等于 ref 的比例）。"""
    h = arr.shape[0]
    ys, xs = np.where(arr[..., 3] > 0)
    hh = (ys.max() - ys.min() + 1) if len(ys) else h
    ys2, xs2 = np.where(ref[..., 3] > 0)
    hr = (ys2.max() - ys2.min() + 1) if len(ys2) else h
    total = int(h + (hr - h) * t)
    head = int(hh + (hr * (hh / max(1, h)) - hh) * t)
    head = max(8, head)
    out = _band_resize(arr, total)
    # 底边对齐
    oy = arr.shape[0] - total if total < arr.shape[0] else 0
    if oy > 0:
        out = np.concatenate([np.zeros((oy, out.shape[1], 4), np.float32), out], 0)
    elif oy < 0:
        out = out[-oy:]
    return out


def _h_blur_band(rgb: np.ndarray, alpha_mask: np.ndarray, radius: int = 3):
    """仅对角色像素做水平方向运动模糊（盒式），边缘更顺滑。"""
    if radius <= 0:
        return rgb
    kernel = np.ones(radius * 2 + 1, np.float32) / (radius * 2 + 1)
    out = rgb.copy()
    for c in range(3):
        out[..., c] = np.apply_along_axis(
            lambda row: np.convolve(row, kernel, mode="same"), 1, rgb[..., c])
    out = rgb * (1 - 0.45) + out * 0.45                    # 45% 强度，保留细节
    return out


def tween_frame(im_a: Image.Image, im_b: Image.Image, t: float = 0.5,
                smear: bool = True) -> Image.Image:
    """生成 a、b 之间的中间帧。t=0 → a，t=1 → b。"""
    t = float(min(max(t, 0.0), 1.0))

    def prep(im):
        im = im.copy()
        im.thumbnail((CANVAS - 4, CANVAS - 4), Image.LANCZOS)   # 大图先缩进画布
        arr = np.asarray(im.convert("RGBA")).astype(np.float32)
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        a = arr[..., 3:] / 255.0
        keyed = ~((r > 200) & (b > 200) & (g < 110))   # 品红色键（GIF 无透明通道）
        if float((a > 0).mean()) >= 0.5:               # 无实际透明信息时结合色键
            keyed = keyed & (a[..., 0] > 0.1)
        h, w = arr.shape[:2]
        cv = np.zeros((CANVAS, CANVAS, 4), np.float32)
        x0 = max(0, (CANVAS - w) // 2)
        y0 = CANVAS - h
        cv[y0:y0 + h, x0:x0 + w, :3] = arr[..., :3]
        cv[y0:y0 + h, x0:x0 + w, 3] = keyed.astype(np.float32) * 255.0
        return cv

    ca, cb = prep(im_a), prep(im_b)
    fa = _warp_toward(ca, cb, t * 0.5)
    fb = _warp_toward(cb, ca, (1 - t) * 0.5)
    aa, ab = fa[..., 3:] / 255.0, fb[..., 3:] / 255.0
    num = fa[..., :3] * aa * (1 - t) + fb[..., :3] * ab * t
    den = aa * (1 - t) + ab * t
    rgb = np.where(den > 1e-3, num / np.maximum(den, 1e-3), 255.0)
    alpha = np.maximum(aa, ab)                             # 剪影并集（端点纯度由调用方保证）
    if smear and t > 0.05 and t < 0.95:                    # 过渡帧加运动模糊
        rgb = _h_blur_band(rgb, alpha, 3)
    out = np.zeros_like(fa)
    vis = (alpha > 0.02)[..., 0]
    out[vis, :3] = np.clip(rgb[vis], 0, 255)
    out[vis, 3:] = np.clip(alpha[vis] * 255, 0, 255)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def walk_cycle_tweens(poses, w: float = 0.4, smear: bool = True):
    """姿势序列 → 加轻补间的循环帧。

    每对相邻姿势 (a→b) 生成一个 w 权重的轻补间插在中间：
    n 个姿势 → 2n 帧循环 [a0, m01, a1, m12, ...]。跨渲染姿势（视角不一致）
    的重补间会出明显双曝光，故只用单级轻补间软化硬切。
    """
    seq = []
    n = len(poses)
    for i in range(n):
        a, b = poses[i], poses[(i + 1) % n]
        seq.append(a)
        seq.append(tween_frame(a, b, w, smear=smear))
    return seq
