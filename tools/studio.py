"""Iven Pet Studio v0.1 · 桌宠制作器（配置页 + 三视图生成向导）。

功能：
    - 角色管理：characters/<name>/{frames3d/*.gif, meta.json}，可切换当前角色
    - 制作向导：选三视图 → 调 make_pet_from_views 生成 29 帧 → 预览 → 保存
    - 台词库编辑：每行一条，写入角色 meta.json（pet.py 启动时加载覆盖默认）

运行（需要构建期依赖 PIL/numpy/scipy/rembg，即 ComfyUI 的 Python）：
    D:/tools/ComfyUI-aki-v3/python/pythonw.exe tools/studio.py

生成在子进程执行（同解释器），进度实时显示；无依赖时向导禁用但配置可用。
"""
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
CH = ROOT / "characters"
SETTINGS = ROOT / "pet_settings.json"
PY = sys.executable          # 生成子进程用同一解释器（保证依赖可用）

GEN_DEPS = True
try:
    import numpy  # noqa: F401
    import PIL  # noqa: F401
except ImportError:
    GEN_DEPS = False


def load_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(conf):
    SETTINGS.write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")


def list_characters():
    if not CH.is_dir():
        return []
    return sorted(p.name for p in CH.iterdir()
                  if p.is_dir() and (p / "frames3d" / "idle_0.gif").exists())


class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Iven Pet Studio · 桌宠制作器")
        self.geometry("880x560")
        self.minsize(760, 480)
        self.gen_proc = None
        self._build()

    # ---------- 界面 ----------
    def _build(self):
        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # 左：角色列表
        left = ttk.Frame(main)
        main.add(left, weight=1)
        ttk.Label(left, text="角色").pack(anchor="w")
        self.char_list = tk.Listbox(left, width=24, exportselection=False)
        self.char_list.pack(fill="both", expand=True, pady=(4, 4))
        self.char_list.bind("<<ListboxSelect>>", lambda e: self._on_select())
        ttk.Button(left, text="启用选中角色", command=self._use_char).pack(fill="x")

        # 右：三页
        right = ttk.Frame(main)
        main.add(right, weight=3)
        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)
        nb.add(self._page_wizard(nb), text=" 制作向导 ")
        nb.add(self._page_lines(nb), text=" 台词库 ")
        nb.add(self._page_about(nb), text=" 关于 ")

        self.status = ttk.Label(self, text="就绪", anchor="w", relief="sunken")
        self.status.pack(fill="x", side="bottom")
        self._refresh()

    def _page_wizard(self, parent):
        f = ttk.Frame(parent, padding=12)
        ttk.Label(f, text="① 选择三视图（正 / 侧 / 背，从左到右，任意背景）").pack(anchor="w")
        row = ttk.Frame(f); row.pack(fill="x", pady=4)
        self.src_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.src_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="浏览…", command=self._pick_src).pack(side="left", padx=(6, 0))
        ttk.Label(f, text="② 角色名").pack(anchor="w", pady=(8, 0))
        self.name_var = tk.StringVar(value="my-pet")
        ttk.Entry(f, textvariable=self.name_var).pack(fill="x", pady=4)
        self.gen_btn = ttk.Button(f, text="③ 生成桌宠（约 1~2 分钟）", command=self._start_gen,
                                  state="normal" if GEN_DEPS else "disabled")
        self.gen_btn.pack(fill="x", pady=(10, 4))
        if not GEN_DEPS:
            ttk.Label(f, text="当前解释器缺 PIL/numpy（生成需构建期依赖），\n"
                              "请用 ComfyUI 的 Python 启动 Studio。",
                      foreground="#a33").pack(anchor="w")
        self.log = tk.Text(f, height=8, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(6, 0))
        # 预览区
        self.preview = ttk.Label(f, text="（生成后在此预览）", anchor="center")
        self.preview.pack(fill="both", expand=True, pady=(6, 0))
        ttk.Button(f, text="启用该角色（写设置并重启桌宠生效）",
                   command=self._use_new).pack(fill="x", pady=(6, 0))
        return f

    def _page_lines(self, parent):
        f = ttk.Frame(parent, padding=12)
        ttk.Label(f, text="当前角色台词库（每行一条，保存后重启桌宠生效）").pack(anchor="w")
        self.lines_box = tk.Text(f, font=("Microsoft YaHei UI", 10))
        self.lines_box.pack(fill="both", expand=True, pady=(6, 4))
        ttk.Button(f, text="保存台词", command=self._save_lines).pack(anchor="e")
        return f

    def _page_about(self, parent):
        f = ttk.Frame(parent, padding=14)
        txt = ("Iven Pet Studio v0.1\n\n"
               "制作流程 = 确定性管线：粗定位 → 逐人 rembg 抠图 → 朝向检测 →\n"
               "程序化 8 相位步态 / 呼吸 / 转体，共 29 帧。\n\n"
               "完整 SOP 见 docs/SOP-IP角色桌宠化.md（含踩坑速查表）。\n"
               "v0.2 计划：LLM 增强（表情 Sheet 生成 / 台词生成 / 智能调参）。")
        ttk.Label(f, text=txt, justify="left").pack(anchor="nw")
        return f

    # ---------- 逻辑 ----------
    def _refresh(self):
        self.char_list.delete(0, "end")
        for c in list_characters():
            self.char_list.insert("end", c)
        conf = load_settings()
        cur = conf.get("character", "（内置）")
        self.status.config(text=f"当前角色：{cur}   |   Studio v0.1")

    def _on_select(self):
        sel = self.char_list.curselection()
        if not sel:
            return
        name = self.char_list.get(sel[0])
        meta_p = CH / name / "meta.json"
        lines = []
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            lines = meta.get("lines", [])
        except Exception:
            pass
        self.lines_box.delete("1.0", "end")
        self.lines_box.insert("1.0", "\n".join(lines))

    def _pick_src(self):
        p = filedialog.askopenfilename(title="选择三视图",
                                       filetypes=[("图片", "*.png *.jpg *.jpeg *.webp")])
        if p:
            self.src_var.set(p)

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.update_idletasks()

    def _start_gen(self):
        src = self.src_var.get().strip()
        name = self.name_var.get().strip()
        if not src or not Path(src).exists():
            messagebox.showwarning("缺素材", "请先选择三视图文件")
            return
        if not name or any(c in name for c in "\\/:*?\"<>|"):
            messagebox.showwarning("名字无效", "角色名不能为空或包含 \\ / : * ? \" < > |")
            return
        out = CH / name / "frames3d"
        self.gen_btn.config(state="disabled")
        self._log(f"→ 生成角色「{name}」…（首次加载模型约需 1 分钟）")
        cmd = [PY, str(ROOT / "tools" / "make_pet_from_views.py"),
               "--src", src, "--out", str(out)]
        self.gen_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace",
                                         cwd=str(ROOT))
        threading.Thread(target=self._pump, args=(name, out), daemon=True).start()

    def _pump(self, name, out: Path):
        for line in self.gen_proc.stdout:
            if any(k in line for k in ("onnx", "CUDA", "RuntimeWarning", "provider")):
                continue
            self.after(0, self._log, line.rstrip())
        self.gen_proc.wait()
        ok = (out / "idle_0.gif").exists()
        def done():
            self.gen_btn.config(state="normal")
            if ok:
                meta = {"name": name, "created": str(out.stat().st_mtime), "lines": []}
                (CH / name / "meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                self._log(f"✓ 完成：{len(list(out.glob('*.gif')))} 帧 → {out}")
                self._show_preview(out)
                self._refresh()
            else:
                self._log("✗ 生成失败，请检查素材是否为清晰的三视图")
        self.after(0, done)

    def _show_preview(self, out: Path):
        try:
            self._photo = tk.PhotoImage(file=str(out / "idle_0.gif"))
            self._photo = self._photo.subsample(2)      # 200→100
            self.preview.config(image=self._photo, text="")
        except tk.TclError:
            self.preview.config(text="（预览失败，但帧已生成）")

    def _use_new(self):
        name = self.name_var.get().strip()
        if (CH / name / "frames3d" / "idle_0.gif").exists():
            self._apply_char(name)
        else:
            messagebox.showinfo("先生成", "请先完成生成")

    def _use_char(self):
        sel = self.char_list.curselection()
        if sel:
            self._apply_char(self.char_list.get(sel[0]))

    def _apply_char(self, name):
        conf = load_settings()
        conf["character"] = name
        save_settings(conf)
        self._refresh()
        messagebox.showinfo("已启用", f"角色「{name}」已设为当前角色。\n"
                                      f"右键退出桌宠后重新启动即换装。")

    def _save_lines(self):
        sel = self.char_list.curselection()
        if not sel:
            messagebox.showinfo("先选角色", "在左侧选择要编辑台词的角色")
            return
        name = self.char_list.get(sel[0])
        meta_p = CH / name / "meta.json"
        meta = {}
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except Exception:
            pass
        meta["lines"] = [l.strip() for l in
                         self.lines_box.get("1.0", "end").splitlines() if l.strip()]
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status.config(text=f"台词已保存到 {name}（重启桌宠生效）")


if __name__ == "__main__":
    Studio().mainloop()
