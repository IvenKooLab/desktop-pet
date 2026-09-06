# desktop-pet · Iven Pet 3D 🐾

3D 手办版桌面宠——把 Q 版场记板少女（豆包生成的 3D 三视图 + 表情动作 Sheet）做成 Shimeji 式 Windows 桌宠。

**运行时零第三方依赖**——纯 Python 标准库 tkinter。素材帧由 `tools/make_frames3d.py` 预生成（仅构建期需要 Pillow/numpy/scipy）。

## 功能

- **六态状态机**：待机呼吸 / 底边走动（左右侧视自动切换）/ 抓取挣扎 / 重力下落 / 落地压扁 / 60 秒无交互睡着
- **开场演出**：从天上掉下来 → 落地弹压 → 挥手「我上线啦！」
- **右键菜单**：说句话 / 打个板 🎬 / 转一圈 🔄（伪 3D 360° 转体）/ 跑两步 / 睡一觉 / 退出
- 双击起跳、左键拖拽到任意位置、随机台词气泡

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
