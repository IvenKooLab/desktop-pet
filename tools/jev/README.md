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

## mock 决策规则

1. 任一客观标准违反 → **FAIL**（confidence 0.98，逐条列出违反项）
2. 无违反但 `height_cv` / `head_width_cv` 落在警告带 `(0.10, 0.15]` → **REVIEW**（0.72）
3. 全部达标且无灰区 → **PASS**（0.96）
4. evidence 结构不完整 → **REVIEW**（0.5，列出缺失字段）

警告带下界在 `decision.WARN_BAND`。

## 真实 Jev API（占位）

`jev_decide()` 需要 `JEV_API_KEY` 环境变量；接口确定前任何输入都返回 REVIEW。
**API Key 永不入库**（走环境变量）。

## 已知事实（2026-09-21 采集）

当前已入库 8 帧 walk 素材的真实证据在 `tests/jev/fail.json`：动检两项
（leg_reposition / phase_consistency）未过——与 `python tools/qa_walk8.py` 的现行
FAIL 判定一致，根因是锯齿规则按旧 4 帧步态的 period-2 假设写死，8 帧
Contact/Down/Passing/Up 循环天然不满足；且基线对齐的源帧本身不含垂直弹跳。
素材是靠人工目检上线的。**这个差距正是 Jev 要暴露的东西**：后续由人工决策
（a）修素材补真弹跳/交替步幅，或（b）把标准按 8 帧结构修订——那是改
`schema.THRESHOLDS` / qa 工具的事，属于本 POC 范围之外。
