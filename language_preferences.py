"""Small, local UI preference; contains no credentials or agent content."""
from pathlib import Path

LANGUAGES = ("system", "zh", "en")


def load_language(path=None):
    path = Path(path) if path is not None else Path.home() / ".iven-pet" / "language"
    try:
        value = path.read_text(encoding="utf-8").strip()
        return value if value in LANGUAGES else "system"
    except (OSError, UnicodeError):
        return "system"


def save_language(value, path=None):
    if value not in LANGUAGES:
        raise ValueError("Unsupported UI language")
    path = Path(path) if path is not None else Path.home() / ".iven-pet" / "language"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value+"\n", encoding="utf-8")
    except OSError:
        return False
    return True
