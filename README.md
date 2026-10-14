# Iven Pet 🐾

简体中文 | [English](README.en.md)

一只陪你工作、偶尔摸鱼的 3D 绒质桌宠。紫白短发、青蓝耳机、随身场记板——Iven 会在桌面上小跳漫游，挥手、打板、观察四周，也会在你点击和拖动时作出反应。

支持 **macOS / Windows**，独立运行，无需 Codex、账号或模型 API。

## 看看她的日常

| 眨眼与四处看看 | 挥手、弹跳、打板 | 等待、工作、检查 |
| :---: | :---: | :---: |
| ![眨眼与观察](docs/previews/idle-look.gif) | ![互动动作](docs/previews/reactions.gif) | ![日常动作](docs/previews/action-cycle.gif) |

### 摸鱼时间

伸个懒腰、眯一会儿，再认真转几下魔方。三种小动作也会出现在自动轮播中，右键菜单可以单独点播。

![伸懒腰、打瞌睡和玩魔方](docs/previews/little-breaks.gif)

## 会做什么

- **桌面漫游**：八帧小跳移动、加速移动；Windows 掉头时有正面停顿。
- **表情与动作**：六帧眨眼待机、挥手、五帧弹跳、开心、害羞、打板、等待、工作、检查、失落、十六方向观察四周、闭眼睡觉，以及伸懒腰、打瞌睡和玩魔方。
- **自动表演**：默认自动轮播，动作之间稍作休息；每轮打乱顺序，右键可随时暂停或点播。
- **鼠标互动**：单击弹跳，双击开心，拖拽时有抓取反应，松手后重力下落并落地。
- **流畅透明**：约 60fps 渲染，统一角色比例和动作时间轴；Mac 使用原生透明窗口。
- **Windows 窗口即平台**：沿桌面、任务栏和可见窗口顶边行走，走到边缘会掉头或落下；窗口关闭或移走时随之下落。开场从天而降、落地、挥手，并有随机台词气泡。
- **Mac 固定位置**：可以留在你选的位置，继续播放原地动作。

## 快速开始

### macOS

双击仓库中的 **`start-mac.command`**。首次运行会构建应用，需要 Apple 命令行工具：

```bash
xcode-select --install
```

之后也可直接打开 `build/IvenPet.app`，无需 Python。

### Windows

安装 Python 3.8+（包含 tkinter），在项目目录运行：

```bash
python pet.py
```

[发布页](https://github.com/IvenKooLab/desktop-pet/releases)也提供已打包版本。体验最新动作请从当前源码运行或重新构建。

## 怎么互动

| 操作 | 效果 |
| :--- | :--- |
| 单击 | 弹跳；睡觉时唤醒 |
| 双击 | 开心反应 |
| 按住拖动 | 移动桌宠，松手后自然下落 |
| 右键 | 点播动作、切换自动轮播、睡觉、退出 |
| Control + 点击（Mac） | 打开菜单 |
| 固定在当前位置（Mac） | 停止漫游，保留原地动画 |

手动选择睡觉后会保持睡眠，点击即可唤醒。Mac 沿桌面底边漫游；其他应用窗口顶边行走和台词气泡目前仅 Windows 支持。Linux 暂未支持。

## 从源码构建

```bash
# Windows：先安装 PyInstaller
pip install pyinstaller
tools\build_exe.bat

# macOS
zsh tools/build_macos.sh
```

运行时无需第三方 Python 包。素材导出、GIF 生成和验证方法见[维护说明](docs/IVEN_V2_MIGRATION.md)。

## 致谢

感谢 [dsh-pet](https://github.com/PC2005-cloud/dsh-pet) 提供的动作编排和日常小动作灵感。

## License

[MIT](LICENSE) · Iven 角色素材由 AI 生成，归 IvenKooLab 所有。
