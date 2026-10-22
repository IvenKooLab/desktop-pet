"""system_notify · 任务事件系统通知（可选能力，默认 auto：桌宠隐藏/内嵌时才弹）。

门控（gate）与限流（RateLimiter）为纯逻辑，跨平台一致，配套单元测试；
发送（send）按平台分发且绝不抛异常——通知失败静默，不影响桌宠本体：
    darwin  osascript display notification（无第三方依赖、无需公证 entitlement）
    win32   Shell_NotifyIcon 气泡（ctypes，复用 Tk 窗口句柄；Win10+ 显示为 toast）
    其余平台 返回 False

只针对一次性任务事件（等待确认/任务完成/出问题），绝不转发摘要内容——
通知正文只含状态与任务标签（标签本身已由适配器截断清洗）。
"""
import subprocess
import sys
import time

NOTIFY_KINDS = ("permission.required", "turn.failed", "task.completed")
MIN_INTERVAL = 8.0        # 同类通知最小间隔（秒）
BODY_LIMIT = 120


class RateLimiter:
    """简单时间窗限流；allow(now) 通过后记录，未通过返回 False。"""

    def __init__(self, min_interval=MIN_INTERVAL):
        self.min_interval = min_interval
        self._last = None

    def allow(self, now):
        if self._last is not None and now - self._last < self.min_interval:
            return False
        self._last = now
        return True


def gate(kind, pet_hidden, mode):
    """是否应发系统通知：kind 必须是一次性任务事件 + 模式允许。

    mode: "auto"（仅桌宠隐藏/内嵌时）|"always"|"off"
    """
    if kind not in NOTIFY_KINDS or mode == "off":
        return False
    if mode == "always":
        return True
    return bool(pet_hidden)               # auto


def _escape_applescript(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _send_darwin(title, body):
    script = ('display notification "%s" with title "%s"'
              % (_escape_applescript(body[:BODY_LIMIT]),
                 _escape_applescript(title[:64])))
    try:
        subprocess.run(["/usr/bin/osascript", "-e", script],
                       timeout=5, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _send_windows(title, body, hwnd=None):
    try:
        import ctypes
        from ctypes import wintypes

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HANDLE),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
            ]

        text = body[:BODY_LIMIT]
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = hwnd or 0
        data.uID = 1
        data.uFlags = 0x10                 # NIF_INFO（气球/toast）
        data.szInfo = text
        data.szInfoTitle = title[:63]
        data.dwInfoFlags = 0x1             # NIIF_INFO
        ok = ctypes.windll.shell32.Shell_NotifyIconW(0x1, ctypes.byref(data))  # NIM_MODIFY
        if not ok and hwnd:
            # 尚未注册过的句柄：先 NIM_ADD 再试一次
            ok = ctypes.windll.shell32.Shell_NotifyIconW(0x0, ctypes.byref(data))
        return bool(ok)
    except (OSError, AttributeError, ImportError):
        return False


def send(title, body, platform=None, hwnd=None):
    """平台分发发送；失败静默返回 False。"""
    platform = platform or sys.platform
    if platform == "darwin":
        return _send_darwin(title, body)
    if platform == "win32":
        return _send_windows(title, body, hwnd)
    return False


def notify_text(kind, label, zh=True):
    """通知正文（与状态卡同一信息口径：状态 + 任务标签，无摘要内容）。"""
    labels = label[:80] if label else None
    if kind == "permission.required":
        return ("等你确认权限" if zh else "Approval needed") + (f"：{labels}" if labels else "")
    if kind == "turn.failed":
        return ("出问题了" if zh else "Something failed") + (f"：{labels}" if labels else "")
    if kind == "task.completed":
        return ("任务完成" if zh else "Task completed") + (f"：{labels}" if labels else "")
    return labels or ""
