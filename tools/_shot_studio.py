"""临时：PrintWindow 截取 Studio 窗口（用后即删）。"""
import ctypes
import ctypes.wintypes as wt

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
targets = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, _):
    if user32.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if "Iven Pet Studio" in buf.value:
            targets.append(hwnd)
    return True


user32.EnumWindows(cb, None)
assert targets, "studio not found"
hwnd = targets[0]
rc = wt.RECT()
user32.GetClientRect(hwnd, ctypes.byref(rc))
W, H = rc.right, rc.bottom
hdcw = user32.GetWindowDC(hwnd)
hdcm = gdi32.CreateCompatibleDC(hdcw)
hbmp = gdi32.CreateCompatibleBitmap(hdcw, W, H)
gdi32.SelectObject(hdcm, hbmp)
user32.PrintWindow(hwnd, hdcm, 2)


class BMI(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("xPPM", ctypes.c_int32),
                ("yPPM", ctypes.c_int32), ("clrUsed", ctypes.c_uint32),
                ("clrImportant", ctypes.c_uint32)]


bmi = BMI()
bmi.biSize = ctypes.sizeof(BMI)
bmi.biWidth = W
bmi.biHeight = -H
bmi.biPlanes = 1
bmi.biBitCount = 32
buf = ctypes.create_string_buffer(W * H * 4)
gdi32.GetDIBits(hdcm, hbmp, 0, H, buf, ctypes.byref(bmi), 0)
img = Image.frombuffer("RGBA", (W, H), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")
img.save("assets/cut/studio_ui.png")
gdi32.DeleteObject(hbmp)
gdi32.DeleteDC(hdcm)
user32.ReleaseDC(hwnd, hdcw)
print("shot ok", img.size)
