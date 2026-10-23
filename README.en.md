# Iven Pet 🐾

[简体中文](README.md) | English

[![Release](https://img.shields.io/github/v/release/IvenKooLab/desktop-pet)](https://github.com/IvenKooLab/desktop-pet/releases/latest)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-487dc5)
![Runtime](https://img.shields.io/badge/runtime-zero%20dependency%20·%20local%20only-398c79)

A tiny 3D plush companion for work and little breaks. With lavender-white hair, cyan headphones and a clapperboard, Iven hops around your desktop, waves, claps her board and looks around—then reacts when you click or drag her.

Runs independently — no Codex, account or model API required.

[Download the latest release](https://github.com/IvenKooLab/desktop-pet/releases/latest) · [Changelog](CHANGELOG.md)

## A glimpse of her day

| Blink & look around | Wave, bounce & clapperboard | Wait, work & review |
| :---: | :---: | :---: |
| ![Idle and look around](docs/previews/idle-look.gif) | ![Interactive actions](docs/previews/reactions.gif) | ![Everyday actions](docs/previews/action-cycle.gif) |

### Little breaks

A stretch, a sleepy nod, then a few turns of a Rubik's cube. All three join automatic playback and can be selected from the right-click menu.

![Stretching, dozing and playing with a Rubik's cube](docs/previews/little-breaks.gif)

## Quick start

**Download a packaged build (recommended):** grab the zip for your platform from the [releases page](https://github.com/IvenKooLab/desktop-pet/releases/latest) and unpack —

- **macOS 13+:** open `IvenPet.app`. The Mac build is ad-hoc signed and not notarized; if macOS says it cannot verify the developer, right-click the app and choose Open, or run `xattr -d com.apple.quarantine IvenPet.app` first.
- **Windows:** run `IvenPet.exe`. No Python installation needed.

**Run from source** (for the latest actions):

```bash
# macOS: double-click start-mac.command, or
zsh tools/build_macos.sh   # first build needs Apple's command-line tools (xcode-select --install)
open build/IvenPet.app

# Windows: Python 3.8+ (tkinter included)
python pet.py
```

## What she does

- **Desktop roaming:** eight-frame hopping and faster movement; on Windows she also walks along the taskbar and visible app-window tops, turns or falls at edges, and drops when a supporting window closes or moves.
- **Entrance and chatter:** arrives with a fall, a landing and a wave; random speech bubbles on Windows.
- **Expressions and actions:** six-frame blinking idle, waving, five-frame bouncing, happiness, shyness, clapperboard, sixteen gaze directions, closed-eye sleep, waiting, working, reviewing, sadness — plus stretching, dozing and playing with a Rubik's cube; newly added sleepy blinking, feeling down, waving in celebration and looking around (all choreographed from approved frames, no new pixels). Want brand-new actions? See the [asset recipe](docs/ASSET_RECIPE.md).
- **Automatic performances:** longer complete animation segments with short rests, with the four new sequences lasting about 5–8 seconds at 75% playback speed. Pause or choose an action from the right-click menu.
- **Work companion themes:** thinking hard, getting impatient, low token budget and relief. These sequences reuse approved original frames, preserving the character and palette. Work alternates with thinking; approval waits longer than 30 seconds use the impatient theme, and explicit completion triggers relief. Low token budget is a manual performance, not a detected account balance.
- **Mouse interactions:** click to bounce, double-click for a happy reaction, drag for a grab reaction, then release to fall and land.
- **Fling physics:** flick the pet and she flies on a parabola — bouncing off screen edges and losing energy on each ground bounce until settling; a gentle release just drops in place. The Mac build adds a squash animation on impact, with identical physics semantics on both platforms.
- **Smooth and transparent:** approximately 60fps rendering, consistent proportions and per-frame timing, with native transparent windows on Mac.
- **Position memory & system notifications:** the pet returns to where you left her after a restart (`~/.iven-pet/config.json`); task completed, failed and approval-needed events can raise native notifications — by default only while the pet is hidden inside DSH, with always/off options.
- **Scriptable:** a local file control API ([docs/API.md](docs/API.md)) lets other plugins or the command line make her speak, play an action or read live state: `python tools/iven_cli.py say "take a break"`. Zero network, zero ports.

## Two display modes

- **Desktop:** the native macOS / Windows pet runs independently of any coding agent.
- **Inside DSH:** install the [DSH adapter](adapters/dsh/README.md), then use the Iven entry in DSH to bring the pet into its interface, with dragging, action selection and status bubbles. The desktop app’s Display mode menu can also request the switch.

Both views coordinate to avoid showing two copies. The pet hides only after the DSH web page claims the display; if nothing claims it within about 6 seconds, the desktop pet stays and a hint appears, and if the DSH page closes or disconnects later, desktop display returns within about 30 seconds. Reload DSH when first enabling the frontend plugin. Embedded mode currently targets DSH only; other agents continue to drive the independent desktop pet through their adapters.

## Company while you work

Iven runs as an independent desktop pet. Optional adapters let her follow a local coding agent: a status card stays visible while it works, approval requests remain visible, and turn endings or failures receive a reaction. With summaries enabled, the card can also show task labels or reply summaries provided by the adapter. Available text varies by source; this is not full conversation access for every agent.

![Iven following ZCode at work: the status bubble shows the source, task label and current step, with a "Following · ZCode" badge](docs/images/bridge-zcode-working.png)

### Choose a source

Right-click → **跟踪 Harness** (Track Harness):

- **Automatic · all connected sources:** receive events from every configured adapter, prioritizing approval requests and then the most recently active session.
- **One source:** show only that source’s status and notices, without interruptions from other agents.
- **Per-source state:** working, approval needed, idle, or no events received. Opening an agent app or selecting its name does not establish a connection; install its adapter first.

A badge identifies the source currently followed. In automatic mode, `+1` indicates another active source. A selected source without events is labeled accordingly, such as “Codex · No events”. One pet receives multiple sources, while the card displays one session at a time. Menu and label wording follows the app’s available language support.

### Integration availability

| Source | Connection | Current scope |
| :--- | :--- | :--- |
| [ZCode](adapters/zcode/README.md) | Hooks | Work, tool activity, approvals and turn endings; optional task labels and reply summaries |
| [DSH / DeepSeek Harness](adapters/dsh/README.md) | Host plugin | Session and tool events, approvals and goal results; optional task labels |
| [Claude Code](adapters/claude-code/README.md) | Hooks | Adapter and event replay tests provided; validation in the actual client is still needed |
| [Cursor](adapters/cursor/README.md) | Hooks | Adapter and event replay tests provided; validation in the actual client is still needed |
| [OpenCode](adapters/opencode/README.md) | Server event stream | State adapter and mock server tests provided; validation in the actual client is still needed |
| [Codex](adapters/codex/README.md) | Separate App Server client | **Cannot currently follow your active Codex desktop session.** Verification covers a separate client’s handshake, thread listing and simulated events; this is not a ready-to-use desktop integration |

Install each adapter separately using the links above. See the [capability matrix](adapters/README.md) for details. Iven is separate from the built-in pets in ChatGPT / Codex and runs without either app.

### Local communication and optional text

Adapters send events through a local file inbox — no network, no extra model calls. State and tool names are sent by default. Task labels and reply summaries require a separate opt-in and are truncated; only when enabled is that text written to local event files and shown on your desktop. The pet does not approve permissions, send tasks or control the agent. Closing either side does not prevent the other from working normally.

See [docs/BRIDGE.md](docs/BRIDGE.md) for the protocol and developer notes.

### Talk to Iven

Right-click → **“Talk to Iven…”** and type a message; Iven answers with the model
configured in your DSH — a speech bubble, sometimes with a matching expression
animation, and the last 8 turns are remembered locally (delete
`~/.iven-pet/chat/memory.json` to reset). DSH must be running with its adapter
installed; when it is unreachable she says so instead of pretending to chat.
Chat also stays on your machine, and the pet itself still needs no model API.

## Interactions

| Input | Response |
| :--- | :--- |
| Click | Bounce; wake up when sleeping |
| Double-click | Happy reaction |
| Drag | Move the pet; release to fall naturally |
| Fling | Parabolic flight with screen-edge and ground bounces |
| Right-click | Talk to Iven, pick actions, toggle autoplay, system notifications, choose a tracked source, sleep or quit |
| Control + click (Mac) | Open the menu |
| Pin in place (Mac) | Stop roaming while in-place actions continue |

The right-click menu also switches the interface language (system default / 简体中文 / English, applied immediately and remembered) and opens the GitHub repository.

Manual sleep lasts until you click to wake her. Mac roaming follows the desktop floor; walking on application window tops and random dialogue bubbles currently require Windows. Mac supports coding-agent status bubbles. Linux is not supported yet.

## Build a packaged release

The archives published on the releases page:

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
