# Iven Pet 🐾 · 3D Chibi Desktop Pet

**Default artwork updated on 2026-10-13:** Iven v2 preserves the approved original 3D fleece-toy identity, with consistent proportions, cleaned chroma edges and full per-frame timing. Built-in and Studio assets share the same export. See [migration, rebuild and rollback notes](docs/IVEN_V2_MIGRATION.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-blue)](#)
[![Runtime](https://img.shields.io/badge/runtime-zero%20dependency-green)](#)

A standalone macOS/Windows desktop pet built from **AI-generated 3D character sheets**.
She hops along your desktop and automatically performs expressive actions.
On Windows, she can also stand on application windows and fall when they close.

English | [简体中文](README.zh-CN.md)

> Part of the **IvenKooLab** IP lab series. Want to turn *your* character into a
> desktop pet? Follow [docs/SOP-IP角色桌宠化.md](docs/SOP-IP角色桌宠化.md) (Chinese, with checklist).


## Animated previews

| Idle & look around | Wave, bounce & clapperboard | Action sequence |
| :---: | :---: | :---: |
| ![Idle and look around](docs/previews/idle-look.gif) | ![Reactions](docs/previews/reactions.gif) | ![Action sequence](docs/previews/action-cycle.gif) |

These GIFs use shipped PNG frames and their timing, on a preview backdrop; they are not desktop recordings. The sequence demonstrates waiting, working, reviewing and sadness between idle clips. Runtime order is randomized.

**Automatic playback is on by default.** A shuffled action pool plays each action once per cycle, with 3–6 seconds of idle between actions. Pause it from the right-click menu. Manual sleep stays asleep until a click wakes her; dragging suspends scheduling. A pinned Mac pet continues in-place actions without roaming. All nine source animations and sixteen gaze directions retain the approved Iven v2 proportions.

Animation-chain and preview ideas are inspired by [dsh-pet](https://github.com/PC2005-cloud/dsh-pet); character artwork remains this project's own Iven v2.

Rebuild previews: `python tools/make_readme_previews.py` (Pillow is needed only for generation).

## Features

- **Consistent original 3D fleece artwork** — eight-pose hopping movement,
  shared scale and per-frame timing, with a front-facing turn-around pause
- **~60 fps rendering** — fixed 50 ms logic steps + wall-clock animation phase
  and sub-pixel position interpolation (no more 20 fps stepping)
- **Windows: app windows are platforms** — she walks on top of your app windows,
  turns at edges (or falls off), and drops when you close the window
- Idle blinking · grab reaction · gravity fall · landing · closed-eye sleep
- Interactions: click = bounce, double-click = happy, right-click menu
  (clapperboard action / sixteen-direction look-around / faster hopping / shy / sleep)
- **Zero third-party dependencies at runtime** — native AppKit on Mac; Python standard library (tkinter) on Windows

## Quick Start

**Option A — ready-to-run**: grab `IvenPet.exe` (≈11 MB) from
[Releases](https://github.com/IvenKooLab/desktop-pet/releases), drop it on your desktop, double-click.
Existing executables may still contain the older art; rebuild from source for Iven v2.

**Option B — from source**:

```bash
python pet.py        # Windows + Python 3.8+ (tkinter bundled), nothing else to install
```

On macOS, double-click `start-mac.command`. The first build requires Apple command-line tools
(`xcode-select --install`); the generated `build/IvenPet.app` runs without Python.
Native transparent windows use RGBA PNG on Mac and color-key GIF on Windows.
The app runs independently of Codex or ChatGPT, without an account or model API.
Desktop movement, gravity, dragging and menus work on both platforms; walking on
other applications' window edges currently remains Windows-only. Linux is not yet supported.

Right-click the pet for the menu; drag her anywhere; double-click her for a reaction.
Close her via right-click menu → 退出 (Exit).


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
