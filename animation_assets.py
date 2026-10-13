"""Optional animation manifest support; legacy characters remain compatible."""
import json
import re
from pathlib import Path


def load_clips(directory):
    try:
        payload = json.loads((Path(directory) / "animation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return {}
    result = {}
    candidates = payload.get("clips", {})
    if not isinstance(candidates, dict):
        return {}
    for state, clip in candidates.items():
        if not isinstance(clip, dict):
            continue
        names, durations = clip.get("frames"), clip.get("durations")
        if not isinstance(names, list) or not names or not isinstance(durations, list):
            continue
        if len(names) != len(durations):
            continue
        if any(not isinstance(n, str) or not re.fullmatch(r"[a-z0-9_]+", n)
               or not (Path(directory) / (n + ".gif")).is_file() for n in names):
            continue
        if any(type(d) is not int or d <= 0 for d in durations):
            continue
        result[state] = (tuple(names), tuple(durations))
    return result


def timed_frame(names, durations, elapsed_ms):
    """Resolve exact boundaries and loop duration without losing hold frames."""
    phase = max(0, elapsed_ms) % sum(durations)
    for name, duration in zip(names, durations):
        if phase < duration:
            return name
        phase -= duration
    return names[-1]
