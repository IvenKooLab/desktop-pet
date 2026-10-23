"""Performance lengths, shared with the native player; no artwork is synthesized."""
import json
from pathlib import Path


DEFAULT_ACTIONS = {
    "GREET": (4, 6), "BOUNCE": (4, 6), "HAPPY": (4, 6), "SHY": (4, 6),
    "CHEER": (4, 6), "SPIN": (2, 3), "WAITING": (4, 6), "WORK": (4, 6),
    "REVIEW": (4, 6), "FAILED": (4, 6), "STRETCH": (4, 6),
    "DOZE": (4, 6), "RUBIK": (4, 6),
    "THINKING": (1, 1), "IMPATIENT": (1, 1), "RELIEVED": (1, 1),
    "YAWN": (1, 2), "STOMP": (2, 3), "CELEBRATE": (1, 2), "SEARCH": (1, 2),
}


def _range(value, maximum, integer=False):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    allowed = (int,) if integer else (int, float)
    if any(type(number) not in allowed for number in value):
        return None
    if not 0 < value[0] <= value[1] <= maximum:
        return None
    return tuple(value)


def load_behaviors(directory):
    """A missing or partially invalid optional file keeps safe bundled defaults."""
    result = {"idle_seconds": (3, 5), "walk_cycles": (5, 8),
              "actions": dict(DEFAULT_ACTIONS)}
    try:
        payload = json.loads((Path(directory) / "animation_behaviors.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return result
    for key, maximum, integer in (("idle_seconds", 30, False), ("walk_cycles", 16, True)):
        validated = _range(payload.get(key), maximum, integer)
        if validated:
            result[key] = validated
    actions = payload.get("actions")
    if isinstance(actions, dict):
        for state, definition in actions.items():
            # Sleep, drag and physics are controlled by interaction, never autoplay.
            if state not in DEFAULT_ACTIONS or not isinstance(definition, dict):
                continue
            cycles = _range(definition.get("cycles"), 16, True)
            if cycles:
                result["actions"][state] = cycles
    return result


def performance_ticks(durations, cycles=1):
    """50 ms of animation time per logic tick; playback speed is applied once by the clock."""
    return (sum(durations) * cycles + 49) // 50
