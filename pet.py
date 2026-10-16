"""Iven Pet · macOS/Windows 独立 3D 绒质桌宠（运行时纯标准库）。

素材由批准的 Iven v2 母版导出，原版 3D 绒质风格。Mac 使用透明 PNG，
Windows 使用色键 GIF；时间轴来自 animation.json，观察四周不等于全身转体。

状态机：GREET(落地打招呼) → IDLE(呼吸) → WALK(走动) / RUN(小短腿快走) →
        GRAB(挣扎) → FALL(重力下落) → LAND(压扁) → SLEEP(睡着)
        + CHEER(打板) / SPIN(转一圈) / BOUNCE(点击弹跳) / HAPPY(双击开心) / SHY(害羞)

主循环：逻辑固定 50ms 步长（tick 语义/状态机节奏不变）+ ~60fps 渲染层——
        动画相位取自墙钟（帧周期可为任意毫秒）、窗口位置在逻辑步间亚像素插值。

平台：屏幕底部 + 所有可见窗口的顶边（Shimeji 式）——掉落时踩到就落地，
     沿窗口顶边行走，窗口关闭/移走会跟着掉下来。

    python pet.py
"""
import os
import random
import socket
import sys
import time
import tkinter as tk
import webbrowser
from language_preferences import load_language, save_language
from animation_assets import load_clips, timed_frame
from animation_behaviors import load_behaviors, performance_ticks
from display_mode import read_display_mode, write_display_mode
from desktop_platform import configure_transparency, frame_path, clear_legacy_color_key
from host_bridge import HostBridge, default_dir
from bridge_display import status_card, following_badge

try:                    # Windows：枚举窗口顶边当平台
    import ctypes
    from ctypes import wintypes
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
except (ImportError, AttributeError):   # 非 Windows
    ctypes = None

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
def _load_profile():
    """Use the bundled Iven artwork; environment override supports maintenance rollback."""
    frames_dir = os.environ.get("PET_FRAMES_DIR") or os.path.join(BASE, "frames3d")
    language = load_language()
    return frames_dir, (_detect_lang() if language == "system" else language)


def _texts(lang):
    """5 语言 UI/台词表（zh 简中 / zh-Hant 繁中 / en / ko / ja）。"""
    if lang == "zh-Hant":
        return {
            "menu_speak": "說句話", "menu_clap": "打個板 🎬",
            "menu_spin": "轉一圈 🔄", "menu_run": "小短腿快走 🏃",
            "menu_shy": "害羞一下 😳", "menu_sleep": "睡一覺",
            "menu_exit": "退出",
            "lines": [
                "token 又免費了，快薅！", "今天的格子，點亮了嗎？",
                "Agent & RAG，學著呢。", "free tier 也要有夢想。",
                "README 已經是英文的了哦。", "我的場記板呢……",
                "三個倉庫，都在雙平台躺著。", "慢慢做，比較快。",
                "有 bug 去公眾號看我調試。", "我現在是 3D 手辦了哦。",
                "你的視窗，都是我的路。",
            ],
            "grab": ["哇！", "放手！", "別提我！"],
            "land": ["著陸成功。", "一點不疼。", "再來。"],
            "cheer": ["Action——！", "咔，一條過！"],
            "sleep": "Zzz……",
            "wake": "……吵醒我了。",
            "greet": "我上線啦！",
            "shy": "……討厭啦。",
            "dash": "衝呀——！",
            "spin": "轉起來～",
            "wow": ["哇！", "開心！", "耶！"],
        }
    if lang == "en":
        return {
            "menu_speak": "Say something", "menu_clap": "Clap board 🎬",
            "menu_spin": "Spin around 🔄", "menu_run": "Quick walk 🏃",
            "menu_shy": "Get shy 😳", "menu_sleep": "Sleep",
            "menu_exit": "Exit",
            "lines": [
                "Free tokens again — grab 'em!",
                "Did you light up today's square?",
                "Learning Agents & RAG.",
                "Free tier dreams matter too.",
                "My README is already in English.",
                "Where's my clapperboard…",
                "Three repos, napping on two platforms.",
                "Slow is smooth, smooth is fast.",
                "Bugs? Watch me debug on my channel.",
                "I'm a 3D figure now.",
                "Your windows are my streets.",
            ],
            "grab": ["Whoa!", "Let go!", "Hey, hands off!"],
            "land": ["Landed.", "Didn't hurt a bit.", "Again!"],
            "cheer": ["Action—!", "One take, perfect!"],
            "sleep": "Zzz…",
            "wake": "…Hey, I was sleeping.",
            "greet": "I'm online!",
            "shy": "…S-stop that.",
            "dash": "Here I go—!",
            "spin": "Spin spin~",
            "wow": ["Whoa!", "Yay!", "Whee!"],
        }
    if lang == "ko":
        return {
            "menu_speak": "말 걸기", "menu_clap": "클래퍼 🎬",
            "menu_spin": "빙글 돌기 🔄", "menu_run": "빠른 걸음 🏃",
            "menu_shy": "쑥스러움 😳", "menu_sleep": "자기",
            "menu_exit": "종료",
            "lines": [
                "토큰 또 무료래, 얻어먹자!", "오늘의 칸, 채웠어?",
                "Agent & RAG, 배우는 중.", "무료 티어에도 꿈이 있어.",
                "README는 이미 영어란 말이야.", "내 클래퍼 보드 어딨지…",
                "저장소 3개, 두 플랫폼에서 쉬는 중.", "천천히 하면 오히려 빨라.",
                "버그는 채널에서 디버깅하는 거 봐.", "이제 난 3D 피규어야.",
                "네 창문들이 전부 내 거야.",
            ],
            "grab": ["앗!", "놔!", "그만!"],
            "land": ["착륙 성공.", "하나도 안 아파.", "또 할래!"],
            "cheer": ["액션—!", "한 방에 OK!"],
            "sleep": "쿨쿨…",
            "wake": "…왜 깨우는 거야!",
            "greet": "켜졌다!",
            "shy": "…히힝, 그만해!",
            "dash": "달려—!",
            "spin": "빙글빙글~",
            "wow": ["와!", "신나!", "이야!"],
        }
    if lang == "ja":
        return {
            "menu_speak": "話しかける", "menu_clap": "カチンコ 🎬",
            "menu_spin": "ぐるっと回る 🔄", "menu_run": "ちょこ速歩き 🏃",
            "menu_shy": "照れちゃう 😳", "menu_sleep": "お昼寝",
            "menu_exit": "終了",
            "lines": [
                "トークンまた無料だって、捕まえよう！", "今日のマス、塗った？",
                "Agent & RAG、勉強中。", "無料枠にも夢があるの。",
                "README、もう英語だよ。", "私のクラッパーボードどこ…",
                "リポジトリ 3つ、デュアルで寝てる。", "ゆっくり丁寧が一番速い。",
                "バグはチャンネルでデバッグ見てね。", "今では 3D フィギュアだよ。",
                "あなたのウィンドウは私の道。",
            ],
            "grab": ["わっ！", "離して！", "やめてよ！"],
            "land": ["着地成功。", "全然痛くない。", "もう一回！"],
            "cheer": ["アクション—！", "ワンカット OK!"],
            "sleep": "Zzz…",
            "wake": "んー…起こしたの？",
            "greet": "オンラインだよ！",
            "shy": "…もう、いじわる。",
            "dash": "ダッシュ—！",
            "spin": "ぐるぐる~",
            "wow": ["わー！", "楽しい！", "イェーイ！"],
        }
    return {
        "menu_speak": "说句话", "menu_clap": "打个板 🎬",
        "menu_spin": "转一圈 🔄", "menu_run": "小短腿快走 🏃",
        "menu_shy": "害羞一下 😳", "menu_sleep": "睡一觉",
        "menu_exit": "退出",
        "lines": [
            "token 又免费了，快薅！", "今天的格子，点亮了吗？",
            "Agent & RAG，学着呢。", "free tier 也要有梦想。",
            "README 已经是英文的了哦。", "我的场记板呢……",
            "三个仓库，都在双平台躺着。", "慢慢做，比较快。",
            "有 bug 去公众号看我调试。", "我现在是 3D 手办了哦。",
            "你的窗口，都是我的路。",
        ],
        "grab": ["哇！", "放手！", "别提我！"],
        "land": ["着陆成功。", "一点不疼。", "再来。"],
        "cheer": ["Action——！", "咔，一条过！"],
        "sleep": "Zzz……",
        "wake": "……吵醒我了。",
        "greet": "我上线啦！",
        "shy": "……讨厌啦。",
        "dash": "冲呀——！",
        "spin": "转起来～",
        "wow": ["哇！", "开心！", "耶！"],
    }


def _bridge_texts(lang):
    """宿主桥接提醒文案（5 语言，键同 host_bridge.Notice.kind）。"""
    table = {
        "zh": {"waiting": "等你确认：{label}", "waiting_plain": "等你确认～",
               "turn_end": "本轮回复结束", "done": "任务完成！",
               "failed": "出问题了：{label}", "failed_plain": "出问题了…",
               "tool_fail": "工具出错，再试一次"},
        "zh-Hant": {"waiting": "等你確認：{label}", "waiting_plain": "等你確認～",
                    "turn_end": "本輪回覆結束", "done": "任務完成！",
                    "failed": "出問題了：{label}", "failed_plain": "出問題了…",
                    "tool_fail": "工具出錯，再試一次"},
        "en": {"waiting": "Waiting for you: {label}", "waiting_plain": "Waiting for you~",
               "turn_end": "Turn finished", "done": "Task done!",
               "failed": "Something failed: {label}", "failed_plain": "Something failed…",
               "tool_fail": "Tool error, retrying"},
        "ko": {"waiting": "확인 기다려요: {label}", "waiting_plain": "확인 기다려요~",
               "turn_end": "이번 턴 끝", "done": "과제 완료!",
               "failed": "문제가 생겼어요: {label}", "failed_plain": "문제가 생겼어요…",
               "tool_fail": "도구 오류, 재시도 중"},
        "ja": {"waiting": "確認待ち：{label}", "waiting_plain": "確認待ち～",
               "turn_end": "このターン終了", "done": "タスク完了！",
               "failed": "問題が起きた：{label}", "failed_plain": "問題が起きた…",
               "tool_fail": "ツールエラー、再試行"},
    }
    return table.get(lang, table["zh"])


def _detect_lang():
    """系统 UI 语言检测：中/日/韩 → 对应语言，其余 → 英文。"""
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x04: "zh", 0x11: "ja", 0x12: "ko"}.get(lid, "en")
    except Exception:
        return "zh"


FRAMES_DIR, LANG = _load_profile()
_T = _texts(LANG)
_BT = _bridge_texts(LANG)
LINES = _T["lines"]
GRAB_LINES = _T["grab"]
LAND_LINES = _T["land"]
CHEER_LINES = _T["cheer"]
SLEEP_LINE = _T["sleep"]

# 单实例：绑定本地端口。进程退出端口立即释放，不会有互斥锁僵尸句柄问题
try:
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _sock.bind(("127.0.0.1", 56570))
    _sock.listen(0)
except OSError:
    # 已有实例在跑；若是其他程序占了端口，留一条日志便于排查
    try:
        logdir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE
        logf = os.path.join(logdir, "crash.log")
        if os.path.exists(logf) and os.path.getsize(logf) > 65536:
            os.remove(logf)
        with open(logf, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%F %T] 单实例端口 56570 被占，退出（可能是已有实例）\n"))
    except OSError:
        pass
    sys.exit(0)                                        # 已有实例在跑

MAGENTA = "#FF00FF"
SIZE = 200                   # 画布边长
GROUND_MARGIN = 6            # 距屏幕底边
WALK_SPEED = 2.5             # 步速与步态帧率匹配（10 tick/步 ≈ 25px 一步）
PLAYBACK_SPEED = 0.75        # 动作、移动与轮播共用的整体速度
LOGIC_DT = 0.05 / PLAYBACK_SPEED  # 渲染频率不变，逻辑时间放慢
RENDER_MS = 16               # 渲染间隔 ~60fps（动画相位/窗口位置在逻辑步间插值）
WALK_CYCLE_MS = 1150         # 走路整循环时长：帧周期=时长/帧数（24帧≈48ms）
TURN_TICKS = 6               # 转身过渡：正面帧短停顿（300ms），抹掉镜像硬切
GRAVITY = 3
FOOT_INSET = 40              # 脚底支撑判定的左右内缩
PLATFORM_MIN_W = 180         # 窗口至少这么宽才配当平台
PLATFORM_MIN_TOP = 240       # 太靠上的窗口顶不站（会半截出屏）
PLAT_TOL = 8                 # 站立面吸附容差

FRAMES = ["idle_0", "idle_1", "idle_2", "grab_0", "grab_1", "fall_0", "land_0",
          "sleep_0", "sleep_1", "greet_0", "cheer_0", "cheer_1",
          "spin_0", "spin_1", "spin_2", "spin_3",
          "bounce_0", "bounce_1", "happy_0", "happy_1", "shy_0"]
for _d in ("l", "r"):
    # legacy 24 相位程序步态（ASSET-FIRST 冻结：保留 fallback，优先级低于 av_walk）
    FRAMES += [f"walk_{_d}_{i}" for i in range(24)]
    # av_walk：8 帧真素材（GPT 同视角步态循环，见 characters/iven-pet/animations/walk）
    FRAMES += [f"av_walk_{_d}_{i:02d}" for i in range(8)]
    FRAMES += [f"fast_{_d}_{i}" for i in range(2)]

LINES = [
    "token 又免费了，快薅！",
    "今天的格子，点亮了吗？",
    "Agent & RAG，学着呢。",
    "free tier 也要有梦想。",
    "README 已经是英文的了哦。",
    "三个仓库，都在双平台躺着。",
    "慢慢做，比较快。",
    "有 bug 去公众号看我调试。",
    "Action！开拍啦！",
    "我现在是 3D 手办了哦。",
    "你的窗口，都是我的路。",
]
GRAB_LINES = ["哇！", "放手！", "别提我！"]
LAND_LINES = ["着陆成功。", "一点不疼。", "再来。"]
CHEER_LINES = ["Action——！", "咔，一条过！"]
SLEEP_LINE = "Zzz……"


def enum_window_platforms(exclude=()):
    """可见窗口的顶边 → [(x0, surface_y, x1)]，用 DWM 可视边界（去掉隐形边框）。

    过滤：不可见/最小化/工具窗/幻影窗(UWP cloak)/无标题/太窄/太靠上。
    """
    if ctypes is None:
        return []
    u32 = ctypes.windll.user32
    dwm = ctypes.windll.dwmapi
    out = []

    def cb(hwnd, lparam):
        try:
            if hwnd in exclude:
                return True
            if not u32.IsWindowVisible(hwnd) or u32.IsIconic(hwnd):
                return True
            if u32.GetWindowLongW(hwnd, -20) & 0x80:        # WS_EX_TOOLWINDOW
                return True
            cloaked = wintypes.DWORD(0)
            if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked),
                                         ctypes.sizeof(cloaked)) == 0 and cloaked.value:
                return True                                  # DWMWA_CLOAKED
            rect = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect),
                                         ctypes.sizeof(rect)) != 0:   # EXTENDED_FRAME_BOUNDS
                if not u32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w < PLATFORM_MIN_W or h < 80:
                return True
            if u32.GetWindowTextLengthW(hwnd) == 0:
                return True
            if rect.top < PLATFORM_MIN_TOP:
                return True
            out.append((rect.left, rect.top, rect.right))
        except Exception:
            pass
        return True

    proc = _WNDENUMPROC(cb)
    u32.EnumWindows(proc, 0)
    return out


def taskbar_top():
    """主任务栏顶边的屏幕 y 坐标（她该站的地方），找不到/位置异常返回 None。"""
    if ctypes is None:
        return None
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if not u32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        top = rect.top
    except Exception:
        return None
    sh = u32.GetSystemMetrics(1)
    if not (200 <= top <= sh - 40):
        return None                                    # 贴顶/自动隐藏等异常位置
    return top


class Pet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.title("Iven Pet · 独立桌宠")
        self.background = configure_transparency(self.root)

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        # 基础地面 = 任务栏顶边（站在任务栏上），取不到再用屏幕底边
        self.base = taskbar_top() or (self.sh - GROUND_MARGIN)
        self.ground = self.base - SIZE

        self.canvas = tk.Canvas(self.root, width=SIZE, height=SIZE,
                                bg=self.background, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.frames = {}
        self.clips = load_clips(FRAMES_DIR)
        self.behaviors = load_behaviors(BASE)
        extra_frames = {name for names, _ in self.clips.values() for name in names}
        for name in sorted(set(FRAMES) | extra_frames):
            path = frame_path(FRAMES_DIR, name)
            if path.is_file():
                image = tk.PhotoImage(file=str(path))
                if sys.platform == "darwin" and path.suffix == ".gif":
                    clear_legacy_color_key(image)
                self.frames[name] = image
        if "idle_0" not in self.frames:
            raise FileNotFoundError(f"帧目录缺少 idle_0.gif: {FRAMES_DIR}")
        # 兜底帧：优先 fall_0（状态机主帧），否则任意可用帧（最小角色集也活）
        self._fallback = ("fall_0" if "fall_0" in self.frames
                          else next(iter(self.frames)))
        # 走路序列按实际可用帧动态生成；帧周期=整循环时长/帧数
        # （24 帧→48ms/帧、8 帧→144ms、4 帧→288ms，帧数越多越顺滑）
        self._walk_seq = {}
        self._walk_period = {}
        for d in ("l", "r"):
            av = [f"av_walk_{d}_{i:02d}" for i in range(8)
                  if f"av_walk_{d}_{i:02d}" in self.frames]
            if len(av) == 8:                     # 真素材优先：12 FPS
                self._walk_seq[d] = av
                self._walk_period[d] = round(1000 / 12)
                continue
            seq = [f"walk_{d}_{i}" for i in range(24) if f"walk_{d}_{i}" in self.frames]
            if len(seq) < 8:
                seq = [f"walk_{d}_{i}" for i in range(4) if f"walk_{d}_{i}" in self.frames]
            self._walk_seq[d] = seq
            self._walk_period[d] = max(40, round(WALK_CYCLE_MS / max(1, len(seq))))
        self.sprite = self.canvas.create_image(0, 0, image=self.frames["fall_0"],
                                               anchor="nw")

        # 自身窗口句柄（平台枚举时排除自己）
        self.hwnd = self.root.winfo_id()
        if ctypes is not None:
            self.hwnd = ctypes.windll.user32.GetParent(self.hwnd) or self.hwnd
        self.plats = []
        self._plat_cd = 0

        # 状态
        self.state = "FALL"          # 开场从天上掉下来，落地后打招呼
        self.x, self.y = random.randint(100, self.sw - SIZE - 100), 40
        self.vy = 0
        self.dir = random.choice((-1, 1))
        self.tick_n = 0
        self.state_left = 0
        self.autoplay = True
        self._action_deck = []
        self._last_auto_action = None
        self._clip_deadline = None
        self.first_land = True
        self.last_input = 0
        self.drag_off = None
        self.press_pos = None
        self.bubble = None
        self.bubble_job = None
        self._follow_badge = None
        self._follow_label = None
        self._follow_key = None
        self._bubble_key = None
        self._bubble_persistent = False
        self._bubble_deadline = 0
        self._bubble_position = None

        # 宿主桥接（可选能力；无收件箱时 poll 静默空转，桌宠完全独立）
        self.host = (HostBridge()
                     if os.environ.get("PET_BRIDGE", "1") != "0" else None)
        self._bridge_on = self.host is not None
        self._host_poll_cd = 10          # 首轮 ~0.5s 后开始轮询
        self._host_hold = 0              # 手动点播的宿主抑制窗口（tick）
        self._sleep_queue = []           # 睡眠期间的重要提醒，醒来补播
        self._host_label_shown = None
        self._host_dwell = False         # 工作节奏：打一轮板后的喘气间隙
        self._host_action = False        # 区分真实宿主状态与普通轮播的同名动作
        self._waiting_since = None
        self._waiting_source = None
        self._embedded_display = False
        self._display_poll_at = 0

        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
        self._bind()
        # 双层主循环：逻辑固定步长 + 高频渲染插值，见 _loop/_render
        self._px, self._py = self.x, self.y     # 渲染插值锚点（上一步位置）
        self._logic_next = time.monotonic() + LOGIC_DT
        self._anim_key = ("still", "fall_0")    # ("still",名)|("seq",帧表,周期ms)|("spin",)
        self._anim_t0 = time.monotonic()
        self._shown = None                      # 当前已上屏帧名（去重 itemconfig）
        self._turn = 0                          # 转身过渡剩余 tick
        self._idle_fx = 0                        # 待机微动作剩余 tick
        self._idle_fx_frame = None
        self.root.after(RENDER_MS, self._loop)

    # ---------- 平台 ----------
    def _all_platforms(self):
        return self.plats + [(0, self.base, self.sw)]

    def _support(self):
        """脚底下踩着的平台，没有则 None。"""
        span_l, span_r = self.x + FOOT_INSET, self.x + SIZE - FOOT_INSET
        sy = self.y + SIZE
        for (x0, py, x1) in self._all_platforms():
            if x0 <= span_r and x1 >= span_l and abs(py - sy) <= PLAT_TOL:
                return (x0, py, x1)
        return None

    # ---------- 输入 ----------
    def _set_language(self, language):
        global LANG, _T, _BT, LINES, GRAB_LINES, LAND_LINES, CHEER_LINES, SLEEP_LINE
        save_language(language)
        self._ui_language = language
        LANG = _detect_lang() if language == "system" else language
        _T, _BT = _texts(LANG), _bridge_texts(LANG)
        LINES, GRAB_LINES, LAND_LINES = _T["lines"], _T["grab"], _T["land"]
        CHEER_LINES, SLEEP_LINE = _T["cheer"], _T["sleep"]
        self._hide_bubble()
        self._follow_key = None
        self._bind()

    @staticmethod
    def _menu_text(chinese, english):
        return chinese if LANG.startswith("zh") else english

    def _bind(self):
        old_menu = getattr(self, "_context_menu", None)
        if old_menu is not None:
            self.root.after_idle(old_menu.destroy)
        c = self.canvas
        c.bind("<Button-1>", self._press)
        c.bind("<Double-Button-1>", self._double)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        menu = tk.Menu(self.root, tearoff=0)
        self._context_menu = menu
        menu.add_command(label=self._menu_text("Iven Pet · 独立桌宠", "Iven Pet · Desktop companion"), state="disabled")
        menu.add_separator()
        menu.add_command(label=_T["menu_speak"], command=lambda: self.say(random.choice(LINES)))
        if {"cheer_0", "cheer_1"} <= self.frames.keys():
            menu.add_command(label=_T["menu_clap"], command=self._to_cheer)
        if {"spin_0", "spin_1", "spin_2", "spin_3"} <= self.frames.keys():
            label = ({"zh": "四处看看 👀", "zh-TW": "四處看看 👀", "en": "Look around 👀",
                      "ja": "見回す 👀", "ko": "둘러보기 👀"}.get(LANG, "Look around 👀")
                     if "SPIN" in self.clips else _T["menu_spin"])
            menu.add_command(label=label, command=self._to_spin)
        if "fast_l_0" in self.frames:
            menu.add_command(label=_T["menu_run"], command=self._to_run)
        if "shy_0" in self.frames:
            menu.add_command(label=_T["menu_shy"], command=self._to_shy)
        auto = tk.BooleanVar(value=self.autoplay)
        menu.add_checkbutton(label=self._menu_text("自动轮播动作", "Automatic animations"), variable=auto,
                             command=lambda: setattr(self, "autoplay", auto.get()))
        display = tk.Menu(menu, tearoff=0)
        display_choice = tk.StringVar(value="embedded" if self._embedded_display else "desktop")
        display.configure(postcommand=lambda: display_choice.set("embedded" if self._embedded_display else "desktop"))
        for mode, zh, en in (("desktop", "独立桌面", "Desktop"), ("embedded", "DSH 界面内", "Inside DSH")):
            display.add_radiobutton(label=self._menu_text(zh, en), variable=display_choice,
                                    value=mode, command=lambda: self._set_display_mode(display_choice.get()))
        display.add_separator()
        display.add_command(label=self._menu_text("DSH 需保持打开；未接通时 30 秒回桌面", "Keep DSH open; returns to desktop after 30s if unavailable"),
                            state="disabled")
        menu.add_cascade(label=self._menu_text("显示模式", "Display mode"), menu=display)
        if self.host is not None:
            def _toggle_bridge():
                self._bridge_on = bool(bridge.get())
                if not self._bridge_on and (self._host_action or self._host_dwell):
                    self._set_state("IDLE", random.randint(40, 80))
                    if self._bubble_persistent:
                        self._hide_bubble()
            bridge = tk.BooleanVar(value=self._bridge_on)
            menu.add_checkbutton(label=self._menu_text("宿主桥接", "Host bridge"), variable=bridge,
                                 command=_toggle_bridge)
        if self.host is not None:
            tracking = tk.Menu(menu, tearoff=0)
            choice = tk.StringVar(value=self.host.selected_source or "")
            def select_source():
                self.host.select_source(choice.get() or None)
                self._sleep_queue.clear()
                self._hide_bubble()
            def refresh_sources():
                from bridge_display import SOURCES
                tracking.delete(0, "end")
                tracking.add_radiobutton(label=self._menu_text("自动 · 全部已接入", "Automatic · All connected"), variable=choice,
                                         value="", command=select_source)
                for source, name in SOURCES.items():
                    status = self.host.source_status(source)
                    if not LANG.startswith("zh"):
                        status = {"工作中":"Working", "等你确认":"Needs approval",
                                  "未收到事件":"No events received", "空闲（已收到事件）":"Idle (events received)"}.get(status, status)
                    tracking.add_radiobutton(label=name+" · "+status,
                                             variable=choice, value=source, command=select_source)
                tracking.add_separator()
                tracking.add_command(label=self._menu_text("自动：确认优先 → 最近活动", "Auto: approvals → recent activity"), state="disabled")
            tracking.configure(postcommand=refresh_sources)
            menu.add_cascade(label=self._menu_text("跟踪 Harness", "Track Harness"), menu=tracking)
        for state, title in (("STRETCH", "伸懒腰 / Stretch"), ("DOZE", "打瞌睡 / Doze"),
                             ("RUBIK", "玩魔方 / Rubik cube"), ("WAITING", "等待 / Waiting"), ("WORK", "工作 / Working"),
                             ("REVIEW", "检查 / Reviewing"), ("FAILED", "失落 / Sad"),
                             ("THINKING", "苦思冥想 / Deep in thought"), ("IMPATIENT", "等待不耐烦 / Getting impatient"),
                             ("TOKEN_LOW", "额度不足（手动表演） / Low budget (manual performance)"),
                             ("RELIEVED", "松口气 / Relieved")):
            if state in self.clips:
                menu.add_command(label=title.split(" / ")[0 if LANG.startswith("zh") else 1], command=lambda s=state: self._menu_clip(s))
        menu.add_command(label=_T["menu_sleep"], command=self._to_sleep)
        menu.add_separator()
        languages = tk.Menu(menu, tearoff=0)
        preference = getattr(self, "_ui_language", load_language())
        language_choice = tk.StringVar(value=preference)
        for code, name in (("system", self._menu_text("跟随系统", "System default")),
                           ("zh", "简体中文"), ("en", "English")):
            languages.add_radiobutton(label=name, value=code, variable=language_choice,
                                      command=lambda: self._set_language(language_choice.get()))
        menu.add_cascade(label=self._menu_text("语言 / Language", "Language / 语言"), menu=languages)
        menu.add_command(label=self._menu_text("打开 GitHub 仓库", "Open GitHub repository"),
                         command=lambda: webbrowser.open("https://github.com/IvenKooLab/desktop-pet"))
        menu.add_command(label=_T["menu_exit"], command=self.root.destroy)
        c.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        if sys.platform == "darwin":
            c.bind("<Button-2>", lambda e: menu.tk_popup(e.x_root, e.y_root))
            def control_menu(e):
                menu.tk_popup(e.x_root, e.y_root)
                return "break"
            c.bind("<Control-Button-1>", control_menu)

    def _touch(self):
        self.last_input = self.tick_n

    def _press(self, e):
        self._touch()
        self.drag_off = (e.x, e.y)
        self.press_pos = (e.x_root, e.y_root)
        if self.state not in ("GRAB",):
            self._set_state("GRAB")
            if random.random() < 0.4:
                self.say(random.choice(GRAB_LINES), 900)

    def _double(self, e):
        self._touch()
        if self._support() is None:
            return
        if "happy_0" in self.frames:                  # 双击：开心反应（MVP 缺帧时跳过）
            self._manual(60)
            self._set_state("HAPPY", 26)
            self.say(random.choice(_T["wow"]), 1600)

    def _drag(self, e):
        self._touch()
        if self.drag_off is None:
            return
        self.x = e.x_root - self.drag_off[0]
        self.y = e.y_root - self.drag_off[1]
        self._px, self._py = self.x, self.y     # 拖拽直通，不做步间插值
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    def _release(self, e):
        if self.press_pos is None or self.drag_off is None:
            return
        moved = abs(e.x_root - self.press_pos[0]) + abs(e.y_root - self.press_pos[1])
        if moved < 6:                                   # 点击（非拖拽）→ 弹跳
            if self.state == "SLEEP":
                self.say(_T["wake"], 1500)
                self._set_state("IDLE", random.randint(60, 120))
                if self._sleep_queue:                   # 补播睡眠期间的重要提醒
                    pending = self._sleep_queue[-1]
                    self._sleep_queue = []
                    self.root.after(700, lambda: self._host_notice(pending))
            elif self.state not in ("CHEER", "SPIN", "BOUNCE", "HAPPY", "SHY"):
                grounded = self._support() is not None
                if grounded and "bounce_0" in self.frames:
                    self._manual(50)
                    self._set_state("BOUNCE", 16)
                elif self.state == "GRAB":
                    # 无弹跳帧的素材（MVP）：点了也要离开 GRAB，防卡死
                    self._set_state("IDLE", random.randint(60, 120)) if grounded \
                        else self._to_fall()
                self.say(random.choice(LINES))
        elif self.state == "GRAB":
            self._to_fall()                             # 松手 → 重力接管
        self.drag_off = None
        self.press_pos = None

    # ---------- 状态切换 ----------
    def _set_state(self, s, duration=0):
        self.state, self.state_left = s, duration
        self._clip_deadline = None
        self._host_action = False
        self._host_dwell = False

    def _start_clip(self, state, cycles=1):
        """Start a complete performance now, independently of the next logic tick."""
        clip = self.clips[state]
        self._set_state(state, performance_ticks(clip[1], cycles))
        self._anim_key = None
        self._play_clip(state, [], 1)
        self._clip_deadline = self._anim_t0 + sum(clip[1]) * cycles / (1000 * PLAYBACK_SPEED)

    def _clip_finished(self):
        deadline = self._clip_deadline
        return time.monotonic() >= deadline if deadline is not None else self.state_left <= 0

    def _idle(self):
        low, high = self.behaviors["idle_seconds"]
        self._set_state("IDLE", round(random.uniform(low, high) * 20))

    def _performance_cycles(self, state):
        low, high = self.behaviors["actions"].get(state, (1, 1))
        return random.randint(low, high)

    def _next_auto_action(self):
        if not self.autoplay:
            self._idle()
            return
        if not self._action_deck:
            self._action_deck = [s for s in self.behaviors["actions"] if s in self.clips]
            self._action_deck += ["WALK"]
            random.shuffle(self._action_deck)
            if len(self._action_deck) > 1 and self._action_deck[-1] == self._last_auto_action:
                self._action_deck[0], self._action_deck[-1] = self._action_deck[-1], self._action_deck[0]
        # Several menu names intentionally reuse one clip. Avoid showing the same
        # artwork twice in succession when a different performance is available.
        previous = self.clips.get(self._last_auto_action)
        if previous and len(self._action_deck) > 1 and self.clips.get(self._action_deck[-1]) == previous:
            for index, candidate in enumerate(self._action_deck[:-1]):
                if self.clips.get(candidate) != previous:
                    self._action_deck[index], self._action_deck[-1] = self._action_deck[-1], candidate
                    break
        state = self._action_deck.pop()
        self._last_auto_action = state
        if state == "WALK":
            self.dir = random.choice((-1, 1))
            clip = self.clips.get("WALK_l" if self.dir < 0 else "WALK_r")
            cycles = random.randint(*self.behaviors["walk_cycles"])
            self._set_state("WALK", performance_ticks(clip[1], cycles) if clip else random.randint(100, 160))
        else:
            self._start_clip(state, self._performance_cycles(state))

    def _menu_clip(self, state):
        self._touch()
        if self._support() is not None:
            self._start_clip(state, self._performance_cycles(state))
            self._manual(self.state_left + 30)

    def _front_frame(self):
        """正面立绘帧名（转身过渡用）：优先 idle_0（正视图），无则 spin_0。"""
        for n in ("idle_0", "spin_0"):
            if n in self.frames:
                return n
        return None

    def _flip(self):
        """掉头；有正面帧时插入短促转身过渡，否则直接镜像。"""
        self.dir *= -1
        if self._front_frame():
            self._turn = TURN_TICKS

    def _to_walk(self):
        self._touch()
        self.dir = random.choice((-1, 1))
        self._set_state("WALK", random.randint(100, 260))

    def _to_run(self):
        self._touch()
        if self._support() is None:
            return
        self.dir = random.choice((-1, 1))
        ticks = random.randint(120, 220)
        self._manual(ticks + 30)
        self._set_state("RUN", ticks)
        self.say(_T["dash"], 1500)

    def _to_shy(self):
        if "SHY" in self.clips:
            self._menu_clip("SHY")
            return
        self._touch()
        if self._support() is None:
            return
        self._manual(60)
        self._set_state("SHY", 30)
        self.say(_T["shy"], 1800)

    def _to_fall(self):
        self.vy = 0
        self._set_state("FALL")

    def _to_sleep(self):
        self._set_state("SLEEP")
        self.say(SLEEP_LINE, 2000)

    def _to_cheer(self):
        if "CHEER" in self.clips:
            self._menu_clip("CHEER")
            return
        self._touch()
        if self._support() is None:
            return
        self._manual(60)
        self._set_state("CHEER", 26)
        self.say(random.choice(CHEER_LINES), 1800)

    def _to_spin(self):
        if "SPIN" in self.clips:
            self._menu_clip("SPIN")
            return
        self._touch()
        if self._support() is None:
            return
        self._manual(60)
        self._set_state("SPIN", 32)                   # 4 帧 × 2 圈
        self.say(("看看周围～" if LANG.startswith("zh") else "Looking around~")
                 if "SPIN" in self.clips else _T["spin"], 1500)

    # ---------- 宿主桥接 ----------
    def _manual(self, ticks):
        """手动点播后暂时压住宿主接管，播完再还回去。"""
        self._host_hold = self.tick_n + ticks

    def _host_busy(self):
        """宿主提醒不得打断的情形：拖拽中/下落中/刚操作/手动点播窗口。"""
        return (self.drag_off is not None
                or self.state in ("GRAB", "FALL", "LAND")
                or self.tick_n - self.last_input < 30
                or self._host_hold > self.tick_n)

    def _host_poll(self):
        if self.host is None or not self._bridge_on:
            return
        try:
            for notice in self.host.poll():
                if os.environ.get("IVEN_BRIDGE_DEBUG"):
                    print(f"[bridge] notice={notice.kind} label={notice.label} "
                          f"mode={self.host.mode}", flush=True)
                self._host_notice(notice)
        except Exception:
            pass                                  # 桥接异常不影响桌宠本体

    def _host_notice(self, n):
        """一次性提醒 → 动作/气泡。睡眠不唤醒，重要提醒入队。"""
        if self.state == "SLEEP":
            if n.kind in ("permission.required", "turn.failed", "task.completed") \
                    and len(self._sleep_queue) < 3:
                self._sleep_queue.append(n)
            return
        if self._host_busy():
            return
        if n.kind == "permission.required":
            if "WAITING" in self.clips:
                self._set_state("WAITING", 10 ** 9)
                self._host_action = True
                card = status_card(self.host, LANG.startswith("zh")) if self.host else None
                if card:
                    self.say(card[1], 0, title=card[0], tone=card[2])
        elif n.kind == "tool.failed":
            if self.host and self.host.mode == "working" and "FAILED" in self.clips:
                self._set_state("FAILED", (sum(self.clips["FAILED"][1]) + 49) // 50)
        elif n.kind == "turn.failed":
            if "FAILED" in self.clips:
                self._set_state("FAILED", (sum(self.clips["FAILED"][1]) + 49) // 50)
            self.say(_BT["failed"].format(label=n.label) if n.label
                     else _BT["failed_plain"], 6000, title=_BT["failed_plain"], tone="error")
        elif n.kind == "task.completed":
            pick = next((state for state in ("RELIEVED", "CHEER", "HAPPY") if state in self.clips), None)
            if pick:
                self._start_clip(pick)
                self._manual(self.state_left + 30)
            self.say(n.label or _BT["done"], 7000, title=_BT["done"], tone="done")
        elif n.kind == "turn.ended":
            # Stop 语义：只是"本轮回复结束"，绝不宣称任务成功
            if self._host_action or self._host_dwell:
                self._host_dwell = False
                self._set_state("IDLE", random.randint(40, 80))
            self.say(n.label or _BT["turn_end"], 7000, title=_BT["turn_end"], tone="done")

    def _host_assert(self):
        """边界断言：等待确认 > 宿主工作 > 普通轮播。

        工作状态不无限连打板：打一轮 WORK 后进 IDLE 喘气（_host_dwell），
        到点由 IDLE 分支回 WORK；等待保持 WAITING 姿势（由归约器静默退 idle）。
        """
        if self.host is None or not self._bridge_on:
            self._waiting_since = self._waiting_source = None
            return
        if self.host.mode is None:
            self._waiting_since = self._waiting_source = None
            if self._host_action or self._host_dwell:
                self._host_dwell = False
                self._set_state("IDLE", random.randint(40, 80))
            self._host_label_shown = None
            if self._bubble_persistent:
                self._hide_bubble()
            return
        if self.host.mode != "waiting":
            self._waiting_since = self._waiting_source = None
        if (self.state in ("SLEEP", "GRAB", "FALL", "LAND")
                or self.drag_off is not None or self._host_hold > self.tick_n):
            if self._bubble_persistent:
                self._hide_bubble()
            return
        if self._bubble_persistent or self._bubble_deadline <= time.monotonic():
            card = status_card(self.host, LANG.startswith("zh"))
            if card:
                self.say(card[1], 0, title=card[0], tone=card[2])
        if self.host.mode == "waiting":
            source = getattr(self.host, "source", None)
            if self._waiting_since is None or self._waiting_source != source:
                self._waiting_since, self._waiting_source = time.monotonic(), source
            target = "IMPATIENT" if time.monotonic() - self._waiting_since >= 30 and "IMPATIENT" in self.clips else "WAITING"
            if target in self.clips and (self.state != target or not self._host_action):
                self._host_dwell = False
                self._set_state(target, 10 ** 9)
                self._host_action = True
            return
        self._waiting_since = self._waiting_source = None
        if "WORK" not in self.clips:
            return
        if self.state == "WORK" and self._host_action:
            return
        if self.state in ("IDLE", "THINKING") and self._host_dwell:
            return                             # 喘气中，播完自动回 WORK
        self._enter_work()

    def _enter_work(self):
        self._host_dwell = False
        self._start_clip("WORK")
        self._host_action = True

    def _update_display_mode(self, now):
        if now < self._display_poll_at:
            return
        self._display_poll_at = now + 0.25
        events = self.host.dir if self.host is not None else default_dir()
        embedded = read_display_mode(events) == "embedded"
        if embedded == self._embedded_display:
            return
        self._embedded_display = embedded
        if embedded:
            self.root.withdraw()
            self._hide_bubble()
            if self._follow_badge:
                self._follow_badge.withdraw()
        else:
            self.root.deiconify()
            if self._follow_badge:
                self._follow_badge.deiconify()

    def _set_display_mode(self, mode):
        events = self.host.dir if self.host is not None else default_dir()
        if write_display_mode(events, mode):
            self._display_poll_at = 0
            self._update_display_mode(time.monotonic())

    # ---------- 主循环 ----------
    def _loop(self):
        now = time.monotonic()
        self._update_display_mode(now)
        steps = 0
        while self._logic_next <= now and steps < 4:   # 追帧上限 4 步防风暴
            self._logic_step()
            self._logic_next += LOGIC_DT
            steps += 1
        if self._logic_next <= now:                    # 卡顿过久：弃追对表
            self._logic_next = now + LOGIC_DT
        self._render(now)
        self.root.after(RENDER_MS, self._loop)

    def _render(self, now):
        """高频渲染：窗口位置在逻辑步间线性插值（亚像素），动画按墙钟相位取帧。"""
        if self._embedded_display:
            return
        a = 1.0 - min(1.0, max(0.0, (self._logic_next - now) / LOGIC_DT))
        rx = self._px + (self.x - self._px) * a
        ry = self._py + (self.y - self._py) * a
        name = self._frame_at(now, a)
        if name != self._shown:
            self._shown = name
            self.canvas.itemconfig(self.sprite,
                                   image=self.frames.get(name, self.frames[self._fallback]))
        self.root.geometry(f"+{int(rx)}+{int(ry)}")
        self._place_bubble()
        self._update_following_badge()

    def _frame_at(self, now, alpha):
        """当前应显示的帧名。alpha=当前逻辑步内进度 0~1（SPIN 用其连续取面）。"""
        spec = self._anim_key
        if spec[0] == "clip":
            _, names, durations = spec
            return timed_frame(names, durations, (now - self._anim_t0) * 1000 * PLAYBACK_SPEED)
        if spec[0] == "seq":
            _, names, period = spec
            if not names:                               # 自定义帧目录缺整组帧时兜底
                return self._fallback
            return names[int((now - self._anim_t0) * 1000 * PLAYBACK_SPEED / period) % len(names)]
        if spec[0] == "spin":
            names = [n for n in ("spin_0", "spin_1", "spin_2", "spin_3")
                     if n in self.frames]
            if not names:
                return self._fallback
            prog = (32 - max(self.state_left, 0)) + alpha   # 每 8 tick 换一面
            return names[int(prog // 8) % len(names)]
        return spec[1]

    def _logic_step(self):
        """固定 50ms 逻辑步（tick 语义与原版一致）。"""
        self._px, self._py = self.x, self.y          # 渲染插值锚点（步前位置）
        self.tick_n += 1
        if self.state != "GRAB":
            self.state_left -= 1

        # 平台清单每 0.5s 刷新一次
        self._plat_cd -= 1
        if self._plat_cd <= 0:
            self.plats = enum_window_platforms((self.hwnd,))
            self._plat_cd = 10

        # 宿主桥接：0.5s 轮询收件箱，随后在边界上维持/退出持续状态
        self._host_poll_cd -= 1
        if self._host_poll_cd <= 0:
            self._host_poll_cd = 10
            self._host_poll()
        self._host_assert()

        # 站立类状态：吸附/跟随脚下的平台；平台消失 → 掉落
        if self.state not in ("FALL", "GRAB"):
            s = self._support()
            if s is None:
                self._to_fall()
            else:
                self.y = s[1] - SIZE

        if self.state == "IDLE":
            self._play_clip("IDLE", ["idle_0", "idle_1", "idle_2"], 1000)
            # 随机微动作（路线C简化版）：低概率眨眼/浅笑，待机永不完全重复
            if self._idle_fx > 0:
                self._idle_fx -= 1
                if self._idle_fx_frame:
                    self._show(self._idle_fx_frame)
            elif random.random() < 0.0015:               # 平均 ~33s 一次
                pool = [n for n in ("shy_0", "happy_0") if n in self.frames]
                if pool:
                    self._idle_fx_frame = random.choice(pool)
                    self._idle_fx = 6                    # 300ms
            if self.state_left <= 0:
                if self._host_dwell:
                    # 工作喘气结束：宿主仍在干活就再打一轮板，否则回普通轮播
                    if (self.host and self._bridge_on
                            and self.host.mode == "working"
                            and not self._host_busy()):
                        self._enter_work()
                    else:
                        self._host_dwell = False
                        self._next_auto_action()
                else:
                    self._next_auto_action()

        elif self.state in ("WALK", "RUN"):
            s = self._support()
            if s is None:
                self._to_fall()
            elif self._turn > 0:
                # 转身过渡：正面帧短停顿，不位移（抹掉左右镜像硬切）
                self._turn -= 1
                self._show(self._front_frame())
            else:
                run = self.state == "RUN"
                d = "l" if self.dir < 0 else "r"
                if run:
                    self._play_clip("RUN_" + d, [f"fast_{d}_0", f"fast_{d}_1"], 250)
                    self.x += self.dir * (WALK_SPEED + 2)
                else:
                    self._play_clip("WALK_" + d, self._walk_seq[d], self._walk_period[d])
                    self.x += self.dir * WALK_SPEED
                nx = self.x
                if nx + FOOT_INSET < s[0] or nx + SIZE - FOOT_INSET > s[2]:
                    if random.random() < 0.6:           # 到窗口边缘：多半掉头
                        self._flip()
                        nx = self.x
                    # 否则径直走下去 → 下个 tick 失去支撑自然掉落
                if nx < -20 or nx > self.sw - SIZE + 20:
                    self._flip()
                    nx = self.x
                self.x = nx
                if self.state_left <= 0:
                    self._idle()
                if random.random() < 0.004:
                    self.say(random.choice(LINES))

        elif self.state == "GRAB":
            self._play_clip("GRAB", ["grab_0", "grab_1"], 200)

        elif self.state == "FALL":
            prev_feet = self.y + SIZE
            self.vy += GRAVITY
            self.y += self.vy
            feet = self.y + SIZE
            span_l, span_r = self.x + FOOT_INSET, self.x + SIZE - FOOT_INSET
            hits = sorted(py for (x0, py, x1) in self._all_platforms()
                          if x0 <= span_r and x1 >= span_l and prev_feet <= py <= feet)
            if hits:                                    # 最先碰到的面
                self.y = hits[0] - SIZE
                self._set_state("LAND", 10)
            elif self.y >= self.ground:
                self.y = self.ground
                self._set_state("LAND", 10)
            else:
                self._show("fall_0")

        elif self.state == "LAND":
            self._show("land_0")
            if self.state_left <= 0:
                if self.first_land:
                    self.first_land = False
                    if "greet_0" in self.frames:
                        self._set_state("GREET", 30)
                        self.say(_T["greet"], 1800)
                    else:
                        self._set_state("IDLE", random.randint(60, 120))
                        self.say(_T["greet"], 1800)
                else:
                    self._set_state("IDLE", random.randint(60, 120))
                    if random.random() < 0.5:
                        self.say(random.choice(LAND_LINES), 1200)

        elif self.state == "GREET":
            self._play_clip("GREET", ["greet_0"], 1500)
            if self._clip_finished():
                self._idle()

        elif self.state in ("WAITING", "WORK", "REVIEW", "FAILED", "STRETCH", "DOZE", "RUBIK",
                            "THINKING", "IMPATIENT", "TOKEN_LOW", "RELIEVED"):
            self._play_clip(self.state, [], 1)
            if self._clip_finished():
                if self._host_action and self.state == "WORK" and self.host and self._bridge_on \
                        and self.host.mode == "working":
                    if "THINKING" in self.clips:
                        self._start_clip("THINKING")
                        self._host_action = True
                    else:
                        self._set_state("IDLE", random.randint(24, 48))
                    self._host_dwell = True          # 一轮打板后思考，避免持续连打
                elif self._host_action and self._host_dwell and self.state == "THINKING" \
                        and self.host and self._bridge_on and self.host.mode == "working":
                    self._enter_work()
                else:
                    self._idle()

        elif self.state == "SLEEP":
            self._play_clip("SLEEP", ["sleep_0", "sleep_1"], 2000)
            if random.random() < 0.002:
                self.say(SLEEP_LINE, 1500)

        elif self.state == "BOUNCE":
            self._play_clip("BOUNCE", ["bounce_0", "bounce_1"], 200)
            if self._clip_finished():
                self._idle()

        elif self.state == "HAPPY":
            self._play_clip("HAPPY", ["happy_0", "happy_1"], 300)
            if self._clip_finished():
                self._idle()

        elif self.state == "SHY":
            self._play_clip("SHY", ["shy_0"], 1500)
            if self._clip_finished():
                self._idle()

        elif self.state == "CHEER":
            self._play_clip("CHEER", ["cheer_0", "cheer_1"], 350)
            if self._clip_finished():
                self._idle()

        elif self.state == "SPIN":
            if "SPIN" in self.clips:
                self._play_clip("SPIN", [], 1)
            else:
                self._set_anim(("spin",))
            if self._clip_finished():
                self._idle()

    # ---------- 动画 ----------
    def _play_clip(self, state, legacy_names, period_ms):
        clip = self.clips.get(state)
        if clip:
            self._set_anim(("clip", clip[0], clip[1]))
        else:
            self._anim(legacy_names, period_ms)

    def _anim(self, names, period_ms):
        """循环帧组：渲染层按墙钟相位取帧（period_ms = 每帧时长）。"""
        self._set_anim(("seq", tuple(names), int(period_ms)))

    def _show(self, name):
        self._set_anim(("still", name))

    def _set_anim(self, spec):
        if spec != self._anim_key:                     # 切换动画时相位归零
            self._anim_key = spec
            self._anim_t0 = time.monotonic()

    # ---------- 台词气泡 ----------
    def _update_following_badge(self):
        text,color = following_badge(self.host if self._bridge_on else None, LANG.startswith("zh"))
        if self._follow_badge is None:
            badge = tk.Toplevel(self.root); badge.overrideredirect(True); badge.attributes("-topmost",True)
            self._follow_label = tk.Label(badge,bg="#fcfbfe",font=("Segoe UI",9),padx=9,pady=4,
                                          highlightthickness=1,highlightbackground="#d5cfe0")
            self._follow_label.pack(); self._follow_badge = badge
        if self._follow_key != (text,color):
            self._follow_key = (text,color)
            self._follow_label.configure(text="●  "+text,fg=color)
            self._follow_badge.update_idletasks()
        width = self._follow_badge.winfo_reqwidth()
        x = int(self.x+SIZE/2+50)
        if x+width > self.sw-8: x = int(self.x+SIZE/2-50-width)
        y = max(5,min(self.sh-32,int(self.y+SIZE-43)))
        self._follow_badge.geometry(f"+{max(8,x)}+{y}")

    def _hide_bubble(self):
        if self.bubble_job:
            self.root.after_cancel(self.bubble_job)
            self.bubble_job = None
        if self.bubble:
            self.bubble.destroy()
            self.bubble = None
        self._bubble_key = None
        self._bubble_persistent = False
        self._bubble_deadline = 0
        self._bubble_position = None

    def _place_bubble(self):
        if not self.bubble:
            return
        width, height = self.bubble.winfo_reqwidth(), self.bubble.winfo_reqheight()
        x = max(8, min(self.sw-width-8, int(self.x+SIZE/2-width/2)))
        y = max(8, int(self.y+52-height))
        position = (x,y)
        if position != self._bubble_position:
            self.bubble.geometry(f"+{x}+{y}")
            self._bubble_position = position

    def say(self, text, ms=2600, title=None, tone="info"):
        if self._embedded_display:
            return
        # Status cards persist until the reducer changes state, independent of animation.
        title = title or "Iven"
        text = str(text)[:160]
        key = (title,text,tone,ms == 0)
        if key == self._bubble_key and self.bubble:
            return
        self._hide_bubble()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        b.configure(bg=self.background)
        if sys.platform == "win32":
            b.attributes("-transparentcolor", self.background)
        canvas = tk.Canvas(b,width=286,height=110,bg=self.background,bd=0,highlightthickness=0)
        canvas.pack()
        font = ("Segoe UI", 10)
        body = canvas.create_text(18,39,text=text,font=font,fill="#302d38",width=250,anchor="nw")
        bounds = canvas.bbox(body)
        height = max(76,(bounds[3] if bounds else 57)+18)
        canvas.configure(height=height)
        r,w,h = 14,285,height-1
        points = [r,1,w-r,1,w,1,w,r,w,h-r,w,h,w-r,h,r,h,1,h,1,h-r,1,r,1,1]
        background = canvas.create_polygon(points,smooth=True,splinesteps=24,fill="#fcfbfe",outline="#d5cfe0",width=1)
        canvas.tag_lower(background)
        color = "#d89525" if tone == "waiting" else "#419c70" if tone == "done" else "#c95c61" if tone == "error" else "#8970ba"
        canvas.create_oval(16,19,22,25,fill=color,outline="")
        canvas.create_text(29,15,text=title,font=("Segoe UI",9,"bold"),fill="#655775",anchor="nw",width=240)
        self.bubble = b
        self._bubble_key = key
        self._bubble_persistent = ms == 0
        self._bubble_deadline = time.monotonic()+ms/1000 if ms else 0
        b.update_idletasks()
        self._place_bubble()
        self.bubble_job = self.root.after(ms,self._hide_bubble) if ms else None

    def run(self):
        self.last_input = self.tick_n
        self.root.update_idletasks()
        print("[start] Iven Pet standalone | platform=%s | Tk=%s | background=%s | frames=%s | bridge=%s" %
              (sys.platform, self.root.tk.call("info", "patchlevel"), self.background, len(self.frames),
               str(self.host.dir) if self.host else "off"), flush=True)
        self.root.after(800, lambda: print("[window] mapped=%s | canvas=%s | state=%s" %
                        (self.root.winfo_ismapped(), self.canvas.cget("bg"), self.state), flush=True))
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Pet().run()
    except Exception:
        import time
        import traceback
        logdir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE
        try:
            logf = os.path.join(logdir, "crash.log")
            if os.path.exists(logf) and os.path.getsize(logf) > 65536:
                os.remove(logf)                        # 防 crashes 无限增长
            with open(logf, "a", encoding="utf-8") as f:
                f.write(time.strftime("[%F %T]\n") + traceback.format_exc() + "\n")
        except OSError:
            pass
        raise
