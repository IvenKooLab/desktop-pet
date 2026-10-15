import tempfile
import unittest
from pathlib import Path
from language_preferences import load_language, save_language


class LanguagePreferenceTests(unittest.TestCase):
    def test_choice_survives_reload_and_system_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings" / "language"
            self.assertEqual(load_language(path), "system")
            for value in ("en", "zh", "system"):
                self.assertTrue(save_language(value, path))
                self.assertEqual(load_language(path), value)

    def test_invalid_content_and_unwritable_location(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "language"
            path.write_bytes(b"\xff")
            self.assertEqual(load_language(path), "system")
            path.write_text("unexpected")
            self.assertEqual(load_language(path), "system")
            self.assertFalse(save_language("en", path / "child"))
            with self.assertRaises(ValueError):
                save_language("unsupported", path)
