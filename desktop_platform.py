"""Native window transparency and asset selection without a host-app dependency."""
import sys
from pathlib import Path

MAGENTA = "#FF00FF"


def configure_transparency(window, platform=None):
    platform = platform or sys.platform
    if platform == "darwin":
        # macOS uses a transparent native window plus real per-pixel PNG alpha.
        window.configure(bg="systemTransparent")
        window.attributes("-transparent", True)
        return "systemTransparent"
    if platform == "win32":
        window.attributes("-transparentcolor", MAGENTA)
        return MAGENTA
    raise RuntimeError("Native floating pets currently support macOS and Windows. Linux needs a compositor backend.")


def frame_path(directory, name, platform=None):
    platform = platform or sys.platform
    folder = Path(directory)
    png = folder / (name + ".png")
    gif = folder / (name + ".gif")
    if platform == "darwin" and png.is_file():
        return png
    return gif if gif.is_file() else png


def clear_legacy_color_key(image):
    """Convert old opaque GIF key pixels to true transparency in Tk itself."""
    for y in range(image.height()):
        for x in range(image.width()):
            if image.get(x, y) in ((255, 0, 255), "#ff00ff", "#FF00FF"):
                image.transparency_set(x, y, True)
