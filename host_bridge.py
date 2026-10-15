"""host_bridge · 宿主（编码助手）事件桥接，收件箱消费端。运行时纯标准库。

桌宠与宿主适配器（adapters/zcode、adapters/dsh 等）之间的唯一通道是本地
收件箱目录（默认 ~/.iven-pet/events）：适配器把统一事件 JSON 原子写入，
桌宠轮询消费后删除。协议 v1 字段：

    version event_id source session_id turn_id timestamp kind
    task_label summary tool_name severity

归约语义（与 docs/BRIDGE.md 一致，Stop/turn.ended 只是"本轮结束"）：
    session.started   注册会话，不动可见状态
    turn.started      working（可带 task_label）
    tool.started      working
    permission.required  waiting + 重要提醒
    tool.finished     仍 working（只更新计数）
    tool.failed       短暂 FAILED 闪现，宿主可自行恢复
    turn.ended        本轮结束 → 回普通轮播（不宣称成功）
    turn.failed       FAILED + 重要提醒
    task.completed    明确完成 → 庆祝
    interrupted / session.ended  清理该会话；全部清空后回普通轮播

断线回退：最新事件超过 stale_after 秒未更新 → 清空所有会话静默回退，
桌宠保持独立可用。事件文本只作数据展示，绝不当指令执行。
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL_VERSION = 1
KINDS = frozenset(("session.started", "turn.started", "tool.started",
                   "permission.required", "tool.finished", "tool.failed",
                   "turn.ended", "turn.failed", "task.completed", "task.updated",
                   "interrupted", "session.ended"))
# 会触发动作/气泡的一次性通知；其余只改持续状态
IMPORTANT = frozenset(("permission.required", "turn.failed", "task.completed"))
MAX_LABEL = 80          # task_label 截断
MAX_SUMMARY = 160       # summary 截断（适配器默认不传，用户开启后才有）
MAX_EVENTS_PER_POLL = 64    # 单轮最多消费，防止风暴
MAX_BACKLOG = 500           # 收件箱超过则丢弃最旧（过期清理兜底）
EVENT_MAX_AGE = 180.0       # 事件时间戳超过即过期（宿主休眠后的陈旧事件）
STALE_AFTER = 1200.0         # 无新事件多久判离线（无心跳时的保守回退）
SESSION_QUIET = 900.0        # 长任务保持状态，不再 45 秒误判空闲
                            # （宿主 Stop 未触发/回合未结束时不把桌宠钉死）


def default_dir():
    return Path(os.environ.get("IVEN_BRIDGE_DIR")
                or Path.home() / ".iven-pet" / "events")


def write_event(directory, source, kind, session_id="unknown", turn_id=None,
                task_label=None, summary=None, tool_name=None, severity="info",
                timestamp=None, tool_call_id=None):
    """适配器侧：统一事件原子写入收件箱。失败静默（宿主 Hook 绝不因此报错）。"""
    try:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        event = {
            "version": PROTOCOL_VERSION,
            "event_id": f"{source}-{int(time.time()*1000)}-"
                        f"{os.urandom(4).hex()}",
            "source": source,
            "session_id": str(session_id)[:64] or "unknown",
            "turn_id": str(turn_id)[:64] if turn_id is not None else None,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(
                timespec="milliseconds").replace("+00:00", "Z"),
            "kind": kind,
            "task_label": (str(task_label)[:MAX_LABEL] if task_label else None),
            "summary": (str(summary)[:MAX_SUMMARY] if summary else None),
            "tool_name": (str(tool_name)[:48] if tool_name else None),
            "tool_call_id": (str(tool_call_id)[:64] if tool_call_id else None),
            "severity": severity if severity in ("info", "warn", "error")
            else "info",
        }
        tmp = directory / f"tmp-{os.getpid()}-{os.urandom(4).hex()}.json"
        final = directory / f"{time.time_ns():019d}-{event['event_id']}.json"
        tmp.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, final)
        return final
    except OSError:
        return None


def _parse_ts(value):
    """ISO 8601 → epoch 秒；解析失败返回 None（事件作废）。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        ts = datetime.fromisoformat(text).timestamp()
        return ts if ts < time.time() + 300 else None   # 拒绝未来事件
    except ValueError:
        return None


def _clean_text(value, limit):
    """事件文本进气泡前的一道清洗：去控制字符 + 截断（防御性，文本只作数据）。"""
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", value).strip()
    return cleaned[:limit] if cleaned else None


class Notice:
    """一次性提醒（重要级可打断当前动作/入睡眠队列）。"""

    __slots__ = ("kind", "label", "source")

    def __init__(self, kind, label=None, source=None):
        self.kind = kind
        self.label = label
        self.source = source

    def __repr__(self):
        return f"Notice({self.kind!r}, {self.label!r})"


class _Session:
    __slots__ = ("last_seen", "phase", "label", "source", "tool", "summary")

    def __init__(self, ts):
        self.last_seen = ts
        self.phase = "idle"        # idle | working | waiting
        self.label = None
        self.source = None
        self.tool = None
        self.summary = None


class HostBridge:
    """收件箱消费者 + 归约器。poll() 每 0.5s 左右调用一次（桌宠逻辑步内）。

    mode: None（无会话/离线，普通轮播）| "working" | "waiting"
    label: 最近一次 task_label（可 None）
    """

    def __init__(self, directory=None, enabled=True, clock=time.time):
        self.dir = Path(directory) if directory else default_dir()
        self.enabled = enabled
        self._clock = clock
        self.mode = None
        self.label = None
        self.source = None
        self.detail = None
        self.sessions = {}          # session_id -> _Session
        self._seen = {}             # event_id -> epoch（有界去重）
        self._last_event_ts = None

    # ---------- 消费 ----------
    def poll(self):
        """读收件箱 → 应用事件 → 返回本轮 Notice 列表。目录不存在=无宿主。"""
        notices = []
        if not self.enabled:
            return notices
        now = self._clock()
        events = self._load(now)
        for ev in events:
            self._apply(ev, notices)
        self._gc(now)
        self._recompute_mode()
        return notices

    def _load(self, now):
        try:
            names = sorted(os.listdir(self.dir))
        except OSError:
            return []
        names = [n for n in names if n.endswith(".json")]
        if len(names) > MAX_BACKLOG:                    # 丢弃最旧的积压
            for stale in names[:len(names) - MAX_BACKLOG]:
                self._discard(stale)
            names = names[-MAX_BACKLOG:]
        events = []
        for name in names[:MAX_EVENTS_PER_POLL]:
            try:
                raw = json.loads((self.dir / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._discard(name)
                continue
            if not isinstance(raw, dict):
                self._discard(name)
                continue
            ts = _parse_ts(raw.get("timestamp"))
            eid = raw.get("event_id")
            if (not isinstance(raw, dict) or raw.get("version") != PROTOCOL_VERSION
                    or raw.get("kind") not in KINDS or ts is None
                    or not isinstance(eid, str) or now - ts > EVENT_MAX_AGE):
                self._discard(name)
                continue
            if eid in self._seen:                       # 去重（适配器可能重发）
                self._discard(name)
                continue
            self._seen[eid] = ts
            raw["_ts"] = ts
            events.append((name, raw))
        for _, ev in events:                            # 消费成功才删除
            self._last_event_ts = max(self._last_event_ts or 0, ev["_ts"])
        for name, _ in events:
            self._discard(name)
        return [ev for _, ev in events]

    def _discard(self, name):
        try:
            os.unlink(self.dir / name)
        except OSError:
            pass

    # ---------- 归约 ----------
    def _apply(self, ev, notices):
        kind = ev["kind"]
        sid = ev.get("session_id") or "unknown"
        sess = self.sessions.get(sid)
        if sess is None:
            if kind in ("session.ended",):
                return
            sess = self.sessions[sid] = _Session(ev["_ts"])
            if kind != "session.started":
                notices.append(Notice("session.started"))
        sess.last_seen = ev["_ts"]
        sess.source = _clean_text(ev.get("source"), 32) or sess.source
        label = _clean_text(ev.get("task_label"), MAX_LABEL)
        summary = _clean_text(ev.get("summary"), MAX_SUMMARY)
        tool = _clean_text(ev.get("tool_name"), 48)
        if kind == "turn.started":
            sess.label, sess.tool, sess.summary = None, None, None
        if tool:
            sess.tool = tool
        if summary:
            sess.summary = summary
        if label:
            sess.label = label
            self.label = label

        if kind in ("turn.started", "tool.started"):
            sess.phase = "working"
        elif kind == "permission.required":
            sess.phase = "waiting"
            notices.append(Notice("permission.required", sess.label
                                  or _clean_text(ev.get("tool_name"), 48)))
        elif kind in ("tool.finished", "tool.failed"):
            # 审批已通过、宿主继续跑：等待结束，回到工作（失败只闪一个片段）
            if sess.phase == "waiting":
                sess.phase = "working"
            if kind == "tool.failed":
                notices.append(Notice("tool.failed", sess.label))
        elif kind == "turn.ended":
            sess.phase = "idle"
            notices.append(Notice("turn.ended", summary or sess.summary or sess.label, sess.source))
        elif kind == "turn.failed":
            sess.phase = "idle"
            notices.append(Notice("turn.failed", sess.label
                                  or _clean_text(ev.get("summary"), MAX_SUMMARY)))
        elif kind == "task.completed":
            sess.phase = "idle"
            notices.append(Notice("task.completed", summary or sess.summary or sess.label, sess.source))
        elif kind in ("interrupted", "session.ended"):
            self.sessions.pop(sid, None)
        # session.started / tool.finished：无可见状态变化

    def _gc(self, now):
        # 去重表有界（防长会话内存增长）
        if len(self._seen) > 4096:
            horizon = sorted(self._seen.values())[-2048:]
            floor = horizon[0] if horizon else 0
            self._seen = {k: v for k, v in self._seen.items() if v >= floor}
        # 断线回退：太久没有任何新事件 → 全部会话清空（静默）
        if (self._last_event_ts is not None
                and now - self._last_event_ts > STALE_AFTER):
            self.sessions.clear()
            self._last_event_ts = None
            return
        # 单会话静默退 idle：宿主 Stop 未触发/回合没结束时，别把桌宠钉死
        for sess in self.sessions.values():
            if sess.phase != "idle" and now - sess.last_seen > SESSION_QUIET:
                sess.phase = "idle"

    def _recompute_mode(self):
        active = [s for s in self.sessions.values() if s.phase in ("working", "waiting")]
        if active:
            current = max(active, key=lambda s: (s.phase == "waiting", s.last_seen))
            self.mode, self.label = current.phase, current.label
            self.source, self.detail = current.source, current.tool
        else:
            self.mode = None
            current = max(self.sessions.values(), key=lambda s: s.last_seen, default=None)
            self.label = current.label if current else None
            self.source = current.source if current else None
            self.detail = None
