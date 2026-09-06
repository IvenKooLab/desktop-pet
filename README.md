# desktop-pet · Iven Pet 🐾

我的 GitHub 头像（ComfyAgent Q 版形象）做成的 Windows 桌面宠。

**运行时零第三方依赖**——纯 Python 标准库 tkinter。素材帧由 Pillow 一次性预生成（仅构建期需要）。

## 功能

- 桌面悬浮，呼吸式上下浮动
- 左键拖拽到任意位置
- 单击冒台词气泡（程序员人设台词库，随机）
- 双击跳跃动画
- 右键菜单：说句话 / 跳一下 / 置顶开关 / 退出

## 使用

```bash
python pet.py
```

前提：Windows（透明色特性）+ Python 3.8+（tkinter 随装随有）。

## 生成素材帧（可选，仓库已带成品帧）

```bash
pip install pillow
python tools/make_frames.py assets/avatar_raw.png
```

## License

MIT
