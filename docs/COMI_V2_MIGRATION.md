# 默认角色更新：Iven v2 原版绒质风格

2026-10-13 用户确认直接替换，以新完成的资源为后续维护基准。

## 当前默认

原版紫白短发、青蓝耳机、大头短身与紫色绒质卫衣保持一致。`assets/iven-v2/spritesheet.png` 为批准母版，73 个姿势包含九种状态与十六个视线方向。最终透明素材经边缘去色、Pets 格式、跳跃落地和独立方向审查；个别近垂直视线的衔接有人工接受的轻微警告，验证记录在同目录。

发布帧由 `tools/export_iven_v2.py` 生成。所有姿势使用同一个 192×208 到 200×200 的适配变换，GIF 背景保持精确品红色键，不引入品红混色；脚底约在第 193 行，沿用原运行时平台锚点。

`animation.json` 保存完整帧序列与每帧时长。待机使用六帧，移动使用八帧，挥手使用四帧，弹跳使用五帧；快走加快同套移动节奏。观察四周使用十六个视线姿势，菜单据此改名，不再宣称全身旋转。打板复用工作动作，开心复用挥手，害羞/抓取复用等待姿势；睡觉用闭眼待机，坠落/落地用跳跃对应姿势。它们是复用映射，不是额外生成的新动作。

## 后续更新

构建期安装 Pillow，运行：

```bash
python tools/export_iven_v2.py
python -m unittest discover -s tests -p test_animation_assets.py -v
python pet.py
```

Windows 打包继续用 `tools/build_exe.bat`，PyInstaller 会收集新增标准库模块；`frames3d` 数据目录包含时间轴 JSON。已有发布 EXE 需要重新打包后才包含新素材。

旧的整套资源在 `assets/legacy-pre-iven-v2/builtin` （制作器旧帧仅为历史归档）。回退可设置 `PET_FRAMES_DIR=assets/legacy-pre-iven-v2/builtin`；无 JSON 的旧角色沿用旧播放路径。旧素材生成脚本仅允许明确指定 `--legacy`，输出隔离的 `frames3d_legacy/`。

## 验证范围

时间轴边界与循环、无效/不完整自定义配置、发布 PNG/GIF 完整性以及实际 Pet 播放方法的旧格式回退由自动测试覆盖。导出 GIF 单独核验尺寸、精确色键、非空内容、同源文件与脚底范围。当前在 Mac 上完成静态与逻辑验证；Windows 透明窗口、拖拽、平台落地和最终 EXE 尚需 Windows 实机验证。

## 2026-10-14 范围调整

桌宠制作器、角色选择配置及三视图生成向导已移除。项目专注独立 Iven 桌宠，发布帧仅导出到 `frames3d/`。根目录 `README.md` 为中文主文档，英文版为 `README.en.md`。

## 日常小动作（2026-10-14）

新增伸懒腰、打瞌睡与玩魔方，参考 dsh-pet 的动作主题，以现有 Iven 待机帧生成补充素材，未复制对方角色。源图及切片坐标、共同缩放比例、源文件 SHA-256 和逐帧时间轴在 `assets/iven-v2/actions/`。补充动作共用一套缩放，不按姿势独立放大；脚底锚点维持 193。伸懒腰与瞌睡以默认待机姿势开头、结尾，魔方动作保留道具。自动轮播和手动菜单均支持三种动作；手动睡觉仍保持睡眠，瞌睡是一段有限时长的表演。

README GIF：`python tools/make_readme_previews.py`（Pillow）。运行回归测试：`python -m unittest discover -s tests`；Mac 构建：`zsh tools/build_macos.sh`。真实桌面拖动与 Windows 运行仍需实机检查。
