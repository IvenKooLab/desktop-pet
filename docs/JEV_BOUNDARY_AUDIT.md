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

---

## 修复记录 · F1+F2（2026-09-21，同日完成）

**修复方式**（`tools/_build_av_walk.py` 单点修改，同时消除 F1+F2——同根因）：

- `sole_row()` 由"底部 25% 最宽行"（鞋面/脚背的偶然宽扫描线）改为
  **alpha 二值化后内容的最末行 = 真实接地线**（步行各姿态至少一只鞋贴地）；
- 二值化时序提前：定锚 mask 与最终贴图 mask 完全一致（旧版锚点用 alpha>96、
  贴图用 ≥128，两者不一致本身也是隐患）；
- `SIZE/FOOT_Y/REF_H/统一缩放/左右镜像` 全部未动。

**量化对比**（`tests/jev/placement_fix_verification.json`，前后同口径）：

| 指标 | Before | After |
|---|---|---|
| clipped frames | 8/8（clip_px 9~18） | **0/8** |
| 接地线（内容底行） | 恒 199（被裁切顶到边） | **恒 194**（FOOT_Y 设计值，jitter=0） |
| py 序列 | [57,55,57,57,64,58,57,56]（9px 不规则抖动） | [41×7,42]（1px = walk_06 源艺术高差） |
| 鞋底完整度 | 末 ~11px 被裁 | 完整（overlay 可视验证） |

视觉证据：`tests/jev/sole_anchor_overlay.png`（8 帧剪影叠画 + 接地线标线，
鞋底区放大条见该文件生成脚本）。

**修复后门禁状态**：`runtime.gif_bottom_clip → PASS`；qa_walk8 判定不变（其 FAIL 项
均为已分类的 StandardMismatch/MeasurementArtifact，按纪律未修改该工具）；
真实证据重采后 Overall 仍 **FAIL**——唯一剩余 FAIL = phase_consistency
（bounce，GenuineDefect，暂缓待标准拍板），符合"修 F1/F2 不污染判断边界"的预期。

**新发现 F4（记录，未修，超出本阶段授权）**：全套其它动画（idle/fall/cheer/fast/旧 walk）
人物高 176px、脚线 192~193；av_walk 人物高 154px——REF_H=874 是初版源帧（874px）
的身高基准，源素材重切后变为 763px，REF_H 未同步 → walk 状态人物比其它状态
小 12.5%。修复只需同步 REF_H（如 874→764），但会改变角色上屏尺寸，属视觉变更，
待 owner 拍板后与 bounce 决策一并处理。

---

## F4 专项审计 · 角色上屏尺寸一致性（2026-09-21，只读取证）

> 复现：`python tools/jev/audit_diagnostics.py` → D_size_consistency。
> 本阶段零生产修改：不改资产/builder/runtime/Jev。

### 1) 系统尺寸规范考古（逐族实测，全部 200×200 canvas，runtime 1:1 上屏）

| 族 | n | 人物高 | 接地线 | top | 内容宽max | 备注 |
|---|---|---|---|---|---|---|
| idle / bounce / fall / greet / shy / cheer / happy / fast_l / fast_r | 15 | **176** | 193 | 18 | 87~113 | 站立系基线（cheer/happy/fast 部分帧脚抬起=艺术） |
| walk_l / walk_r（旧 24 相位） | 48 | **176** | 188~193 | 13~18 | 98 | 步幅内抬脚=艺术 |
| grab | 2 | 175 | 184~186 | 10 | 108 | 悬空状态 |
| land | 1 | 141 | 199 | 59 | 100 | 落地压扁（设计） |
| sleep | 2 | 168~176 | 193~197 | 18~30 | 108 | 躺卧 |
| spin | 4 | **154** | 193 | 40 | 107 | 176×0.88 手工缩放（make_frames3d.py:538"缩放对齐新Sheet"） |
| **av_walk** | 16 | **153~154** | **194** | 41 | 92 | **唯一同时偏离高度基线与脚线的行走状态** |

- **成文常量**：`make_frames3d.py:36 FIT_H, FIT_W = 176, 168`（"单帧角色适配盒"）
  ——176 是系统成文基线，不是统计巧合；12 个站立/行走状态实测一致。
- **runtime 无二次缩放**：pet.py 无 zoom/subsample/resize，GIF 像素即上屏像素；
  也不存在状态切换额外缩放——尺寸差全部来自 GIF 本身。

### 2) REF_H=874 来源（git + 像素双重追溯）

- `git log -S "874" -- tools/`：874 随 builder 诞生于 **f63e370**（2026-09-20，
  "以最高帧身高为 176px 基准"），无更早出处。
- **874 的实物对应**：`characters/iven-pet/animations/walk/source/walk_sheet_8f.png`
  （4096×1024，8 条带）人物 bbox：mx<245 阈值下最高 **874px**（strip8；其余 858~861）。
- **单位错配**：REF_H 量在 **原始 Sheet 人物**（含抗锯齿晕环）上，而 builder 实际
  消费 **抠图切图**（rembg+defringe 后剩 762~764px，alpha>96 口径）。
  764 × (176/874) = **154px** —— 这就是 12.5% 差值的精确来源，与"素材换代未同步"
  叠加（切图管线多次重切，874 对应的 Sheet 世代早已不在磁盘上）。

### 3) A/B 模拟（纯内存，经真实 builder 数学，未触生产）

| | A：REF_H=874（现状） | B：REF_H=764（=当前切图最高身高） |
|---|---|---|
| scale | 0.20137 | 0.23037 |
| 人物高 | 153~154 | **176（全帧一致）** |
| foot line | 194 | **194（不变）** |
| top（头顶） | 41 | **19**（idle=18，差 1px） |
| 内容宽 max | 92 | 106（≤200，不裁边） |
| 裁切 | 无 | **无**（上余量 19px、下余量 5px） |

**"高度一致 + 脚线一致"可以同时成立**：FOOT_Y=194 不动的前提下，B 让 av_walk
达到 176px 且盒位与 idle 几乎重合（top 19 vs 18、foot 194 vs 193，各差 1px AA 级）。
冲突不存在——画布上方有 22px 余量可容纳放大。

### 4) 状态切换跳跃（现状 A 的量化后果）

runtime 直接切换 GIF，无插值：
- idle ↔ walk：高 176→154（**-22px / -12.5%**），头顶 18→41（**23px 跳变**），foot 1px
- fast → walk：同上 12.5% 缩放跳
- walk → fall：154→176 反向跳
即**每次进出步行状态角色必然瞬间缩放 12.5%**——确定性发生、非艺术意图
（builder 注释自证目标 176px）、无 runtime 缓冲。

头身比旁证（top-35% 头宽/身高）：idle 0.574 / fall 0.494 / av_walk 0.442~0.539。
该指标受跨代美术（3D 渲染 vs GPT Sheet）与步姿发丝/手臂混杂影响大，**不单独构成
同源或非同源证明**，仅记录。角色造型一致性属 art-side 审查，F4 只判定缩放一致性。

### 5) F4 判定

## **F4 = GenuineDefect**

判定依据：① 系统成文规范 FIT_H=176 + 12 状态实测一致；② builder 注释自证目标
176px 而实现交付 154px（自相矛盾）；③ REF_H=874 实测对应 Sheet 人物（含晕环），
builder 输入为抠图切图——缩放基建立在错误工件上，且切图管线多代重切后未同步；
④ 状态切换 12.5% 缩放跳变确定性发生且 runtime 无缓冲。

**建议修复参数**（只报告，本阶段未执行）：

| 项 | 现状 | 建议 |
|---|---|---|
| REF_H | 874 | **764**（= 当前切图 alpha>96 最高身高；素材再重切时须同步） |
| 人物高 | 153~154 | 176（全帧一致） |
| foot line | 194 | 194（不受影响） |
|头顶余量 | 41 | 19（≥安全边距，无裁切） |
| 状态切换跳变 | 12.5% / 23px | **归零**（1px AA 级） |
| 新裁切风险 | — | 无（模拟 B 验证 8/8 帧零裁切） |

**连带事项（owner 一并决策）**：
- spin 目前 154px（176×0.88 手工对齐的历史产物）——av_walk 修至 176 后 spin 成为
  剩余离群，是否同步属独立小项；
- 人物上屏将变大 14.4%（154→176）——这是修复的目的本身，但属可见视觉变更，
  批准权在 owner；
- Jev 各项维持不变：唯一真实 FAIL 仍为 bounce（DEFERRED），zigzag（DEFERRED）、
  head_width（MeasurementArtifact→REVIEW）不动，F4 不新入 schema 检查
  （尺寸基线已由本审计建立事实，待修复指令后可加检查项）。

---

## F4 修复记录（2026-09-21，owner 批准后的最小修复）

**修复方式**（`tools/_build_av_walk.py`）：废除硬编码 `REF_H=874`，新增
`measure_ref_h()`——每次构建对 8 张**实际输入切图**实测 alpha>96 bbox 高、取最高帧
（本次实测 764），`scale = TARGET_H(176) / ref_h`。缩放基准与消费工件永久同源，
素材再重切也不会复发。FOOT_Y / sole_row（F1/F2）/ SIZE / TARGET_H / 镜像全部未动。

**Before / After**（交付 GIF 实测，`tests/jev/f4_scale_verification.json`）：

| 指标 | Before | After |
|---|---|---|
| character height | 153~154 | **176（8/8 全一致）** |
| foot line | 194 | **194（不变）** |
| top | 41 | **19** |
| width max | 92 | 106（≤200，无裁边） |
| bottom clip | 0 | **0**（row199 前景=0，下边距 5px） |
| sole jitter | 0 | **0** |
| idle↔walk height delta | -22px（-12.5%） | **0** |
| idle↔walk top delta | +23px | **+1px（AA 级）** |

状态切换（fast→walk、walk→fall 同表）：高度 delta 全部归零，top/foot 差 ≤1px。
F1/F2 回归：零污染（foot 恒 194、无裁切、无抖动）。

**Jev 变更（最小且语义不变）**：新增证据字段 `visual_quality.character_height`
（交付 GIF 内容高众数）+ check `character_height == 176`（标准来源 =
make_frames3d.py:36 FIT_H 成文基线，classification=None → 违反即 FAIL）。
 bounce=FAIL、zigzag=REVIEW、head_width=REVIEW 语义原样。

**修复后门禁终态**：F1 PASS / F2 PASS / F4 PASS / head_width REVIEW /
zigzag REVIEW / **bounce FAIL（DEFERRED，唯一剩余 FAIL）**——Overall FAIL，
符合"F4 修复不能让 bounce FAIL 消失"的预期。

**Spin 留档**：154px，源于 make_frames3d.py:538-542 有明确"views_clean 人物偏大
~20%，缩放对齐新Sheet"注释的历史手工缩放。本阶段未修改，作为独立后续事项
（av_walk 已修复，spin 成为唯一的 154px 离群）。

---

## Bounce 决策前证据审计（2026-09-22，纯只读，零生产修改）

> 唯一问题：当前 8-frame av_walk 是否应把垂直 bounce 作为本作正式 Walk 的必需动画语义？
> 复现：`python tools/jev/audit_diagnostics.py` → E 项（bounce kinematics）。

### 1) 定义区分

| | 真 bounce | 腿部视觉运动 |
|---|---|---|
| 特征 | 结构锚点（头/躯干）y 随步态相位周期变化；或身高压缩/伸展 | 下域轮廓/步幅变化，上域不动 |
| 判定量 | head_band_y / torso_y / bbox top-h 的周期振幅 | stride 宽度波形、下域轮廓 |
| 注意 | com_y 受发丝质量分布影响大（与 head_w 强相关），不可单独作为身体位移证据 | |

### 2) 当前 8 帧实测（交付层 + 艺术层双视角）

| 量 | 振幅 | 判读 |
|---|---|---|
| bbox top / bottom / h | **0 / 0 / 0 px** | 身体包络完全不动、无压缩 |
| 头部（耳机带刚性锚 y） | **0.79px** | 头顶不随步态运动 |
| 躯干带 / 骨盆带 y | 3.02 / 2.25px | 带内质量分布噪声（手臂/腿像素进出），非身体位移 |
| com_y | 10.89px | **发丝质量伪影**：与 head_w（70↔96，发丝开合 37%）强相关，F2→F3 跳 9.6px 恰为发丝从收到扬帧 |
| stride（脚底行宽） | 12px | 腿部交替存在且连续 |
| 艺术层源高 | 2px（762~764） | 渲染当量 **0.46px**——源素材也不含可用垂直信息 |

**结论：当前 8 帧不存在任何真 bounce，连"幅度接近 0 的微弱证据"都没有**
（结构锚点 ≤1px）。运动感由腿交替（stride 43~55 连续波）+ 发丝摆动（head_w 70~96）
两条通道承担。

**相位结构**：stride 波形 [55,54,52,54,52,43,50,52] 无 C/D/P/U 锯齿；head_w 呈
{F1,F2}/{F3-5}/{F6-8} 三组渐变——当前 Sheet 是**连续渐变 8 帧**，不是标准
4 相位×2 结构。**"Down 最低 / Up 最高"的 bounce 语义在当前素材上没有帧锚点**。

### 3) 系统动画语言的垂直振幅（风格参考，非硬标准）

| 动画 | 垂直振幅 | 来源 |
|---|---|---|
| 旧 walk（24 相位程序） | **5px**（top 13~18） | stride() 的 dy=6u²-4 数学伴生物（设计 6px） |
| fast | **4px**（top 14/18） | 过渡帧 dy=-4 |
| happy（情绪跳） | 8px（top 10/18，脚离地） | dy=-8 |
| idle 呼吸 | 0px（垂直向） | — |
| bounce 状态帧 | 0px（pet.py:741 只播两帧，无窗口 y 位移） | — |

行走类状态历史带 4~5px 垂直运动，但它们是**程序生成管线的伴生输出**，
不是任何产品文档的要求。

### 4) 角色美术特点（几何证据）

- chibi 大头：头部（top35% 带）宽/身高 ≈ 0.57——头是最大质量块，头部位移在视觉上极显眼；
- 运动感双通道已存在：发丝开合 37%（70↔96px）+ 腿部连续交替（stride 12px 摆动）；
  客观上 walk 识别性有两通道支撑，"是否足够"属观感判断；
- 若加 2~4px bounce：幅度为身高 1.1~2.3%，在角色动画常规（2~5%）低端，
  幅度本身不越界；**风险全部在实现路径**（见下）。

### 5) 鞋底接地约束下的三条实现路径

| 方案 | 做法 | 判定 |
|---|---|---|
| A 整体 dy | 全帧正弦位移 | **技术缺陷明确**：直接破坏 F2 刚钉死的接地线（sole 194 变 dy 序列→鞋底滑动/离地）；且 Down 踩实/Up 离地语义在连续渐变 Sheet 上无相位锚点可对齐 |
| B 身体 bounce+脚接地 | 身/腿分层 | 当前是整帧无分层资产——需部件化或重绘，成本最高 |
| C 压缩/伸展 | Down 压扁/Up 拉长 | 干净路径=**重生成 Sheet**（带压缩姿态）；程序 y-scale squash 会等比缩宽、产生"呼吸"而非步态 bounce，且污染交付物 |

**在不重生成资产的前提下，不存在技术干净的 bounce 注入路径。**

### 6) qa_walk8 垂直节奏标准的 provenance 审计

- **来源**：qa_walk8.py 唯一 commit 7922aec——预写 spec（当时 8 帧素材不存在），
  docstring 一行"垂直节奏（Down 最低 / Up 最高）"，**代码只打印、从未 enforce**；
- **产品依据检索**：WALK_ASSET_SPEC 全文无"bounce/垂直/弹跳"要求；最接近的是
  J 项"重心变化"（8c8b64c 引入，人工评分、语义模糊——腿部交替同样改变重心）
  与 prompt 模板一句"身体重心发生自然变化"（对生成器的提示语，交付 Sheet 未实现
  仍被人工验收通过）；
- **针对旧结构**：是——Down/Up 术语与 zigzag 同源，假设 C/D/P/U 结构；
  当前连续渐变 8 帧无此锚点；
- **Standard provenance = weak / undocumented**；
  **Current bounce rule validity = QUESTIONABLE**（作为"当前 8 帧的硬性产品标准"
  不成立：无产品文档背书 + 从未执行 + 结构语义失配；但项目动画语言的 4~5px
  垂直传统给了它风格层面的参考价值，故不判 INVALID/建议直接删除）。

### 7) 结论

## **Bounce product decision = C（REVIEW，Product visual decision）**

不强行 A/B 的理由：工程事实已全部查清（现状 0 振幅、双运动通道存在、系统语言
4~5px、方案 A 技术缺陷、标准 provenance weak），但"当前 walking 观感是否足够生动"
是像素证据无法替代的人眼判断；且两个方向成本悬殊（改 QA 一行 vs 重出 Sheet），
必须由 owner 亲自观看后定夺。

**最小人工评审证据集**（全部已存在，零生成）：
1. `frames3d/av_walk_r_00..07.gif` 循环播放（12fps，看当前 walking 是否"死板"）；
2. `frames3d/walk_r_0..23.gif`（带 5px 垂直节奏的旧程序步行，作对照）；
3. `frames3d/fast_r_0/1.gif`（4px 快走）；
4. 注意观察点：当前角色腿部+发丝运动是否已足够；若补 bounce，头顶位移是否显突兀
   （chibi 头占比 0.57）。

**决策树**（owner 拍板后执行）：
- **拍 A（要 bounce）**：唯一干净路径=让 GPT 重出带 Down/Up 压扁/伸展的 Sheet；
  建议规格：垂直振幅 3~5px @176（≈2~3% 身高，落在系统语言区间）、
  Contact 踩实/Up 微离地 ≤2px、发丝运动保持；新 Sheet 须先过"素材结构验证"
  （C/D/P/U 锚点存在性）再进 builder；不建议 runtime 后处理（方案 A 破坏接地、
  方案 C 程序 squash 等比缩宽）；
- **拍 B（不要 bounce）**：标准治理动作=qa_walk8 垂直节奏标注 legacy（或修订）、
  checks.py 将 phase_consistency 分类由 GenuineDefect 改 StandardMismatch（→REVIEW
  不阻断）——须留痕本文件，Jev FAIL 随之解除；
- **维持 C**：phase_consistency 保持 GenuineDefect→FAIL 但标记 DEFERRED 不阻断
  pipeline（与现状一致）。
