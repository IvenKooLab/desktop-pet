import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop_platform import configure_transparency, frame_path, clear_legacy_color_key


class WindowStub:
    def __init__(self):
        self.options = {}
        self.attributes_set = {}
    def configure(self, **options):
        self.options.update(options)
    def attributes(self, name, value):
        self.attributes_set[name] = value


class PlatformTests(unittest.TestCase):
    def test_mac_never_uses_opaque_magenta(self):
        window = WindowStub()
        self.assertEqual(configure_transparency(window, "darwin"), "systemTransparent")
        self.assertEqual(window.options["bg"], "systemTransparent")
        self.assertEqual(window.attributes_set, {"-transparent": True})

    def test_windows_retains_its_color_key(self):
        window = WindowStub()
        self.assertEqual(configure_transparency(window, "win32"), "#FF00FF")
        self.assertEqual(window.attributes_set, {"-transparentcolor": "#FF00FF"})

    def test_mac_prefers_alpha_png_windows_prefers_gif(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for suffix in ("gif", "png"):
                (folder / ("idle_0." + suffix)).write_bytes(b"fixture")
            self.assertEqual(frame_path(folder, "idle_0", "darwin").suffix, ".png")
            self.assertEqual(frame_path(folder, "idle_0", "win32").suffix, ".gif")
            (folder / "idle_0.png").unlink()
            self.assertEqual(frame_path(folder, "idle_0", "darwin").suffix, ".gif")

    def test_legacy_cleanup_preserves_character_colors(self):
        class ImageStub:
            pixels = [(255,0,255), (120,40,180), (0,200,220), (255,255,255)]
            def __init__(self): self.transparent = []
            def width(self): return 4
            def height(self): return 1
            def get(self,x,y): return self.pixels[x]
            def transparency_set(self,x,y,value): self.transparent.append((x,y,value))
        image = ImageStub()
        clear_legacy_color_key(image)
        self.assertEqual(image.transparent, [(0,0,True)])

    def test_linux_is_not_falsely_reported_as_supported(self):
        with self.assertRaises(RuntimeError):
            configure_transparency(WindowStub(), "linux")


if __name__ == "__main__":
    unittest.main()
