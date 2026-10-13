# Iven Pet 🐾 · 3D Chibi Desktop Pet

**Default artwork updated on 2026-10-13:** Iven v2 preserves the approved original 3D fleece-toy identity, with consistent proportions, cleaned chroma edges and full per-frame timing. Built-in and Studio assets share the same export. See [migration, rebuild and rollback notes](docs/IVEN_V2_MIGRATION.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](#)
[![Runtime](https://img.shields.io/badge/runtime-zero%20dependency-green)](#)

A Shimeji-style Windows desktop pet built from **AI-generated 3D character sheets**.
She walks along your taskbar, stands on top of your application windows,
climbs down when you close them — and does a little clapperboard cheer when you double-click her.

English | [简体中文](README.zh-CN.md)

> Part of the **IvenKooLab** IP lab series. Want to turn *your* character into a
> desktop pet? Follow [docs/SOP-IP角色桌宠化.md](docs/SOP-IP角色桌宠化.md) (Chinese, with checklist).

## Features

- **Consistent original 3D fleece artwork** — eight-pose hopping movement,
  shared scale and per-frame timing, with a front-facing turn-around pause
- **~60 fps rendering** — fixed 50 ms logic steps + wall-clock animation phase
  and sub-pixel position interpolation (no more 20 fps stepping)
- **Windows are platforms** — she walks on top of your app windows,
  turns at edges (or falls off), and drops when you close the window
- Idle blinking · grab reaction · gravity fall · landing · closed-eye sleep
- Interactions: click = bounce, double-click = happy, right-click menu
  (clapperboard action / sixteen-direction look-around / faster hopping / shy / sleep)
- **Zero third-party dependencies at runtime** — pure Python standard library (tkinter)

## Quick Start

**Option A — ready-to-run**: grab `IvenPet.exe` (≈11 MB) from
[Releases](https://github.com/IvenKooLab/desktop-pet/releases), drop it on your desktop, double-click.
Existing executables may still contain the older art; rebuild from source for Iven v2.

**Option B — from source**:

```bash
python pet.py        # Windows + Python 3.8+ (tkinter bundled), nothing else to install
```

Right-click the pet for the menu; drag her anywhere; double-click her for a reaction.
Close her via right-click menu → 退出 (Exit).


![Iven Pet Studio](docs/images/studio.png)


![Iven Pet Studio · 桌宠制作器](docs/images/studio.png)

## Build Your Own IP Pet

The whole pipeline is documented as a step-by-step SOP:
generate character sheets with your favorite AI image tool → AI matting →
animation frame synthesis → automated QA → PyInstaller packaging.

See [docs/SOP-IP角色桌宠化.md](docs/SOP-IP角色桌宠化.md) and the
[new-IP checklist](docs/SOP-IP角色桌宠化.md#新-ip-接入清单checklist) inside.

```bash
tools\build_exe.bat   # rebuilds dist\IvenPet.exe (needs pyinstaller)
```

## Repository Layout

```
pet.py                  # runtime: state machine + window-as-platform + single instance
frames3d/               # default GIF frames, compatibility aliases and animation.json
animation_assets.py    # optional per-frame timing, compatible with legacy characters
tools/export_iven_v2.py # approved atlas → default and Studio assets
tools/make_frames3d.py  # legacy pipeline (isolated output only)
tools/qa_frames.py      # numeric QA: fragments / holes / size consistency
tools/qa_diff.py        # pixel regression: final frames vs source cuts
tools/smoke.py          # state-machine smoke test with screenshots
docs/                   # SOP + asset pipeline documentation
assets/iven-v2/          # approved default atlas and validation evidence
assets/src/             # original character identity references
assets/legacy-pre-iven-v2/ # archived old frames for explicit rollback
```

## License

[MIT](LICENSE) · Character art generated with AI, copyright IvenKooLab
