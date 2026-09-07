# desktop-pet · Iven Pet 3D 🐾

3D 手办版桌面宠——把 Q 版场记板少女（豆包生成的 3D 三视图 + 表情动作 Sheet）做成 Shimeji 式 Windows 桌宠。

**想给任意 IP 角色做同款桌宠？看 [docs/SOP-IP角色桌宠化.md](docs/SOP-IP角色桌宠化.md)**——从设定图生成、AI 抠图、动作帧合成、三重自检到 PyInstaller 打包的完整标准作业流程（含踩坑速查表）。

**运行时零第三方依赖**——纯 Python 标准库 tkinter。素材帧由 `tools/make_frames3d.py` 预生成（仅构建期需要 Pillow/numpy/scipy）。

## 功能

- **动作库（豆包 Sheet 切片）**：待机呼吸×3 帧循环 / 普通走路（真迈步）/ 小短腿快走（菜单触发）/ 点击弹跳 / 双击开心反应 / 害羞反应 / 打板 🎬 / 转一圈 🔄（伪 3D 360°）/ 睡觉 / 抓取挣扎 / 重力下落与落地压扁
- **窗口即平台（Shimeji 式）**：屏幕底部 + 所有可见窗口的顶边都是路——掉落时踩到窗口就落地，沿窗口顶边行走，走到边缘多半掉头、偶尔走空掉下去；窗口关闭或移走，她也会跟着掉下来
- **开场演出**：从天上掉下来 → 落地弹压 → 挥手「我上线啦！」
- 右键菜单、左键拖拽到任意位置、随机台词气泡

## 使用

```bash
python pet.py
```

前提：Windows（透明色特性）+ Python 3.8+（tkinter 随装随有）。

## 重新生成素材帧（可选，仓库已带成品帧）

```bash
python tools/make_frames3d.py           # 抠图+切片，产出 assets/cut/preview.png 供人工检查
python tools/make_frames3d.py --frames  # 合成 frames3d/ 全套动作帧（27 帧）
python tools/smoke.py                   # 状态机冒烟测试，自动触发各状态并截图
```

素材源在 `assets/src/`（豆包 AI 生成）：`views_clean.png` 正/侧/背三视图、`actions.png` 六姿势表情Sheet、`views_blueprint.png` 标注版留档。

抠图原理：棚拍背景是青蓝渐变（实测 G-R ≥ +14），角色全身 G-R ≤ 0——用「G-R/B-G 颜色闸门 + 相邻像素局部梯度洪泛」双条件从四边扩散，渐变背景与软阴影自动吃掉，角色头发泛光处也不渗漏。

## License

MIT
