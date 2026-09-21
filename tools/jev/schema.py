"""Jev Quality Decision Gate · desktop-pet 结构化证据 schema。

本文件定义 evidence.json 的字段规范。
Python 测试产出事实 → evidence.json → Jev → PASS/REVIEW/FAIL。
Jev 不发明标准，只根据本 schema 中已定义的 acceptance criteria 判断。
"""
import json
import sys

SCHEMA_VERSION = "1.0.0"

REQUIRED_KEYS = {
    "project": str,
    "asset": {
        "walk_frames_total": int,
        "left_frames": int,
        "right_frames": int,
        "fps": int,
    },
    "visual_quality": {
        "height_cv": float,
        "head_width_cv": float,
        "badges": int,
        "holes": int,
        "fragments": int,
        "character_height": int,
    },
    "motion_quality": {
        "leg_reposition": bool,
        "phase_consistency": bool,
    },
    "runtime": {
        "gif_load": bool,
        "fps_match": bool,
        "runtime_error": bool,
        "gif_bottom_clip": bool,
    },
}

# 客观验收阈值（来源：WALK_ASSET_SPEC.md + qa_frames.py 既有标准）
THRESHOLDS = {
    "height_cv_max": 0.15,
    "head_width_cv_max": 0.15,
    "badges_max": 0,
    "holes_max": 0,
    "fragments_max": 0,
    "fps_min": 12,
    "frames_min": 8,
    # 系统成文角色高度（make_frames3d.py:36 FIT_H=176；F4 审计确立）
    "character_height": 176,
}


def validate_evidence(ev):
    """校验 evidence 结构是否完整。返回 (ok, missing_keys)。"""
    missing = []
    for key, typ in REQUIRED_KEYS.items():
        if key not in ev:
            missing.append(key)
            continue
        if isinstance(typ, dict):
            for sub, sub_t in typ.items():
                if sub not in ev[key]:
                    missing.append(f"{key}.{sub}")
                elif not isinstance(ev[key][sub], sub_t):
                    missing.append(f"{key}.{sub}(type:{sub_t.__name__})")
    return len(missing) == 0, missing


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: python schema.json <evidence.json>")
        print(f"schema version: {SCHEMA_VERSION}")
        print(f"required keys: {json.dumps(REQUIRED_KEYS, indent=2)}")
        print(f"thresholds: {json.dumps(THRESHOLDS, indent=2)}")
        sys.exit(0)
    ev = json.loads(open(sys.argv[1]).read())
    ok, missing = validate_evidence(ev)
    print(json.dumps({"valid": ok, "missing": missing}, indent=2))
