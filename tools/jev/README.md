# Jev Quality Decision Gate（POC）

结构化证据 → 质量决策的独立验收层。**Jev 不写代码、不改素材、不发明标准**——只对照
`schema.THRESHOLDS`（源自 `docs/WALK_ASSET_SPEC.md` 与 `tools/qa_walk8.py` 既有验收标准）
对客观测试产出的事实做 PASS / REVIEW / FAIL 判断。

```
客观测试（collect_evidence / qa_walk8 / smoke）
        │  事实，JSON
        ▼
  evidence.json  ──→  tools/jev/evaluate.py  ──→  ✅ PASS   全部标准满足且无灰区
                      （mock 确定性引擎 /       ──→  ⚠️ REVIEW 证据不确定或落警告带，需人工复核
                        jev 真实 API 占位）     ──→  ❌ FAIL   任一客观标准被违反
```

## 用法

```bash
PY=D:/tools/ComfyUI-aki-v3/python/python.exe

# 1. 从仓库真实素材采集证据
$PY tools/jev/collect_evidence.py -o tests/jev/fail.json

# 2. 判定（离线 mock，无需任何 API Key）
$PY tools/jev/evaluate.py tests/jev/fail.json --mock

# 3. 决策引擎自测（tests/jev 三用例：pass→PASS review→REVIEW fail→FAIL）
$PY tools/jev/evaluate.py --selftest

# 4. 只校验 evidence 结构
$PY tools/jev/schema.py tests/jev/pass.json
```

## 文件

| 文件 | 职责 |
|---|---|
| `schema.py` | evidence 字段规范 + 客观阈值（验收标准唯一来源，改标准只改这里） |
| `collect_evidence.py` | 从仓库真实素材测得证据（测量口径复用 qa_walk8，见下） |
| `decision.py` | 决策引擎：`mock_decide`（确定性）/ `jev_decide`（API 占位，恒 REVIEW） |
| `evaluate.py` | CLI 入口 + `--selftest` |

## 测量口径（全部复用既有标准，无新发明）

- **mask**：源 PNG（RGBA）用 alpha≥160（与 `on_canvas` 二值化同口径）；品红键控画布用
  `qa_walk8.keyed_mask`
- **头宽/身高**：可见 mask，top 35% 最大行宽 / 全高（qa_walk8 同款）
- **碎片/孔洞/徽章**：非主连通域 >0.2% 主域面积、封闭背景域 >200px（qa_walk8 同款）；
  徽章=底部 12% 带内的独立域（"1 Contact" 标签历史坑）
- **leg_reposition**：脚底基线行跨度奇偶锯齿交替（qa_walk8 Layer2 原公式）
- **phase_consistency**：身高序列奇偶锯齿交替（Down 低 / Up 高 意图）
- **fps_match**：animation.json fps 与 pet.py 8 帧 av_walk 分支 `round(1000/12)` 交叉核对

## mock 决策规则（Decision Boundary Audit 后）

每个检查项独立产出 `{check, measurement, status, classification, standard_source, reason}`：

1. **违反客观标准** → 按 `checks.py` 分类调节：
   - `GenuineDefect`（真实缺陷）→ **FAIL**
   - `MeasurementArtifact`（测量伪影，如发丝摆动混入头宽）→ **REVIEW** 人工复核
   - `StandardMismatch`（规则来自旧 gait 假设，如 period-2 锯齿）→ **REVIEW** 人工重标定
2. **警告带** `(0.10, 0.15]`（height_cv / head_width_cv）→ **REVIEW**
3. 全部达标且无灰区 → **PASS**
4. evidence 结构不完整 → **REVIEW**（列出缺失字段）

整体 = 最坏项：任一 FAIL → FAIL；否则任一 REVIEW → REVIEW；否则 PASS。

**追溯纪律**：每个 FAIL 必须沿 `check → standard_source（文档/代码出处）→ threshold →
measurement → Jev` 追溯。分类表在 `checks.py`（由人工审计写入、附证据出处；
Jev 只消费，不发明分类）。审计全文：`docs/JEV_BOUNDARY_AUDIT.md`。

**取证工具**：`python tools/jev/audit_diagnostics.py` 复现全部审计数字
（头宽带分解 / 交付 GIF 垂直测量 / builder 复算——底部裁切与 sole 抖动证明）。

## 真实 Jev API（占位）

`jev_decide()` 需要 `JEV_API_KEY` 环境变量；接口确定前任何输入都返回 REVIEW。
**API Key 永不入库**（走环境变量）。
接入契约已固化：`build_jev_payload(ev)` 把 **acceptance criteria（阈值+标准出处）+
structured evidence + classifications** 一起发送，指令明确"按给定标准逐项判定"——
而不是发"这个动画好吗"式的开放提问。

## 已知事实（2026-09-21 F1/F2 修复后）

当前已入库 8 帧 walk 素材的真实证据在 `tests/jev/fail.json`，判定 **FAIL**：
- `phase_consistency` = GenuineDefect（bounce 缺失，**暂缓**——产品/动画标准未拍板）
- `gif_bottom_clip` 已修复（F1：接地线恒 194、裁切 0；sole 抖动 F2 一并消除，
  前后对比 `tests/jev/placement_fix_verification.json`）
- `leg_reposition` = StandardMismatch（period-2 锯齿规则对 8 帧结构失效，**暂缓**）
- `head_width_cv` 警告带 = MeasurementArtifact（发丝摆动混入）
完整证据链见 `docs/JEV_BOUNDARY_AUDIT.md`（含修复记录与新发现 F4 尺寸不一致）。
