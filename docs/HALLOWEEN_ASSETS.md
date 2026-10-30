# 万圣节动作维护

这批动作采用项目原有的「动作图 → 显式切片与整段统一标定 → PNG/GIF + 时间轴」流程。它们是 15–16 姿势的桌宠动画，不是固定 3D 模型，也不声称是连续生成的视频。

## 素材与表现

| ID | 内容 | 帧数 | 默认实际时长 |
| --- | --- | --- | --- |
| TRICK_OR_TREAT | 放板、提南瓜桶、收糖、放回与拿板 | 16 | 约 8.88 秒 |
| GHOST_SHEET | 拿白布、盖头探看、摘下放回 | 16 | 约 8.88 秒 |
| VAMPIRE_CAPE | 披上红里披风、展开与鞠躬、收回 | 16 | 约 8.88 秒 |
| WITCH_SPELL | 戴帽、拿扫帚、扫动闪星、收回 | 16 | 约 8.88 秒 |
| BLACK_CAT | 放板、玩毛线、抚摸猫、拿回场记板 | 15 | 约 8.04 秒 |

菜单在三端均为「动作 → 节日」。非节日原版 258 张 PNG/GIF 未改动。

## 可复现导出

原始透明网格、每格裁切框、相机原点、地面、时长和源图 SHA-256 位于 `assets/comi-v2/actions/halloween-source/`。不按每帧人物包围盒缩放；头部和道具运动保留在标注的坐标系里。原始生成图网格并非严格等分，因此每格使用显式裁切框。

```sh
python tools/build_halloween_actions.py \
  --config assets/comi-v2/actions/halloween-source/build.json \
  --out pet-work/halloween-rebuild
```

构建工具只写候选目录，包括 `sheets/` 中与现有导出器兼容的规范化源条、运行 PNG/GIF、深浅预览和 QA。生成的 `review.approved` 永远是 false。现有发布源条上的验收记录是维护者对具体源图哈希的记录，不从重建候选自动继承。

发布源条已经存放在 `assets/comi-v2/actions/*-sheet.png/json`。正常更新默认帧和演示：

```sh
python tools/export_comi_v2.py
python tools/make_halloween_previews.py
python -m unittest discover -s tests
node adapters/dsh/web-test.mjs
zsh tools/build_macos.sh
```

## 检查与限制

- 全部运行帧为 200×200；每组共用缩放，默认首帧人物高度接近原版约 137px，不能按包括帽子/猫/糖桶的外框重新放大。
- 同一中性姿势用于首尾，黑猫中重复毛线球的生成帧不参与时间轴。
- 已查看所有姿势的深浅底 200px 对比；自动检查覆盖源哈希、缺帧、透明、外框裁切、循环端点与导出复现。大幅弯腰、穿脱布料等相邻姿势仍会有较大的像素差，QA 中如实保留。
- 这些是离散姿势动画，局部切换不等于视频插帧。不得用比例扭曲或双曝光掩盖人体/道具缺帧。
- Mac 原生构建与自检、DSH 隔离菜单/点播测试分别记录；Windows 的真实桌面透明与交互仍需 Windows 实机验收。
- DSH 会缓存帧并在插件启动时读取时间轴；更新后重启 DSH 并刷新页面。Windows EXE 需要重新打包才包含新素材。

如需比对旧版，Git 提交 `73753e8` 保留了 Muse 最初的万圣节源图与运行帧，可用于研究和回退。
