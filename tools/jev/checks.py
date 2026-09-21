"""checks 注册表 · 每个检查项的标准来源 + 审计分类。

Decision Boundary Audit（2026-09-21）的结论固化于此。
核心纪律：每一个 FAIL 都必须能沿
    check → standard_source（文档/代码出处）→ threshold → measurement → Jev
追溯；分类（classification）只允许三种：
    GenuineDefect       真实质量缺陷：有客观证据证明素材违反既有要求 → FAIL
    MeasurementArtifact 测量伪影：指标受测量口径混杂（如发丝摆动），不能自动判 FAIL → REVIEW
    StandardMismatch    标准不适用：规则来自旧资产结构假设，对当前资产结构失效 → REVIEW
分类由人工审计写入本表（附证据出处）；Jev 只消费，不自行发明分类。
修订分类 = 修订本表 + 在 docs/JEV_BOUNDARY_AUDIT.md 留痕，属于标准治理动作。
"""

GenuineDefect = "GenuineDefect"
MeasurementArtifact = "MeasurementArtifact"
StandardMismatch = "StandardMismatch"

CHECKS = {
    # ── asset 数量/规格 ──
    "asset.walk_frames_total": {
        "standard_source": "tools/qa_walk8.py:75（需恰好 8 帧）+ docs/WALK_ASSET_SPEC.md 扩帧流程",
        "classification": None,
    },
    "asset.left_frames": {
        "standard_source": "运行时 pet.py:389（左右各需整 8 帧才启用真素材步行）",
        "classification": None,
    },
    "asset.right_frames": {
        "standard_source": "运行时 pet.py:389（左右各需整 8 帧才启用真素材步行）",
        "classification": None,
    },
    "asset.fps": {
        "standard_source": "characters/iven-pet/animations/walk/animation.json fps=12 + pet.py:393 round(1000/12)",
        "classification": None,
    },

    # ── visual_quality ──
    "visual_quality.height_cv": {
        "standard_source": "docs/WALK_ASSET_SPEC.md F 项（角色整体高度一致）+ qa_walk8.py:107（身高偏离中位≤12%）",
        "classification": None,
    },
    "visual_quality.head_width_cv": {
        "standard_source": "docs/WALK_ASSET_SPEC.md B 项（头部尺寸一致）+ qa_walk8.py:107（头宽偏离中位≤12%）",
        "classification": MeasurementArtifact,
        "note": "audit_diagnostics A 项：top-35% 带最大行宽被发丝摆动主导（帧 3-5 发丝外扬 408-414px vs 收拢 304-309px）；"
                "青色耳机门控（刚性结构代理）跨 8 帧 cv=0.0051 → 头部结构稳定，方差来自发丝轮廓。"
                "该指标超警告带时判 REVIEW 交人工，不自动 FAIL。",
    },
    "visual_quality.badges": {
        "standard_source": "docs/WALK_ASSET_SPEC.md 验收清单（无标注徽章；GPT 历史坑：图下方 1 Contact 标签）",
        "classification": None,
    },
    "visual_quality.holes": {
        "standard_source": "qa_walk8.py:60-66（封闭孔洞>200px）+ 头发掏空历史坑",
        "classification": None,
    },
    "visual_quality.fragments": {
        "standard_source": "qa_walk8.py:52-57（非主连通域>0.2%主域面积）",
        "classification": None,
    },

    # ── motion_quality ──
    "motion_quality.leg_reposition": {
        "standard_source": "qa_walk8.py:114-117（步幅锯齿交替：Contact 宽 ↔ Passing 窄）",
        "classification": StandardMismatch,
        "note": "规则为邻位 period-2 配对（values[0::2] vs values[1::2]），立项于 7922aec——"
                "当时 8 帧素材尚不存在（walk/frames 目录为空，frames3d 只有 24 相位程序步态），属预写 spec；"
                "交付步态结构为 Contact/Down/Passing/Up ×2（b9062fb 提交信息），实测步幅序列为平滑波"
                "（438,446,448,457,451,440,396,385），邻位锯齿对 8 帧结构失效。"
                "→ 判 REVIEW：需人工按 8 帧相位重标定规则后该检查才可信。",
    },
    "motion_quality.phase_consistency": {
        "standard_source": "qa_walk8.py:10,120-124（垂直节奏：Down 最低 / Up 最高；代码只打印未实现）"
                          "+ make_frames3d.py:504（历代交付步行均含 dy 弹跳先例）",
        "classification": GenuineDefect,
        "note": "audit_diagnostics B/C 项：交付动画无垂直节奏——艺术高度平（scaled 154×7+153×1），"
                "builder 无 dy 表。历代步行均带弹跳（make_frames3d.py:504 dy=6u²-4），本代丢失 → 真实缺失，判 FAIL。"
                "（原叠加的 sole 行检测抖动 ±4.5px 已随 2026-09-21 F2 修复消除，接地线恒定 194；"
                "bounce 本身属产品/动画标准决策，暂缓待 owner 拍板。）"
                "标准硬度的注意事项：该判据目前只存在于 qa_walk8 docstring（代码从未 enforce）；"
                "若人工决定本作风格不需要 bounce，应走标准修订（改 qa_walk8/本表），而非由 Jev 降级。",
    },

    # ── runtime ──
    "runtime.gif_load": {
        "standard_source": "运行时硬要求：pet.py 帧目录缺 idle_0.gif 即拒绝启动",
        "classification": None,
    },
    "runtime.fps_match": {
        "standard_source": "animation.json fps 与 pet.py:393 round(1000/12) 交叉核对",
        "classification": None,
    },
    "runtime.runtime_error": {
        "standard_source": "tools/smoke.py 冒烟约定（采集过程零加载异常）",
        "classification": None,
    },
    "runtime.gif_bottom_clip": {
        "standard_source": "_build_av_walk.py:3（锚定规则：脚底基线对齐 FOOT_Y=194）与 :11-12（SIZE=200 画布）",
        "classification": GenuineDefect,
        "note": "audit_diagnostics C 项（修复前）：8/8 帧 py+scaled_h≈210/209 > 199（画布末行），"
                "鞋底被静默裁切约 11px。根因 = sole 行启发式（底部 25% 最宽行）选中高于内容底的行。"
                "2026-09-21 F1 修复：锚点改取二值化内容末行（真实接地线），当前 8/8 帧底部=194、"
                "裁切=0（前后对比见 tests/jev/placement_fix_verification.json）。分类保留：若回归即 FAIL。",
    },
}


def get(check: str) -> dict:
    return CHECKS.get(check, {})
