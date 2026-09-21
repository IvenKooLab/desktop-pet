"""Jev 决策引擎 · 结构化证据 → PASS / REVIEW / FAIL。

mock_decide(): 确定性规则引擎（离线 POC 主判定），逐项对照 schema.THRESHOLDS。
jev_decide(): 真实 Jev API 占位（需 JEV_API_KEY，接口确定后实现）。

决策契约：
- PASS   全部客观标准满足，且无指标落在警告带
- REVIEW 证据不确定：指标落在警告带（灰区），需人工复核
- FAIL   任一客观标准被违反
"""
import os

from schema import THRESHOLDS

# 警告带下界：指标超过该值但未超阈值 → REVIEW 而非直接 PASS
WARN_BAND = {
    "height_cv": 0.10,
    "head_width_cv": 0.10,
}


def mock_decide(ev: dict) -> dict:
    asset = ev.get("asset", {})
    vq = ev.get("visual_quality", {})
    mq = ev.get("motion_quality", {})
    rt = ev.get("runtime", {})

    failed = []
    review = []

    # ── 客观标准：违反即 FAIL ──
    if asset.get("walk_frames_total", 0) < THRESHOLDS["frames_min"]:
        failed.append(f"asset.walk_frames_total={asset.get('walk_frames_total')} < {THRESHOLDS['frames_min']}")
    if asset.get("left_frames", 0) < THRESHOLDS["frames_min"] // 2:
        failed.append(f"asset.left_frames={asset.get('left_frames')} < {THRESHOLDS['frames_min'] // 2}")
    if asset.get("right_frames", 0) < THRESHOLDS["frames_min"] // 2:
        failed.append(f"asset.right_frames={asset.get('right_frames')} < {THRESHOLDS['frames_min'] // 2}")
    if asset.get("fps", 0) < THRESHOLDS["fps_min"]:
        failed.append(f"asset.fps={asset.get('fps')} < {THRESHOLDS['fps_min']}")

    if vq.get("height_cv", 1.0) > THRESHOLDS["height_cv_max"]:
        failed.append(f"visual_quality.height_cv={vq.get('height_cv')} > {THRESHOLDS['height_cv_max']}")
    if vq.get("head_width_cv", 1.0) > THRESHOLDS["head_width_cv_max"]:
        failed.append(f"visual_quality.head_width_cv={vq.get('head_width_cv')} > {THRESHOLDS['head_width_cv_max']}")
    if vq.get("badges", 0) > THRESHOLDS["badges_max"]:
        failed.append(f"visual_quality.badges={vq.get('badges')} > {THRESHOLDS['badges_max']}")
    if vq.get("holes", 0) > THRESHOLDS["holes_max"]:
        failed.append(f"visual_quality.holes={vq.get('holes')} > {THRESHOLDS['holes_max']}")
    if vq.get("fragments", 0) > THRESHOLDS["fragments_max"]:
        failed.append(f"visual_quality.fragments={vq.get('fragments')} > {THRESHOLDS['fragments_max']}")

    if not mq.get("leg_reposition", False):
        failed.append("motion_quality.leg_reposition=false（qa_walk8 步幅交替检验未通过）")
    if not mq.get("phase_consistency", False):
        failed.append("motion_quality.phase_consistency=false（qa_walk8 垂直节奏检验未通过）")

    if not rt.get("gif_load", False):
        failed.append("runtime.gif_load=false（帧文件无法加载）")
    if not rt.get("fps_match", False):
        failed.append("runtime.fps_match=false（运行时 fps 与 animation.json 不一致）")
    if rt.get("runtime_error", False):
        failed.append("runtime.runtime_error=true（运行时出现异常）")

    if failed:
        return {
            "decision": "FAIL",
            "confidence": 0.98,
            "reasons": failed,
            "requires_human_review": False,
        }

    # ── 灰区：未违反但指标落在警告带 → REVIEW ──
    if vq.get("height_cv", 0.0) > WARN_BAND["height_cv"]:
        review.append(f"height_cv={vq.get('height_cv')} 落在警告带 ({WARN_BAND['height_cv']}, {THRESHOLDS['height_cv_max']}]")
    if vq.get("head_width_cv", 0.0) > WARN_BAND["head_width_cv"]:
        review.append(f"head_width_cv={vq.get('head_width_cv')} 落在警告带 ({WARN_BAND['head_width_cv']}, {THRESHOLDS['head_width_cv_max']}]")

    if review:
        return {
            "decision": "REVIEW",
            "confidence": 0.72,
            "reasons": review,
            "requires_human_review": True,
        }

    # ── 全部通过 ──
    return {
        "decision": "PASS",
        "confidence": 0.96,
        "reasons": [
            f"walk_frames_total={asset.get('walk_frames_total')} ≥ {THRESHOLDS['frames_min']}，左右各 ≥ {THRESHOLDS['frames_min'] // 2}，fps={asset.get('fps')}",
            f"height_cv={vq.get('height_cv')} / head_width_cv={vq.get('head_width_cv')} 均在阈值内",
            f"badges/holes/fragments = {vq.get('badges')}/{vq.get('holes')}/{vq.get('fragments')}",
            "步幅交替与垂直节奏检验通过；运行时加载与 fps 一致",
        ],
        "requires_human_review": False,
    }


def jev_decide(ev: dict) -> dict:
    """真实 Jev API 占位。接口确定后实现；当前任何情况都返回 REVIEW。"""
    if not os.environ.get("JEV_API_KEY"):
        return {
            "decision": "REVIEW",
            "confidence": 0.0,
            "reasons": ["JEV_API_KEY 未设置，无法调用真实 Jev API"],
            "requires_human_review": True,
        }
    return {
        "decision": "REVIEW",
        "confidence": 0.0,
        "reasons": ["Jev 真实 API 尚未实现（POC 阶段，mock_decide 为主判定）"],
        "requires_human_review": True,
    }
