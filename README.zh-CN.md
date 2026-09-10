# desktop-pet · Iven Pet 3D 🐾

3D 手办版桌面宠——把 Q 版场记板少女（豆包生成的 3D 三视图 + 表情动作 Sheet）做成 Shimeji 式 Windows 桌宠。

**想给任意 IP 角色做同款桌宠？看 [docs/SOP-IP角色桌宠化.md](docs/SOP-IP角色桌宠化.md)**——从设定图生成、AI 抠图、动作帧合成、三重自检到 PyInstaller 打包的完整标准作业流程（含踩坑速查表）。

**运行时零第三方依赖**——纯 Python 标准库 tkinter。素材帧由 `tools/make_frames3d.py` 预生成（仅构建期需要 Pillow/numpy/scipy）。

## 功能

- **动作库（豆包 Sheet 切片）**：待机呼吸×3 帧循环 / 普通走路（真迈步）/ 小短腿快走（菜单触发）/ 点击弹跳 / 双击开心反应 / 害羞反应 / 打板 🎬 / 转一圈 🔄（伪 3D 360°）/ 睡觉 / 抓取挣扎 / 重力下落与落地压扁
- **窗口即平台（Shimeji 式）**：屏幕底部 + 任务栏顶边 + 所有可见窗口的顶边都是路——掉落时踩到就落地，沿边缘行走，走到边缘多半掉头、偶尔走空掉下去；窗口关闭或移走，她也会跟着掉下来
- **开场演出**：从天上掉下来 → 落地弹压 → 挥手「我上线啦！」
- 右键菜单、左键拖拽到任意位置、随机台词气泡

## 使用

```bash
python pet.py
```

前提：Windows（透明色特性）+ Python 3.8+（tkinter 随装随有）。

## MVP：只传一张三视图

不想凑齐全套 Sheet？一张三视图（正/侧/背，从左到右）即可出**简化版**桌宠（呼吸压扁 + 程序剪腿步态 + 转体，21 帧）：

```bash
python tools/make_pet_from_views.py --src 路径/三视图.png --out frames3d_mvp
set PET_FRAMES_DIR=frames3d_mvp
python pet.py
```

## 重新生成完整素材帧（可选，仓库已带成品帧）

```bash
python tools/make_frames3d.py           # 抠图+切片，产出 assets/cut/preview.png 供人工检查
python tools/make_frames3d.py --frames  # 合成 frames3d/ 全套动作帧（37 帧）
python tools/qa_frames.py               # 数值自检：碎片/孔洞/尺寸一致性
python tools/qa_diff.py                 # 像素回归：成品帧 vs 源切图逐帧对比
python tools/smoke.py                   # 状态机冒烟测试，自动触发各状态并截图
```

素材源在 `assets/src/`（豆包 AI 生成）：`views_clean.png` 正/侧/背三视图、`walk_cycle.png` 走路循环、`fastwalk.png` 小短腿快走、`idle_breathe.png` 待机呼吸、`actions_lib.png` 八宫格动作库、`wr_*_single.png` 右向单人物原图、`views_blueprint.png` 标注版留档。

抠图管线：新版素材走 **rembg AI 抠图**（滞后阈值 + 深色部件回收 + fill_holes 三层保险，见 `tools/make_frames3d.py` 的 `rembg_fg`）；老版青蓝渐变底用「G-R/B-G 颜色闸门 + 相邻像素局部梯度洪泛」双条件（`flood_bg`）。

## License

MIT
