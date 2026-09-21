"""Jev 决策引擎 · 结构化证据 → 逐项判定 → PASS / REVIEW / FAIL。

mock_decide(): 确定性规则引擎（离线 POC 主判定）。对每个检查项产出：
    {check, measurement, status: PASS|FAIL|REVIEW, classification, standard_source, reason}
整体决策 = 最坏项：
    任一 FAIL（GenuineDefect 违反）      → FAIL
    否则任一 REVIEW（警告带/伪影/规则失效）→ REVIEW
    否则                                 → PASS

分类语义（分类表在 checks.py，由人工审计维护，Jev 只消费）：
    违反 + GenuineDefect       → FAIL   真实缺陷
    违反/警告带 + MeasurementArtifact → REVIEW 测量口径受混杂，人工复核
    违反 + StandardMismatch    → REVIEW 规则对当前资产结构失效，人工重标定
Jev 不发明阈值、不改 gait 定义、不用常识覆盖项目标准。

build_jev_payload(): 真实 Jev API 的输入契约——发送
    acceptance criteria（阈值+标准出处） + structured evidence + classifications，
    而不是"这个动画好吗"式的开放提问。jev_decide() 仍为占位。
"""
import os

from schema import THRESHOLDS

# 警告带下界：指标超过该值但未超阈值 → REVIEW 而非 PASS（schema 阈值不变）
WARN_BAND = {
    "height_cv": 0.10,
    "head_width_cv": 0.10,
}


def _chk(check, measurement, ok, warn, classification, source, note, fail_reason, warn_reason):
    """组装单项判定。ok=True 且无 warn → PASS；分类调节 FAIL→REVIEW 的降级。"""
    if ok and not warn:
        return {"check": check, "measurement": measurement, "status": "PASS",
                "classification": classification, "standard_source": source}
    if ok and warn:
        return {"check": check, "measurement": measurement, "status": "REVIEW",
                "classification": classification, "standard_source": source,
                "reason": warn_reason}
    # 违反：分类决定 FAIL 还是 REVIEW
    if classification == "MeasurementArtifact":
        return {"check": check, "measurement": measurement, "status": "REVIEW",
                "classification": classification, "standard_source": source,
                "reason": f"{fail_reason}；但分类=MeasurementArtifact（{note}）→ 人工复核"}
    if classification == "StandardMismatch":
        return {"check": check, "measurement": measurement, "status": "REVIEW",
                "classification": classification, "standard_source": source,
                "reason": f"{fail_reason}；但分类=StandardMismatch（{note}）→ 人工重标定规则"}
    return {"check": check, "measurement": measurement, "status": "FAIL",
            "classification": classification, "standard_source": source,
            "reason": f"{fail_reason}；{note}" if note else fail_reason}


def mock_decide(ev: dict) -> dict:
    import checks as reg

    asset = ev.get("asset", {})
    vq = ev.get("visual_quality", {})
    mq = ev.get("motion_quality", {})
    rt = ev.get("runtime", {})
    out = []

    # ── asset ──
    for key, need, label in (
        ("walk_frames_total", THRESHOLDS["frames_min"], "帧数"),
        ("left_frames", THRESHOLDS["frames_min"] // 2, "左向帧数"),
        ("right_frames", THRESHOLDS["frames_min"] // 2, "右向帧数"),
    ):
        c = f"asset.{key}"
        m = reg.get(c)
        out.append(_chk(c, asset.get(key), asset.get(key, 0) >= need, False,
                        m.get("classification"), m.get("standard_source"), m.get("note", ""),
                        f"{label}={asset.get(key)} < {need}", ""))
    c = "asset.fps"
    m = reg.get(c)
    out.append(_chk(c, asset.get("fps"), asset.get("fps", 0) >= THRESHOLDS["fps_min"], False,
                    m.get("classification"), m.get("standard_source"), m.get("note", ""),
                    f"fps={asset.get('fps')} < {THRESHOLDS['fps_min']}", ""))

    # ── visual_quality ──
    for key, thr, warn_at, unit in (
        ("height_cv", THRESHOLDS["height_cv_max"], WARN_BAND["height_cv"], ""),
        ("head_width_cv", THRESHOLDS["head_width_cv_max"], WARN_BAND["head_width_cv"], ""),
    ):
        c = f"visual_quality.{key}"
        m = reg.get(c)
        val = vq.get(key, 1.0)
        out.append(_chk(c, val, val <= thr, val > warn_at,
                        m.get("classification"), m.get("standard_source"), m.get("note", ""),
                        f"{key}={val} > {thr}",
                        f"{key}={val} 落在警告带 ({warn_at}, {thr}]"))
    for key, thr in (("badges", THRESHOLDS["badges_max"]),
                     ("holes", THRESHOLDS["holes_max"]),
                     ("fragments", THRESHOLDS["fragments_max"])):
        c = f"visual_quality.{key}"
        m = reg.get(c)
        val = vq.get(key, 0)
        out.append(_chk(c, val, val <= thr, False,
                        m.get("classification"), m.get("standard_source"), m.get("note", ""),
                        f"{key}={val} > {thr}", ""))

    # character_height：必须精确等于系统成文基线（F4）
    c = "visual_quality.character_height"
    m = reg.get(c)
    val = vq.get("character_height", 0)
    out.append(_chk(c, val, val == THRESHOLDS["character_height"], False,
                    m.get("classification"), m.get("standard_source"), m.get("note", ""),
                    f"character_height={val} != 系统统一基线 {THRESHOLDS['character_height']}"
                    f"（缩放基准与实际工件错位，见 F4 审计）", ""))

    # ── motion_quality ──
    for key, label in (("leg_reposition", "步幅交替"), ("phase_consistency", "垂直节奏")):
        c = f"motion_quality.{key}"
        m = reg.get(c)
        val = mq.get(key, False)
        out.append(_chk(c, val, bool(val), False,
                        m.get("classification"), m.get("standard_source"), m.get("note", ""),
                        f"{label}检验未通过（qa_walk8 口径）", ""))

    # ── runtime ──
    for key, label in (("gif_load", "GIF 加载"), ("fps_match", "fps 一致性")):
        c = f"runtime.{key}"
        m = reg.get(c)
        val = rt.get(key, False)
        out.append(_chk(c, val, bool(val), False,
                        m.get("classification"), m.get("standard_source"), m.get("note", ""),
                        f"{label}未通过", ""))
    c = "runtime.runtime_error"
    m = reg.get(c)
    err = rt.get("runtime_error", False)
    out.append(_chk(c, err, not err, False,
                    m.get("classification"), m.get("standard_source"), m.get("note", ""),
                    "运行时/采集过程出现异常", ""))
    c = "runtime.gif_bottom_clip"
    m = reg.get(c)
    clip = rt.get("gif_bottom_clip", False)
    out.append(_chk(c, clip, not clip, False,
                    m.get("classification"), m.get("standard_source"), m.get("note", ""),
                    "交付 GIF 内容触及画布末行（底部裁切，违反 builder FOOT_Y 锚定设计）", ""))

    statuses = [o["status"] for o in out]
    if "FAIL" in statuses:
        decision, conf = "FAIL", 0.98
    elif "REVIEW" in statuses:
        decision, conf = "REVIEW", 0.72
    else:
        decision, conf = "PASS", 0.96

    reasons = [f'{o["check"]}={o["measurement"]} → {o["status"]}'
               for o in out if o["status"] != "PASS"]
    if not reasons:
        reasons = ["全部客观标准满足，无警告带/伪影/规则失效项"]

    return {
        "decision": decision,
        "confidence": conf,
        "reasons": reasons,
        "checks": out,
        "requires_human_review": decision != "PASS",
    }


def build_jev_payload(ev: dict) -> dict:
    """真实 Jev API 的输入契约：标准 + 证据 + 分类上下文，一起发送。"""
    import checks as reg
    from schema import SCHEMA_VERSION
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_criteria": {
            "thresholds": THRESHOLDS,
            "sources": {k: v.get("standard_source") for k, v in reg.CHECKS.items()},
        },
        "classifications": {k: v.get("classification") for k, v in reg.CHECKS.items()},
        "evidence": ev,
        "instruction": "按给定 acceptance criteria 与 classifications 对 evidence 逐项判定；"
                       "不得发明新标准、不得修改阈值、不得以常识覆盖项目验收规则。",
    }


def jev_decide(ev: dict) -> dict:
    """真实 Jev API 占位。接口确定后：POST build_jev_payload(ev) → 解析判定。"""
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
        "reasons": ["Jev 真实 API 尚未实现（POC 阶段，mock_decide 为主判定）；"
                    "接入时将发送 build_jev_payload()：标准+证据+分类上下文"],
        "requires_human_review": True,
    }
