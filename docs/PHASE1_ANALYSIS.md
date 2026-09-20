# Phase 1 前置分析 · desktop-pet 动画系统现状与改造方案

> 按「只分析、不写代码」要求产出。分析人：ZCode（desktop-pet 全链路原作者）。
> 结论可直接作为 Phase 1（Walk 动画）任务单的依据。

---

## 1. 当前架构分析

### 运行时 pet.py（~700 行）
- **状态机**：13 状态（IDLE/WALK/RUN/GRAB/FALL/LAND/SLEEP/GREET/CHEER/SPIN/BOUNCE/HAPPY/SHY），50ms 固定逻辑步长
- **双层主循环**：逻辑 50ms（平台/物理/状态迁移）+ ~60fps 渲染层（墙钟相位取帧、逻辑步间亚像素位置插值、帧切换去重）
- **窗口即平台**：EnumWindows + DWM 可视边界 → 平台列表 `[(x0, surface_y, x1)]`；支撑判定 FOOT_INSET=40；边缘 60% 掉头 / 40% 走空跌落；基础地面 = 任务栏顶边
- **单实例**：TCP 127.0.0.1:56570（进程死端口即释放）
- **动画播放**：`_anim(帧名列表, 帧周期ms)` + 渲染层墙钟相位；走路序列按可用文件动态生成，周期 = WALK_CYCLE_MS/帧数

### 资产管线 tools/make_frames3d.py
- **切图三模式**：`blue`（青蓝底颜色闸门 G-R≥14 + 梯度洪泛）/ `checker`（中性浅色规则）/ `rembg`（u2net + 滞后阈值 140/5 + 深色部件回收 + fill_holes）——三者都含组件过滤与 2px 辉光腐蚀
- **合成**：`on_canvas` = fit(168,176) 预乘 → 二值化 α≥160 → 品红 #FF00FF 画布（色键）→ <150px 岛清理
- **步态**：`stride(侧视图, dx)` 按行水平错位（剪腿）+ 颠步/倾斜；24 相位余弦连续 `dxs=28u`
- 辅助：`blend_poses`（预乘归一化混合）、`cut_single`（单人物直切）、`rough_boxes`（粗定位）

### 质检
- `qa_frames.py`：空帧 / 悬浮碎片 / 内部孔洞 / 头宽身高一致性（正面/侧视双中位数）
- `qa_diff.py`：源切图按管线同款变换回放，与成品帧对齐搜索量化 lost%（方法学假阳性已注明）

### 资产现状
73 帧 GIF（品红色键，200×200）；锚点 = 画布底边中心（**隐式约定，无元数据**）；
帧名扁平 `walk_l_0..11 / idle_0..2 / ...`；**帧→动作的映射硬编码在 pet.py 状态机分支里**。

---

## 2. 当前问题清单（A–F 分类）

### A. 角色美术资产问题
- **A1【最关键】走路循环 Sheet 的 4 个姿势是 4 次独立生成**，镜头角度不一致（纯侧面 ↔ 3/4 斜侧交替）。播放时头部视角每帧翻转 = 「不连贯」的主因。补间/混合救不了（跨视角混合 = 双曝光鬼影，已实测）。
- A2 跨批次生成比例漂移：不同批次头宽差达 25%（历史靠手工 0.83/0.88 缩放补丁）。
- A3 角色常驻手持场记板：遮挡躯干与手臂，步态观感差（用户已定：Walk 不持板，板只用于 Happy/Cheer/Special）。

### B. 帧间运动问题
- B1 程序步态（stride 剪腿）无关节：整腿刚性滑动，无膝盖弯曲、无重心转移——「滑步感」。
- B2 真帧路线仅 4 姿势 + 硬切；插补间帧因 A1 视角不一致产生双曝光。

### C. 缩放/定位问题
- C1 锚点为隐式约定（bottom-center），无 `anchor` 元数据，换素材即破坏。
- C2 跨批次尺寸差靠运行时看不出、导入期无检测（qa_frames 的事后检查可发现但不能阻止）。

### D. 播放时间轴问题
- D1 帧周期 = WALK_CYCLE_MS/帧数，硬编码在状态机；无 fps / loop 元数据。
- D2 帧名列表内联在各状态分支里——新增/换动作必须改 pet.py。

### E. alpha/透明边缘问题
- E1 主链路已解决：滞后阈值 + 深色回收 + fill_holes + 预乘空间变换 + α≥160 二值化 + 品红色键。
- E2 残留：weak≥5 会多吸 2~3px 辉光（靠 glow_cut=4 腐蚀抵消，参数手工调）；白色细节（板条纹）依赖 fill_holes。

### F. 状态机问题
- F1 同 D2：动作定义与状态机耦合，无数据驱动。
- F2 无动作打断/混合系统：SPIN 中被 GRAB 直接打断无过渡（观感可接受，但扩动作后会放大）。

---

## 3. 应该保留的代码（不要重写）

| 模块 | 保留理由 |
|---|---|
| pet.py 状态机骨架 + 窗口平台 + 双层主循环 + 单实例 + crash.log | 经过实机验证，语义稳定 |
| make_frames3d 的 `rembg_fg`（滞后阈值+深色回收+fill_holes）、`cut_sheet` 三模式、`rough_boxes`、`on_canvas`（预乘/色键/岛清理）、`defringe`、`blend_poses`、`stride` | 抠图三层保险与合成管线是全部实测教训的结晶 |
| qa_frames.py 全部 | 数值自检框架直接复用 |
| qa_diff.py 框架（对齐搜索 + lost% 量化） | 保留，MAP 表改为数据驱动 |
| pet.py `_load_profile()` 角色加载、Studio 的角色管理 | 已实现用户配置闭环 |

---

## 4. 应该修改的代码

| 位置 | 改法 |
|---|---|
| pet.py 动画播放 | 内联帧名列表 → `AnimationClip` 数据驱动（读 animation.json：frames/fps/loop/anchor/facing）；帧名解析失败静默回退（保最小角色集可运行） |
| pet.py 状态→动画映射 | 提取为常量映射表 `STATE_CLIPS = {IDLE: "idle", WALK: "walk", ...}`；菜单按 clip 存在性动态生成（沿用现有守卫模式） |
| make_frames3d | walk 24 相位段迁移至新 `tools/make_animation.py`（导入 stride/on_canvas 复用）；切片抠图段保留 |
| qa_diff.py | MAP 硬编码 → 扫描 animations/*/animation.json 自动生成对比任务 |
| 新增 qa_animation.py | 导入期检查（尺寸/头宽方差/脚底基线/居中度/碎片），超阈 FAIL 不进运行时 |

---

## 5. 推荐资源目录结构

```
characters/iven-pet/
├── master/                      # 角色圣经（出图母版，AI 生成的身份锚）
│   ├── avatar_master.png
│   └── character_master_sheet.png
├── reference/                   # 其他参考（配色/细节行）
├── animations/
│   ├── idle/    ├── walk/    ├── sleep/    ├── happy/
│   ├── shy/     ├── grabbed/ └── spin/
│   └── 每个动作 = animation.json + frames/*.png
└── character.json               # 角色级元数据（默认动作/台词/母版指针）
```

---

## 6. 推荐动画数据结构

```json
{
  "name": "walk",
  "fps": 12,
  "loop": true,
  "facing": "right",
  "anchor": "foot_center",
  "frames": ["walk_01.png", "…", "walk_08.png"],
  "source": "sheet",          // sheet | procedural | ai —— 溯源
  "qa": {"checked_at": "…", "head_width_cv": 0.03, "foot_baseline_var": 0.0}
}
```
`character.json`：
```json
{
  "name": "iven-pet",
  "default_action": "idle",
  "master": "master/avatar_master.png",
  "lines": ["…"],
  "actions": {"idle": "animations/idle", "walk": "animations/walk", "…": "…"}
}
```
运行时兼容：`_load_profile()` 优先找 `animations/` 新结构，找不到回退内置 `frames3d/`（最小角色集永不崩）。

---

## 7. Phase 1 Walk 动画最小实现方案

**前置（用户）**：一张**同机位同比例**的连续走路 Sheet（右向 8 相位：Contact/Down/Passing/Up ×2，透明底或纯色底）。
用户新给的 Character Master Sheet 中「行走姿势」即为标准姿势参考。

**管线（确定性，零 AI）**：
1. `cut_sheet(bg=rembg)` 逐姿势切图（粗定位+逐人过模型，分辨率充足）
2. 归一：脚底基线（bottom foot_center）对齐；**头宽方差 >10% 的帧直接 FAIL**（导入期拒绝，不偷偷缩放）
3. 写 `animations/walk/animation.json`（fps=12, loop, facing=right, anchor=foot_center）
4. `qa_animation.py` 五项检查全过才放行

**pet.py**：
1. `AnimationClip` 加载器（~40 行）：读 json、预载帧、按 fps/墙钟推进、loop、镜像接口
2. WALK/RUN 状态改用 walk clip；**水平镜像生成左向**（facing=right 单套素材）
3. 步速与 fps 匹配：像素/秒 = 步幅×fps 恒定（脚步无滑步）
4. 其余状态暂用旧帧（兼容回退），Phase 4 逐个迁移

**验收**：qa_animation 五项全过 + 深底/浅底双接触表目检 + 用户实机验收（头部稳定/脚底不漂/无忽大忽小）。

**规模**：管线 ~150 行 + pet.py ~60 行 + 8 帧素材处理；不含等素材时间 ≈ 半天。
