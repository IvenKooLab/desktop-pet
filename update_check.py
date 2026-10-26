"""update_check · GitHub Release 版本探测（纯标准库，可选能力，默认开启）。

只做一次 GET 到 `https://github.com/IvenKooLab/desktop-pet/releases/latest`，
跟随 GitHub 的 302 跳转读取最终 URL 里的 tag（如 v1.0.1）——不调用 API、
不占配额、不上传任何本机内容；网络不可用或被拦截时静默失败，绝不打扰。

组合语义（Swift 端 UpdateCheck 在 IvenPet.swift 镜像同一套规则）：
    parse_version("v1.0.1")        -> (1, 0, 1)
    is_newer((1,0,2), (1,0,1))     -> True
    parse_tag(".../releases/tag/v1.0.1") -> "1.0.1"
    latest_release(fetch)          -> ("1.0.1", releases_url) | None
    current_version(base_dir)      -> "1.0.1" | None（缺失即跳过检查，不误报）
"""
import re
import urllib.request
from pathlib import Path

RELEASES_URL = "https://github.com/IvenKooLab/desktop-pet/releases/latest"
TAG_RE = re.compile(r"/releases/tag/v?(\d+(?:\.\d+)*)$")
USER_AGENT = ("IvenPet-update-check/1 "
              "(+https://github.com/IvenKooLab/desktop-pet)")


def parse_version(text):
    """'v1.0.1' / '1.0.1' -> (1, 0, 1)；非法返回 None。"""
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest, current):
    """latest 是否比 current 新；任一侧非法返回 False（宁可不提示）。"""
    latest = latest if isinstance(latest, tuple) else parse_version(latest)
    current = current if isinstance(current, tuple) else parse_version(current)
    if latest is None or current is None:
        return False
    width = max(len(latest), len(current))
    return (latest + (0,) * (width - len(latest))
            > current + (0,) * (width - len(current)))


def parse_tag(url):
    """从跳转后的 URL 提取版本：'.../releases/tag/v1.0.1' -> '1.0.1'。"""
    if not isinstance(url, str):
        return None
    match = TAG_RE.search(url)
    return match.group(1) if match else None


def latest_release(fetch=None, timeout=6.0):
    """探测最新发布，返回 (版本串, 下载页 URL)；失败静默返回 None。

    fetch(url, timeout) 可注入测试替身（返回最终 URL 字符串）。
    """
    if fetch is None:
        def fetch(url, timeout):
            request = urllib.request.Request(
                url, method="GET", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.geturl()      # 跟随 302 后的最终 URL
    try:
        final_url = fetch(RELEASES_URL, timeout)
    except Exception:                          # 网络/超时/证书 … 一律静默
        return None
    version = parse_tag(final_url or "")
    return (version, RELEASES_URL) if version else None


def current_version(base_dir):
    """读打包目录/仓库根下的 VERSION；缺失或非法返回 None。"""
    try:
        text = (Path(base_dir) / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return text if parse_version(text) else None


def download_url():
    """下载页（releases/latest 会自动跳到最新 release）。"""
    return RELEASES_URL
