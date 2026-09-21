# Jev Decision Boundary Audit（2026-09-21）

> 目标：把当前真实素材的 FAIL 拆解为 **真实质量缺陷 / 测量伪影 / 标准不适用**，
> 而不是让结果"变好看"。全部结论可由 `python tools/jev/audit_diagnostics.py` 复现。

```
Current HEAD  : 见 git log（本文件提交前的 HEAD = 882e997 之后的 feat/test 两连击）
Working tree  : clean（除本文档提交）
真实素材判定  : FAIL（2 GenuineDefect + 2 REVIEW，逐项见下）
```

---

## Q1 · head_width_cv = 0.1323

**classification: MeasurementArtifact（→ REVIEW）**

证据链：

1. **指标口径**：`tools/qa_walk8.py:87-88` 头宽 = 可见 mask 顶部 35% 区域内的最大行宽。
   顶部 35%（约 267px / 全高 763px）几乎完全被**头发**占据，不是颅骨。
2. **实测序列**（collect_evidence，alpha≥160 mask）：
   `head_widths = [336, 334, 408, 414, 410, 309, 304, 304]`
   帧 3-5 发丝外扬（408-414），帧 6-8 发丝后拢（304-309），帧 1-2 居中——方差跟随**发丝摆动相位**。
3. **刚性结构代理**（audit_diagnostics A 项）：对耳机做青色门控
   （`b>120 & b-r>40 & g-r>20`，耳机是全图唯一青色部件），
   跨 8 帧**垂直跨度 cv = 0.0051**（564-572px，几乎不动）、水平宽度 cv = 0.0493。
   → 头+耳机刚性结构跨帧稳定，头宽指标 13% 的方差来自发丝轮廓，不是头部结构变化。
4. **佐证**：8 帧蒙太奇目检（同脸/同耳机/同比例，仅发丝相位不同）。

结论：指标数值真实，但口径把发丝运动读成"头宽不一致"。分类 MeasurementArtifact；
Jev 语义：超警告带 → REVIEW 交人工，不自动 FAIL。若要可靠的头宽一致性检验，
应改测颅顶带或耳机间距——那是标准修订，归人工（见 Q2 同款纪律）。

## Q2 · period-2 zigzag 规则

**classification: StandardMismatch（→ REVIEW）**

代码证据：

1. `tools/qa_walk8.py:115-117`：
   ```python
   odd = foot_spans[0::2]; even = foot_spans[1::2]
   zigzag = all(a > b for a, b in zip(odd, even)) or all(a < b ...)
   ```
   邻位（period-2）配对——假设序列为 `宽,窄,宽,窄,…` 交替。
2. **考古**（git）：qa_walk8.py 立项于 `7922aec`（"walk/frames 目录就绪"=该目录当时为空），
   早于 8 帧素材落地的 `b9062fb`。立项时 frames3d 只有 24 相位程序步态
   （`walk_l/r_0..23`，`git ls-tree 7922aec` 可验）。该规则是给未来 Sheet 预写的 spec，
   预写时假设了旧 4 帧式 `contact,pass` 交替结构（与历代 4 相位素材一致）。
3. **交付结构**：`b9062fb` 提交信息明确 "Contact/Down/Passing/Up x2"。
   8 帧循环中 Contact(宽) 与 Passing(窄) 相隔 2 帧（period-4 子结构），
   相邻帧之间是 C→D→P→U 的渐变，不构成邻位交替。
4. **实测**：步幅序列 `[438,446,448,457,451,440,396,385]`（qa_walk8 脚底基线行口径）
   = 平滑波（max@帧4，min@帧8），对 period-2 检验结构性不可能通过。

结论：规则确实来自旧 gait 结构假设，对 8 帧 Contact/Down/Passing/Up 循环不适用。
分类 StandardMismatch；Jev 语义：REVIEW（该检查在规则按 8 帧相位重标定前不可信），
不作为素材 FAIL 依据。**重标定规则本身是标准治理动作，本阶段不做。**

## Q3 · phase_consistency = false

**classification: GenuineDefect（→ FAIL）——素材真实缺失垂直节奏，不是测量错误**

事实链（全部代码级/数值级）：

1. **测量口径无误**：垂直节奏 = 身高序列交替（qa_walk8.py:10 写明的 Down 最低/Up 最高意图）。
   实测艺术高度 `scaled_h = [154,154,154,154,154,153,154,154]`（audit_diagnostics C 项）
   —— 素材本身真的是平的（≤1px / 0.65%）。
2. **交付物同样无节奏**：交付 GIF（git 已跟踪）top_y =
   `[57,55,57,57,64,58,57,56]`。其中 ±4px 的位移不是 gait bounce，
   而是 `_build_av_walk.py` sole 行启发式（底部 25% 最宽行，:17-22）在不同步姿选到不同行
   造成的**不规则抖动**（py 序列 55~64，帧 5 突然下沉 9px）——与"Down/Up 节奏"无关，
   且违反该 builder 自己的 docstring 承诺"保证脚底不上下跳"（:3）。
3. **builder 无弹跳机制**：`_build_av_walk.py` 全文无 dy 表；唯一垂直逻辑是 sole 对齐。
   （对比：pet.py 渲染层 `_frame_at` 只选帧不改 y；WALK 分支只改 x——运行时也不补弹跳。）
4. **标准确实要求节奏（但从未被执行）**：qa_walk8.py:10 docstring 把"垂直节奏（Down 最低 /
   Up 最高）"写在 Layer-2 验收契约里；:120-124 只打印从不计入 problems——**工具实现缺口**，
   但 docstring 作为验收工具的书面规格仍然有效。
5. **项目先例**：`make_frames3d.py:504-508` 历代程序步行自带
   `dy = round(6u²-4)`（触地低 2px、过渡高 4px）弹跳；更早的 4 帧 GIF 亦有过渡帧 dy -4/-3。
   垂直 bounce 是本作步行动画的既有交付特征，av_walk 一代把它弄丢了。

结论：**A——当前素材真实缺失该动画特征**（非测量错误、非纯标准冲突）。
分类 GenuineDefect → FAIL 保持。
诚实备注：该判据的"硬度"目前只到 docstring 级（工具从未 enforce）；若人工决定
本作风格不需要 bounce，正确动作是修订标准（qa_walk8 + checks.py 分类 + 本文档留痕），
Jev 的判定会随之改变——而不是由 Jev 或本审计悄悄降级。

## 审计新发现（计划外，均为 GenuineDefect）

**F1 · 交付 GIF 全帧底部裁切**：`audit_diagnostics C 项`：8/8 帧 `py + scaled_h ≈ 210 > 199`
（画布末行），`cv.paste` 静默裁掉鞋底约 11px；交付 GIF 内容全部直触画布末行
（soles 恒 = 199）。违反 `_build_av_walk.py:3` 自己的 FOOT_Y=194 锚定设计。
已入 schema（runtime.gif_bottom_clip）→ FAIL。

**F2 · 交付 GIF 不规则垂直抖动**：上述 Q3-2 的 py 55~64 抖动。12fps 下帧 5 突降 9px
= 可感知的顿挫。根因是 sole 行启发式，修复归资产管线（下一阶段），本阶段仅记录。

**F3 · 证据溯源分裂**：`characters/` 整目录被 .gitignore 排除（.gitignore:16）——
8 张源 PNG 与 animation.json 均未入库，真正入库的交付物只有 frames3d/av_walk_*.gif。
collector 现同时测量两者并在 `_provenance` 注明来源。是否把 characters/ 入库
（可复现性 vs 仓库体积）留用户决策。

---

## 职责边界（本审计确立）

| 层 | 职责 | 不做 |
|---|---|---|
| **Deterministic test**（collect_evidence / audit_diagnostics / qa_*） | 按固定口径产出数字与序列 | 判好坏、改口径 |
| **Jev**（decision/evaluate） | 消费 checks.py 分类表，逐项出 PASS/REVIEW/FAIL，汇总最坏项 | 发明阈值、改 gait 定义、判"好看"、用常识覆盖标准 |
| **Human**（用户+监督） | 维护 checks.py 分类与阈值；处置 REVIEW；决定修素材还是修标准 | — |

## 修复优先级建议（下一阶段，需用户拍板）

1. F1 底部裁切（修 builder：sole 行改取真实贴地行，或 FOOT_Y 留足 margin 重出 GIF）
2. F2 sole 抖动（同一次 builder 修复）
3. phase_consistency（GPT 新 Sheet 带 Down/Up 压扁帧，或 builder 显式 dy 表——先由人工确认 bounce 是否为风格要求）
4. leg_reposition 规则按 8 帧相位重标定（标准修订）
5. head_width 口径改进（颅顶带/耳机间距）
6. F3 characters/ 是否入库
