# Iven 新动作素材配方（ASSET RECIPE）

给 Iven 增加**全新动作**（新像素内容）的完整流程。编排已有帧（如 THINKING、
YAWN 这类复用帧的剪辑）不需要本文——那只是改 `tools/export_iven_v2.py` 的
`themed_clips()`。

整套流程分三段：**① AI 生成原始素材 → ② 一键打包成 sheet → ③ 发布与注册**。
其中 ②③ 已完全自动化；① 需要图像/视频生成工具（豆包、即梦、可灵、Runway、
GPT-4o 图像等，或继续交给 codex 姐姐）。

## 角色卡（所有提示词必须携带的一致性约束）

Iven 是 **3D 绒质手办**风格，任何生成提示词都要固定以下要素，并以
`frames3d/idle_0.png` 为造型/配色/比例的对照基准：

- 紫白短发、青蓝耳机、3D 绒质（fabric/plush figure）质感，柔和棚拍光
- 站姿比例：角色整体高度约占画幅 65%（头顶留 ~20%，脚底在 ~85% 高度线）
- 单帧正视图参考 `frames3d/idle_0.png`；配色以该帧为准（import 工具会做均色
  偏差体检，偏差 >40 会警告）
- **禁止**：2D 扁平插画风、改变发型/耳机/服装、长身比例、重新设计角色

## 路线 A · 图像生成（sheet 或帧序列，codex 姐姐路线）

已有先例：`assets/iven-v2/actions/little-breaks.png + .json`（伸懒腰/打瞌睡/
玩魔方就是这么进来的）。

提示词模板（按需替换"动作描述"）：

> 一只 3D 绒质手办风格的桌面宠物，紫白短发，戴青蓝色耳机，站在纯绿幕
> （#00FF00）背景前。动作：<动作描述，如"打哈欠并伸懒腰，先睁眼、闭眼张嘴、
> 再睁眼">。横排网格 6 格，同一角色、同一比例、同一光照，每格一个关键姿势，
> 脚底对齐同一水平线，正视图。参考图：<附 frames3d/idle_0.png>

产出两种都接受：

1. **帧序列目录**（推荐）：每帧一张 PNG → 直接走下面的"一键打包"
2. **整张 sheet + 手写 JSON**：需符合 schema（见 `little-breaks.json`）——
   `source/sha256/columns/rows/centers/baselines/scale/actions`

## 路线 B · AI 视频（动作连贯，dsh-pet 的做法）

用豆包/即梦/可灵/Runway 生成 10 秒绿幕视频，然后抽帧：

> 一只 3D 绒质手办风格的桌面宠物，紫白短发，戴青蓝色耳机，全程站在纯绿幕
> （#00FF00）背景前的地面上，比例固定不变。0–10 秒动作分解：<按秒写清各阶段>。
> 首帧和末帧都是标准正面站立姿势；角色头顶距画面顶部约 20% 高度，脚底踩在
> 约 85% 高度线；动作全程不超出画幅；镜头固定，正视图。

抽帧（每秒 8–12 帧够用，选 4–8 个关键姿势更好）：

```sh
ffmpeg -i action.mp4 -vf "fps=10" pet-work/raw/<name>/frame_%03d.png
```

## ② 一键打包（自动：抠像 → 收边 → 裁切 → 对齐比例 → sheet + JSON）

```sh
python tools/import_action.py --frames-dir pet-work/raw/<name> --name <ACTION>
# 常用：--ms 180（统一每帧时长）、--durations 200,150,...（逐帧）、
#       --key green|magenta|none（默认按四角自动检测）
```

产物落在 `pet-work/import/`（本地过程目录，**不直接发布**）。工具自动完成：
绿幕/品红键控、alpha 边缘收缩 1px、包围盒裁切、最高帧对齐 idle_0 角色高度、
单行 sheet 排版、脚底线/中心测量、sha256 与 JSON 写入、配色偏差体检。

## ③ 发布与注册（目测验收后）

1. 目测 `pet-work/import/<name>-sheet.png`：比例、配色、透明边缘与 Iven 一致
2. `mv pet-work/import/<name>-sheet.* assets/iven-v2/actions/`
3. 全量导出（重写 frames3d 的 PNG/GIF 与 animation.json）：
   `python tools/export_iven_v2.py`（需 Pillow）
4. 注册到两端运行时（代码改动，走评审）：
   - `animation_behaviors.json` + `animation_behaviors.py` 的 `DEFAULT_ACTIONS`
   - `pet.py`：右键菜单元组 + `_logic_step` 长动作分支元组
   - `IvenPet.swift`：菜单数组 + `ActionDeck` candidates + `BehaviorPolicy`
5. 回归：`python -m unittest discover -s tests`、`zsh tools/build_macos.sh`、
   `IvenPet --self-test`；Windows 侧色键 GIF 需实机补验
6. 质检（可选但推荐，需 numpy/scipy）：`python tools/qa_frames.py`

## 边界与红线（继承 AGENTS.md）

- 权威素材基准不变：不重新设计角色、不改 2D 母版、禁止逐帧独立缩放
- 新动作的透明边缘、统一比例、脚底线、时间轴必须全部重做检查
- 未验收的素材只留在 `pet-work/`，不进 `assets/`、不进发布包
- 观察四周类动作是视线动作；不要宣称完整 3D 转身（除非素材真的做到）
