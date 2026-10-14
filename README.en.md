# Iven Pet 🐾

[简体中文](README.md) | English

A tiny 3D plush companion for work and little breaks. With lavender-white hair, cyan headphones and a clapperboard, Iven hops around your desktop, waves, claps her board and looks around—then reacts when you click or drag her.

Runs independently on **macOS and Windows**. No Codex, account or model API required.

## A glimpse of her day

| Blink & look around | Wave, bounce & clapperboard | Wait, work & review |
| :---: | :---: | :---: |
| ![Idle and look around](docs/previews/idle-look.gif) | ![Interactive actions](docs/previews/reactions.gif) | ![Everyday actions](docs/previews/action-cycle.gif) |

### Little breaks

A stretch, a sleepy nod, then a few turns of a Rubik's cube. All three join automatic playback and can be selected from the right-click menu.

![Stretching, dozing and playing with a Rubik's cube](docs/previews/little-breaks.gif)

## What she does

- **Desktop roaming:** eight-frame hopping and faster movement, with a brief front-facing pause when turning on Windows.
- **Expressions and actions:** six-frame blinking idle, waving, five-frame bouncing, happiness, shyness, clapperboard, waiting, working, reviewing, sadness, sixteen gaze directions, closed-eye sleep, stretching, dozing and playing with a Rubik's cube.
- **Automatic performances:** shuffled action cycles with short rests between actions. Pause playback or pick an action from the right-click menu.
- **Mouse interactions:** click to bounce, double-click for a happy reaction, drag for a grab reaction, then release to fall and land.
- **Smooth and transparent:** approximately 60fps rendering, consistent proportions and per-frame timing, with native transparent windows on Mac.
- **Windows as platforms:** walks along the desktop, taskbar and visible app window tops; turns or falls at edges and drops when a supporting window closes or moves. Arrives with a fall, landing and wave, and occasionally speaks through a bubble.
- **Pin on Mac:** keep her in a chosen spot while in-place animations continue.

## Quick start

### macOS

Double-click **`start-mac.command`** in the repository. The first run builds the app and requires Apple's command-line tools:

```bash
xcode-select --install
```

Afterwards, open `build/IvenPet.app` directly. Python is not required.

### Windows

Install Python 3.8+ with tkinter, then run from the project directory:

```bash
python pet.py
```

Packaged versions are also available on the [releases page](https://github.com/IvenKooLab/desktop-pet/releases). Run or rebuild the current source for the latest actions.

## Coding-agent bridge (optional)

The pet can sense what your local coding agent is doing: she "works" beside you while
the agent runs tools, reminds you when a permission is waiting, and reacts to turn
ends, failures and completed tasks (the native Mac app shows small bubble notices).
Communication is a **local file inbox only — no network — and state-only by default**:
no prompts, replies or tool contents ever leave the host. Either side can be closed
without affecting the other.

Currently supported: **ZCode** and **DSH (DeepSeek Harness)** — see
[`adapters/zcode/`](adapters/zcode/README.md) and
[`adapters/dsh/`](adapters/dsh/README.md) for installation. No pet-side setup is
needed; toggle "宿主桥接 / Host bridge" in the right-click menu anytime. Protocol
and implementation details live in [`docs/BRIDGE.md`](docs/BRIDGE.md).

## Interactions

| Input | Response |
| :--- | :--- |
| Click | Bounce; wake up when sleeping |
| Double-click | Happy reaction |
| Drag | Move the pet; release to fall naturally |
| Right-click | Pick actions, toggle autoplay, sleep or quit |
| Control + click (Mac) | Open the menu |
| Pin in place (Mac) | Stop roaming while in-place actions continue |

Manual sleep lasts until you click to wake her. Mac roaming follows the desktop floor; walking on application window tops and speech bubbles currently require Windows. Linux is not supported yet.

## Build from source

```bash
# Windows: install PyInstaller first
pip install pyinstaller
tools\build_exe.bat

# macOS
zsh tools/build_macos.sh
```

No third-party Python packages are needed at runtime. See the [maintenance guide](docs/IVEN_V2_MIGRATION.md) for asset export, preview generation and validation.

## Credits

Thanks to [dsh-pet](https://github.com/PC2005-cloud/dsh-pet) for animation-chain and everyday-action inspiration.

## License

[MIT](LICENSE) · AI-generated Iven character artwork belongs to IvenKooLab.
