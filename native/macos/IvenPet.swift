import AppKit
import QuartzCore
import Darwin

let playbackSpeed = 0.75

struct Clip: Decodable {
    let frames: [String]
    let durations: [Int]
    var total: Int { durations.reduce(0, +) }
    func frame(at milliseconds: Int) -> String {
        var phase = max(0, milliseconds) % total
        for (name, duration) in zip(frames, durations) {
            if phase < duration { return name }
            phase -= duration
        }
        return frames.last!
    }
}
struct Manifest: Decodable { let version: Int; let clips: [String: Clip] }

func draggedOrigin(start: NSPoint, pointerStart: NSPoint, pointer: NSPoint) -> NSPoint {
    // Cocoa screen coordinates increase upward; never mix them with Tk's y-down coordinates.
    NSPoint(x: start.x + pointer.x - pointerStart.x,
            y: start.y + pointer.y - pointerStart.y)
}

func statusCardPlacement(pet: NSRect, screen: NSRect, card: NSSize) -> (pet: NSPoint, bubble: NSPoint) {
    let origin = NSPoint(x:pet.minX,y:min(pet.minY,screen.maxY-card.height-156))
    let x = min(screen.maxX-card.width-8,max(screen.minX+8,pet.midX-card.width/2))
    return (origin,NSPoint(x:x,y:max(screen.minY+8,origin.y+148)))
}

final class PetPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class PetView: NSView {
    weak var owner: PetController?
    private var pointerStart = NSPoint.zero
    private var originStart = NSPoint.zero
    private var moved = false
    private var doubleClick = false
    override var isOpaque: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with event: NSEvent) {
        if event.modifierFlags.contains(.control) { rightMouseDown(with: event); return }
        guard let window, let owner else { return }
        pointerStart = NSEvent.mouseLocation
        originStart = window.frame.origin
        moved = false
        doubleClick = event.clickCount >= 2
        owner.pressed = true
    }
    override func mouseDragged(with event: NSEvent) {
        guard let window, let owner else { return }
        let pointer = NSEvent.mouseLocation
        if hypot(pointer.x-pointerStart.x, pointer.y-pointerStart.y) > 4 {
            if !moved { owner.play("GRAB", mode: "DRAG", seconds: 0) }
            moved = true
            window.setFrameOrigin(draggedOrigin(start: originStart, pointerStart: pointerStart, pointer: pointer))
        }
    }
    override func mouseUp(with event: NSEvent) {
        guard let owner else { return }
        owner.pressed = false
        if moved {
            owner.velocity = 0
            owner.play(owner.pinned ? "IDLE" : "FALL", mode: owner.pinned ? "IDLE" : "FALL", seconds: owner.pinned ? 6 : 0)
        }
        else { owner.perform(doubleClick ? "HAPPY" : "BOUNCE") }
    }
    override func rightMouseDown(with event: NSEvent) {
        guard let owner else { return }
        NSMenu.popUpContextMenu(owner.contextMenu(), with: event, for: self)
    }
    func show(_ image: CGImage) {
        // Replace the complete immutable layer image. No incremental transparent drawing.
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer?.contents = image
        CATransaction.commit()
    }
}

struct ActionDeck {
    private var remaining: [String] = []
    private var last = ""
    mutating func next(available: Set<String>, pinned: Bool) -> String {
        let candidates = ["GREET", "BOUNCE", "CHEER", "SPIN", "WAITING", "WORK", "REVIEW", "FAILED", "STRETCH", "DOZE", "RUBIK"]
            .filter { available.contains($0) } + (pinned ? [] : ["WALK_r", "WALK_l"].filter { available.contains($0) })
        remaining = remaining.filter { candidates.contains($0) }
        if remaining.isEmpty { remaining = candidates.shuffled() }
        if remaining.count > 1 && remaining.last == last { remaining.swapAt(0, remaining.count-1) }
        last = remaining.popLast() ?? "IDLE"
        return last
    }
}

// MARK: - 宿主桥接（收件箱消费者，语义与 host_bridge.py 一致）
// Stop/turn.ended 只是"本轮结束"，绝不当作任务成功；事件文本只作数据展示。
struct BridgeNotice { let kind: String; let label: String? }

final class HostBridge {
    static let kinds: Set<String> = ["session.started","turn.started","tool.started",
        "permission.required","tool.finished","tool.failed","turn.ended","turn.failed",
        "task.completed","task.updated","interrupted","session.ended"]
    static let staleAfter = 1200.0
    static let eventMaxAge = 180.0
    static let sessionQuiet = 900.0   // 单会话 working/waiting 静默多久退回 idle
    static let maxPerPoll = 64
    static let maxBacklog = 500

    let dir: URL
    private var clock: () -> TimeInterval
    private var sessions: [String: (phase: String, label: String?, lastSeen: TimeInterval, source: String?, tool: String?, summary: String?, order: Int)] = [:]
    private var seen: [String: TimeInterval] = [:]
    private var lastEventTs: TimeInterval?
    private var eventOrder = 0
    private(set) var mode: String?        // nil | "working" | "waiting"
    private(set) var label: String?
    private(set) var source: String?
    private(set) var detail: String?
    var activeSources: [String] {
        Array(Set(sessions.values.filter { $0.phase == "working" || $0.phase == "waiting" }.compactMap { $0.source })).sorted()
    }

    init(directory: URL? = nil, clock: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 }) {
        if let directory { dir = directory }
        else if let env = ProcessInfo.processInfo.environment["IVEN_BRIDGE_DIR"] { dir = URL(fileURLWithPath: env) }
        else { dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".iven-pet/events") }
        self.clock = clock
    }

    private static func parseTimestamp(_ text: Any?) -> TimeInterval? {
        guard let s = text as? String else { return nil }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = iso.date(from: s) { return d.timeIntervalSince1970 }
        let plain = ISO8601DateFormatter()
        if let d = plain.date(from: s) { return d.timeIntervalSince1970 }
        return nil
    }

    static func cleanText(_ value: Any?, limit: Int) -> String? {
        guard let s = value as? String else { return nil }
        let cleaned = String(s.map { c in (c >= " " && c != "\u{7f}") ? c : " " }.prefix(limit)).trimmingCharacters(in: .whitespaces)
        return cleaned.isEmpty ? nil : cleaned
    }

    func poll() -> [BridgeNotice] {
        var notices: [BridgeNotice] = []
        let now = clock()
        guard let names0 = try? FileManager.default.contentsOfDirectory(atPath: dir.path) else { return [] }
        var names = names0.filter { $0.hasSuffix(".json") }.sorted()
        if names.count > HostBridge.maxBacklog {
            names.removeFirst(names.count - HostBridge.maxBacklog)
        }
        var consumed: [(URL, [String: Any], TimeInterval)] = []
        for name in names.prefix(HostBridge.maxPerPoll) {
            let url = dir.appendingPathComponent(name)
            guard let data = try? Data(contentsOf: url),
                  let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  obj["version"] as? Int == 1,
                  let kind = obj["kind"] as? String, HostBridge.kinds.contains(kind),
                  let eid = obj["event_id"] as? String,
                  let ts = HostBridge.parseTimestamp(obj["timestamp"]),
                  abs(now - ts) < HostBridge.eventMaxAge else { try? FileManager.default.removeItem(at: url); continue }
            if seen[eid] != nil { try? FileManager.default.removeItem(at: url); continue }
            seen[eid] = ts
            consumed.append((url, obj, ts))
        }
        for (url, obj, ts) in consumed {
            apply(obj, ts: ts, notices: &notices)
            lastEventTs = max(lastEventTs ?? 0, ts)
            try? FileManager.default.removeItem(at: url)
        }
        if seen.count > 4096 {
            let keep = seen.values.sorted().suffix(2048).min() ?? 0
            seen = seen.filter { $0.value >= keep }
        }
        if let last = lastEventTs, now - last > HostBridge.staleAfter {
            sessions.removeAll()          // 断线回退：静默恢复普通轮播
            lastEventTs = nil
        } else {
            // 单会话静默退 idle：宿主 Stop 未触发/回合没结束时，别把桌宠钉死
            for sid in sessions.keys where sessions[sid]!.phase != "idle"
                && now - sessions[sid]!.lastSeen > HostBridge.sessionQuiet {
                sessions[sid]!.phase = "idle"
            }
        }
        recomputeMode()
        return notices
    }

    private func apply(_ obj: [String: Any], ts: TimeInterval, notices: inout [BridgeNotice]) {
        let kind = obj["kind"] as! String
        let sid = (HostBridge.cleanText(obj["source"],limit:32) ?? "unknown")+":"+(obj["session_id"] as? String ?? "unknown").prefix(64).description
        if sessions[sid] == nil {
            if kind == "session.ended" { return }
            sessions[sid] = (phase: "idle", label: nil, lastSeen: ts, source: nil, tool: nil, summary: nil, order: 0)
            if kind != "session.started" { notices.append(BridgeNotice(kind: "session.started", label: nil)) }
        }
        var sess = sessions[sid]!
        eventOrder += 1; sess.order = eventOrder
        sess.lastSeen = ts
        sess.source = HostBridge.cleanText(obj["source"], limit: 32) ?? sess.source
        if kind == "turn.started" { sess.label = nil; sess.tool = nil; sess.summary = nil }
        if let tool = HostBridge.cleanText(obj["tool_name"], limit: 48) { sess.tool = tool }
        if let summary = HostBridge.cleanText(obj["summary"], limit: 160) { sess.summary = summary }
        let label = HostBridge.cleanText(obj["task_label"], limit: 80)
        if let label { sess.label = label; self.label = label }
        switch kind {
        case "turn.started", "tool.started":
            sess.phase = "working"
        case "permission.required":
            sess.phase = "waiting"
            notices.append(BridgeNotice(kind: "permission.required",
                                        label: sess.label ?? HostBridge.cleanText(obj["tool_name"], limit: 48)))
        case "tool.finished":
            if sess.phase == "waiting" { sess.phase = "working" }   // 审批已通过，继续干活
        case "tool.failed":
            if sess.phase == "waiting" { sess.phase = "working" }
            notices.append(BridgeNotice(kind: "tool.failed", label: sess.label))
        case "turn.ended":
            sess.phase = "idle"
            notices.append(BridgeNotice(kind: "turn.ended", label: sess.summary ?? sess.label))
        case "turn.failed":
            sess.phase = "idle"
            notices.append(BridgeNotice(kind: "turn.failed", label: sess.label))
        case "task.completed":
            sess.phase = "idle"
            notices.append(BridgeNotice(kind: "task.completed", label: sess.summary ?? sess.label))
        case "interrupted", "session.ended":
            sessions.removeValue(forKey: sid)
            return
        default: break                    // session.started / tool.finished 无可见变化
        }
        sessions[sid] = sess
    }

    private func recomputeMode() {
        let active = sessions.values.filter { $0.phase == "waiting" || $0.phase == "working" }
        let chosen = active.sorted {
            if ($0.phase == "waiting") != ($1.phase == "waiting") { return $0.phase == "waiting" }
            return $0.lastSeen == $1.lastSeen ? $0.order > $1.order : $0.lastSeen > $1.lastSeen
        }.first ?? sessions.values.max { $0.lastSeen == $1.lastSeen ? $0.order < $1.order : $0.lastSeen < $1.lastSeen }
        mode = active.isEmpty ? nil : chosen?.phase
        label = chosen?.label
        source = chosen?.source
        detail = active.isEmpty ? nil : chosen?.tool
    }

}

final class PetController: NSObject, NSApplicationDelegate {
    var panel: PetPanel!
    var view: PetView!
    var pressed = false
    var pinned = UserDefaults.standard.bool(forKey:"Pinned")
    var velocity: CGFloat = 0
    private var clips: [String: Clip]
    private var images: [String: CGImage] = [:]
    private var timer: Timer?
    private var mode = "FALL"
    private var clipName = "FALL"
    private var clipStart = ProcessInfo.processInfo.systemUptime
    private var deadline: TimeInterval = 0
    private var previous = ProcessInfo.processInfo.systemUptime
    private var shown = ""
    private var direction: CGFloat = 1
    private var speed: CGFloat = 50
    private var deck = ActionDeck()
    private var autoplay = UserDefaults.standard.object(forKey:"Autoplay") as? Bool ?? true
    // 宿主桥接
    private var bridge = HostBridge()
    private var bridgeFrame = 0
    private var manualUntil: TimeInterval = 0        // 手动点播的宿主抑制窗口
    private var sleepQueue: [BridgeNotice] = []      // 睡眠期间的重要提醒
    private var labelShown: String?
    private var followPanel: NSPanel?
    private var followText: NSTextField?
    private var followDot: CALayer?
    private var followKey = ""
    private var bubblePanel: NSPanel?
    private var bubbleTitle: NSTextField?
    private var bubbleBody: NSTextField?
    private var bubbleCard: CALayer?
    private var bubbleDot: CALayer?
    private var bubbleTail: CAShapeLayer?
    private var bubbleKey = ""
    private var bubbleIsHost = false
    private var bubbleHideAt: TimeInterval = 0
    private let bridgeZh = (Locale.current.language.languageCode?.identifier == "zh")

    private func advance() {
        if let hostMode = bridge.mode, hostAvailable(hostMode), !hostSuppressed() {
            if hostMode == "waiting" {
                play("WAITING", mode: "HOST", seconds: 0)
            } else if clipName == "WORK" && mode == "HOST" {
                // 工作不无限连打板：打一轮板喘口气，到点再打
                play("IDLE", mode: "HOST", seconds: Double.random(in: 1.2...2.2))
            } else {
                play("WORK", mode: "HOST", seconds: Double(clips["WORK"]!.total)/1000)
            }
            return
        }
        if mode != "IDLE" || !autoplay {
            play("IDLE",mode:"IDLE",seconds:Double.random(in:3...6))
            return
        }
        let action = deck.next(available:Set(clips.keys),pinned:pinned)
        if action.hasPrefix("WALK_") {
            direction = action == "WALK_r" ? 1 : -1
            speed = 50
            play(action,mode:"WALK",seconds:Double.random(in:3...5))
        } else {
            play(action,mode:"ACTION",seconds:Double(clips[action]!.total)/1000)
        }
    }

    // ---------- 宿主桥接 ----------
    private func hostAvailable(_ hostMode: String) -> Bool {
        clips[hostMode == "waiting" ? "WAITING" : "WORK"] != nil
    }
    private func hostSuppressed() -> Bool {
        let now = ProcessInfo.processInfo.systemUptime
        return pressed || mode == "DRAG" || mode == "FALL" || mode == "SLEEP" || now < manualUntil
    }
    private func hostTick() {
        bridgeFrame += 1
        if bridgeFrame >= 60 {                       // 每秒轮询一次收件箱
            bridgeFrame = 0
            for notice in bridge.poll() { handleNotice(notice) }
        }
        hostAssert()
    }
    private func hostAssert() {
        if bridge.mode == nil {
            if mode == "HOST" { play("IDLE",mode:"IDLE",seconds:3) }
            labelShown = nil
            if bubbleIsHost { bubblePanel?.orderOut(nil); bubbleKey = ""; bubbleIsHost = false }
            return
        }
        guard hostAvailable(bridge.mode!), !hostSuppressed() else {
            if bubbleIsHost { bubblePanel?.orderOut(nil); bubbleKey = "" }
            return
        }
        updateHostBubble()
        if mode == "HOST" {
            // 已在宿主模式：打板/喘气节奏交给 advance()，只在切等待时立即接管
            if bridge.mode == "waiting" && clipName != "WAITING" {
                play("WAITING", mode: "HOST", seconds: 0)
            }
            return
        }
        if bridge.mode == "waiting" {
            play("WAITING", mode: "HOST", seconds: 0)
        } else {
            play("WORK", mode: "HOST", seconds: Double(clips["WORK"]!.total)/1000)

        }
    }
    private func handleNotice(_ n: BridgeNotice) {
        if mode == "SLEEP" {
            if ["permission.required","turn.failed","task.completed"].contains(n.kind),
               sleepQueue.count < 3 { sleepQueue.append(n) }
            return
        }
        guard !hostSuppressed() else { return }
        switch n.kind {
        case "permission.required":
            if clips["WAITING"] != nil {
                play("WAITING", mode: "HOST", seconds: 0)
                updateHostBubble()
            }
        case "tool.failed":
            if bridge.mode == "working", let clip = clips["FAILED"] {
                play("FAILED", mode: "ACTION", seconds: Double(clip.total)/1000)
            }
        case "turn.failed":
            if let clip = clips["FAILED"] { play("FAILED", mode: "ACTION", seconds: Double(clip.total)/1000) }
            showBubble(n.label.map { bridgeZh ? "出问题了：\($0)" : "Failed: \($0)" }
                       ?? (bridgeZh ? "出问题了…" : "Something failed…"), seconds: 6, title: hostName()+" · "+(bridgeZh ? "遇到问题" : "Needs attention"), tone: "error")
        case "task.completed":
            let pick = clips["CHEER"] != nil ? "CHEER" : (clips["HAPPY"] != nil ? "HAPPY" : nil)
            if let pick {
                manualUntil = ProcessInfo.processInfo.systemUptime + Double(clips[pick]!.total)/1000 + 1.5
                play(pick, mode: "ACTION", seconds: Double(clips[pick]!.total)/1000 + 1.0)
            }
            showBubble(n.label ?? (bridgeZh ? "任务已完成" : "Task completed"), seconds: 7, title: hostName()+" · "+(bridgeZh ? "任务完成" : "Completed"), tone: "done")
        case "turn.ended":
            if mode == "HOST" { play("IDLE", mode: "IDLE", seconds: 3) }
            showBubble(n.label ?? (bridgeZh ? "已回复，随时继续" : "Ready when you are"), seconds: 7,
                       title: hostName()+" · "+(bridgeZh ? "本轮回复结束" : "Reply finished"), tone: "done")
        default: break
        }
    }
    private func flushSleepQueue() {
        guard mode != "SLEEP", !sleepQueue.isEmpty else { return }
        let pending = sleepQueue.removeLast()
        sleepQueue.removeAll()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { [weak self] in
            self?.handleNotice(pending)
        }
    }
    private func updateFollowingBadge() {
        guard let panel else { return }
        if followPanel == nil {
            let badge = NSPanel(contentRect:NSRect(x:0,y:0,width:160,height:25),
                                styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
            badge.isOpaque = false; badge.backgroundColor = .clear; badge.hasShadow = false
            badge.ignoresMouseEvents = true; badge.level = .floating; badge.hidesOnDeactivate = false
            badge.collectionBehavior = [.canJoinAllSpaces,.fullScreenAuxiliary]
            badge.title = "Iven · 当前跟随"
            let content = NSView(); content.wantsLayer = true
            content.layer?.cornerRadius = 12
            content.layer?.backgroundColor = NSColor(calibratedWhite:0.985,alpha:0.95).cgColor
            content.layer?.borderWidth = 0.6
            content.layer?.borderColor = NSColor(calibratedWhite:0.8,alpha:0.8).cgColor
            badge.contentView = content
            let dot = CALayer(); dot.frame = CGRect(x:10,y:9,width:6,height:6); dot.cornerRadius = 3
            content.layer?.addSublayer(dot); followDot = dot
            let field = NSTextField(labelWithString:""); field.font = .systemFont(ofSize:10.5,weight:.medium)
            field.textColor = NSColor(calibratedWhite:0.28,alpha:1)
            content.addSubview(field); followText = field; followPanel = badge
        }
        var text = bridgeZh ? "独立模式" : "Standalone"
        var color = NSColor.systemGray
        if let source = bridge.source {
            text = (bridge.mode == nil ? (bridgeZh ? "最近 · " : "Last · ") : (bridgeZh ? "跟随 · " : "Following · "))+hostName()
            let others = max(0,bridge.activeSources.count-1)
            if bridge.mode != nil && others > 0 { text += "  +\(others)" }
            let colors: [String:NSColor] = ["zcode":.systemPurple,"dsh":.systemBlue,"codex":.systemTeal,
                                           "claude-code":.systemOrange,"cursor":.darkGray,"opencode":.systemIndigo]
            color = colors[source] ?? .systemGray
        }
        if followKey != text {
            followKey = text
            let width = max(98,min(196,(text as NSString).size(withAttributes:[.font:NSFont.systemFont(ofSize:10.5,weight:.medium)]).width+32))
            followPanel?.setContentSize(NSSize(width:width,height:25))
            followText?.stringValue = text
            followText?.frame = CGRect(x:22,y:4,width:width-29,height:17)
            followDot?.backgroundColor = color.cgColor
        }
        let screen = screenFrame(), width = followPanel!.frame.width
        // A compact nameplate beside the feet; never covers the face or task card.
        let preferred = panel.frame.midX+50
        let x = preferred+width <= screen.maxX-8 ? preferred : panel.frame.midX-50-width
        followPanel?.setFrameOrigin(NSPoint(x:max(screen.minX+8,min(screen.maxX-width-8,x)),
                                           y:max(screen.minY+5,min(screen.maxY-30,panel.frame.minY+16))))
        if followPanel?.isVisible != true { followPanel?.orderFrontRegardless() }
    }
    private func hostName() -> String {
        let names = ["zcode":"ZCode", "dsh":"DSH", "claude-code":"Claude Code",
                     "codex":"Codex", "cursor":"Cursor", "opencode":"OpenCode"]
        return names[bridge.source ?? ""] ?? bridge.source ?? (bridgeZh ? "编码助手" : "Coding agent")
    }
    private func updateHostBubble() {
        guard let state = bridge.mode else { return }
        // Let a result/error card finish before resuming persistent status.
        let now = ProcessInfo.processInfo.systemUptime
        if !bubbleIsHost && bubbleHideAt > now && bubblePanel?.isVisible == true { return }
        let title = hostName()+" · "+(state == "waiting" ? (bridgeZh ? "等你确认" : "Needs approval") : (bridgeZh ? "工作中" : "Working"))
        var lines: [String] = []
        if let task = bridge.label { lines.append(task) }
        if let tool = bridge.detail {
            let parts = tool.components(separatedBy:" · ")
            let names = ["Read":"读取文件", "read_file":"读取文件", "Bash":"运行命令", "shell":"运行命令",
                         "run_shell_command":"运行命令", "Edit":"修改文件", "Write":"写入文件", "Grep":"搜索代码", "Glob":"查找文件", "Task":"处理子任务"]
            let activity = (names[parts[0]] ?? parts[0]) + (parts.count > 1 ? " · "+parts.dropFirst().joined(separator:" · ") : "")
            lines.append(bridgeZh ? "当前步骤 · "+activity : "Current tool · "+tool)
        }
        if lines.isEmpty { lines.append(state == "waiting" ? (bridgeZh ? "请在原应用中确认后继续" : "Continue in your coding app") : (bridgeZh ? "正在处理你的任务…" : "Processing your task…")) }
        showBubble(lines.joined(separator:"\n"),seconds:0,title:title,tone:state,persistent:true)
    }
    private func positionBubble() {
        guard let bubblePanel, bubblePanel.isVisible, let panel else { return }
        let screen = screenFrame()
        let width = bubblePanel.frame.width, height = bubblePanel.frame.height
        let layout = statusCardPlacement(pet:panel.frame,screen:screen,card:NSSize(width:width,height:height))
        if !pressed { panel.setFrameOrigin(layout.pet) }
        bubblePanel.setFrameOrigin(layout.bubble)
        let tailX = min(width-20,max(20,panel.frame.midX-layout.bubble.x))
        let triangle = CGMutablePath(); triangle.move(to:CGPoint(x:tailX-7,y:9))
        triangle.addLine(to:CGPoint(x:tailX,y:1)); triangle.addLine(to:CGPoint(x:tailX+7,y:9)); triangle.closeSubpath()
        bubbleTail?.path = triangle
    }
    private func showBubble(_ text: String, seconds: Double, title: String? = nil,
                            tone: String = "info", persistent: Bool = false) {
        let heading = title ?? hostName()
        let body = String(text.prefix(160))
        let key = heading+"|"+body+"|"+tone
        if persistent && bubbleIsHost && bubbleKey == key && bubblePanel?.isVisible == true { return }
        if bubblePanel == nil {
            let card = NSPanel(contentRect:NSRect(x:0,y:0,width:286,height:100),
                               styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
            card.isOpaque = false; card.backgroundColor = .clear; card.hasShadow = true
            card.level = .floating; card.ignoresMouseEvents = true; card.hidesOnDeactivate = false
            card.collectionBehavior = [.canJoinAllSpaces,.fullScreenAuxiliary]
            card.title = "Iven · 任务状态"
            let content = NSView(); content.wantsLayer = true; content.layer?.backgroundColor = NSColor.clear.cgColor
            card.contentView = content
            let background = CALayer(); background.cornerRadius = 14
            background.backgroundColor = NSColor(calibratedWhite:0.985,alpha:0.98).cgColor
            background.borderColor = NSColor(calibratedRed:0.79,green:0.77,blue:0.85,alpha:0.8).cgColor
            background.borderWidth = 0.7; content.layer?.addSublayer(background); bubbleCard = background
            let tail = CAShapeLayer(); tail.fillColor = background.backgroundColor
            content.layer?.addSublayer(tail); bubbleTail = tail
            let dot = CALayer(); dot.cornerRadius = 3; content.layer?.addSublayer(dot); bubbleDot = dot
            let header = NSTextField(labelWithString:""); header.font = .systemFont(ofSize:11,weight:.semibold)
            header.textColor = NSColor(calibratedRed:0.39,green:0.34,blue:0.48,alpha:1)
            content.addSubview(header); bubbleTitle = header
            let message = NSTextField(wrappingLabelWithString:""); message.font = .systemFont(ofSize:12)
            message.textColor = NSColor(calibratedWhite:0.19,alpha:1); message.maximumNumberOfLines = 4
            message.lineBreakMode = .byWordWrapping; content.addSubview(message); bubbleBody = message
            bubblePanel = card
        }
        let font = NSFont.systemFont(ofSize:12)
        let paragraph = NSMutableParagraphStyle(); paragraph.lineBreakMode = .byWordWrapping; paragraph.lineSpacing = 3
        let attributes: [NSAttributedString.Key:Any] = [.font:font,.paragraphStyle:paragraph]
        let measured = (body as NSString).boundingRect(with:NSSize(width:250,height:1000),options:[.usesLineFragmentOrigin,.usesFontLeading],attributes:attributes).height
        let bodyHeight = min(76,max(18,ceil(measured)+3)), height = bodyHeight+52
        bubblePanel?.setContentSize(NSSize(width:286,height:height))
        bubbleCard?.frame = CGRect(x:0,y:8,width:286,height:height-8)
        let triangle = CGMutablePath(); triangle.move(to:CGPoint(x:136,y:9))
        triangle.addLine(to:CGPoint(x:143,y:1)); triangle.addLine(to:CGPoint(x:150,y:9)); triangle.closeSubpath()
        bubbleTail?.path = triangle
        bubbleTitle?.stringValue = heading
        bubbleTitle?.frame = CGRect(x:28,y:height-33,width:242,height:17)
        bubbleBody?.attributedStringValue = NSAttributedString(string:body,attributes:attributes)
        bubbleBody?.frame = CGRect(x:18,y:19,width:250,height:bodyHeight)
        bubbleDot?.frame = CGRect(x:16,y:height-26,width:6,height:6)
        bubbleDot?.backgroundColor = (tone == "waiting" ? NSColor.systemOrange : tone == "done" ? NSColor.systemGreen : tone == "error" ? NSColor.systemRed : NSColor.systemPurple).cgColor
        bubbleIsHost = persistent; bubbleKey = key
        bubbleHideAt = persistent ? 0 : ProcessInfo.processInfo.systemUptime+seconds
        bubblePanel?.orderFrontRegardless(); positionBubble()
        if ProcessInfo.processInfo.environment["IVEN_BRIDGE_DEBUG"] == "1", !persistent || bubbleKey == key {
            if let id = bubblePanel?.windowNumber { print("[status-card] window=\(id)"); fflush(stdout) }
        }
    }

    init(directory: URL) throws {
        let manifest = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: directory.appendingPathComponent("animation.json")))
        guard manifest.version == 1 else { throw NSError(domain:"IvenPet",code:1,userInfo:[NSLocalizedDescriptionKey:"Unsupported animation manifest"]) }
        clips = manifest.clips
        super.init()
        for (state, clip) in clips {
            guard !clip.frames.isEmpty, clip.frames.count == clip.durations.count,
                  clip.durations.allSatisfy({ $0 > 0 }) else {
                throw NSError(domain:"IvenPet",code:2,userInfo:[NSLocalizedDescriptionKey:"Invalid clip: \(state)"])
            }
        }
        clips["FALL"] = Clip(frames:["fall_0"],durations:[1000])
        clips["LAND"] = Clip(frames:["land_0"],durations:[350])
        for name in Set(clips.values.flatMap { $0.frames }) {
            let path = directory.appendingPathComponent(name+".png")
            guard let source = NSImage(contentsOf: path),
                  let image = source.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                throw NSError(domain:"IvenPet",code:3,userInfo:[NSLocalizedDescriptionKey:"Missing transparent PNG: \(path.path)"])
            }
            images[name] = image
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main!.visibleFrame
        panel = PetPanel(contentRect: NSRect(x:screen.maxX-320,y:screen.maxY-240,width:200,height:200),
                         styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
        panel.title = "Iven Pet · 独立桌宠"
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces,.fullScreenAuxiliary]
        view = PetView(frame:NSRect(x:0,y:0,width:200,height:200))
        view.owner = self
        view.wantsLayer = true
        view.layer = CALayer()
        view.layer?.backgroundColor = NSColor.clear.cgColor
        view.layer?.isOpaque = false
        view.layer?.contentsGravity = .resizeAspect
        panel.contentView = view
        panel.orderFrontRegardless()
        // A pinned pet must start idle; FALL has no deadline and suppresses host UI.
        play(pinned ? "IDLE" : "FALL",mode:pinned ? "IDLE" : "FALL",seconds:pinned ? 4 : 0)
        previous = ProcessInfo.processInfo.systemUptime
        timer = Timer(timeInterval:1.0/60.0,target:self,selector:#selector(tick),userInfo:nil,repeats:true)
        RunLoop.main.add(timer!, forMode:.common)
        print("[start] native AppKit | transparent CALayer | \(images.count) PNG frames | drag uses Cocoa screen coordinates | bridge=\(bridge.dir.path)")
        fflush(stdout)
    }

    private func screenFrame() -> NSRect {
        let point = NSPoint(x:panel.frame.midX,y:panel.frame.midY)
        return (NSScreen.screens.first { $0.frame.contains(point) } ?? NSScreen.main!).visibleFrame
    }
    func play(_ name: String, mode newMode: String, seconds: TimeInterval) {
        guard let clip = clips[name] else { return }
        mode = newMode
        clipName = name
        clipStart = ProcessInfo.processInfo.systemUptime
        deadline = seconds > 0 ? clipStart + seconds / playbackSpeed : 0
        shown = ""
        view?.show(images[clip.frames[0]]!)
    }
    @objc private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        let dt = min(0.05,max(0,now-previous)) * playbackSpeed
        previous = now
        hostTick()
        if bubbleHideAt > 0 && now >= bubbleHideAt {
            bubblePanel?.orderOut(nil); bubbleHideAt = 0; bubbleKey = ""
        }
        positionBubble()
        if !pressed {
            var origin = panel.frame.origin
            let screen = screenFrame()
            let floor = screen.minY - 7 // PNG foot baseline 193 in a 200-point window.
            if pinned {
                if deadline > 0 && now >= deadline { advance() }
            } else if mode == "FALL" {
                velocity += CGFloat(dt)*1200
                origin.y -= velocity*CGFloat(dt)
                if origin.y <= floor {
                    origin.y = floor
                    velocity = 0
                    play("LAND",mode:"ACTION",seconds:0.35)
                }
            } else if mode != "DRAG" {
                if origin.y > floor+2 {
                    velocity = 0
                    play("FALL",mode:"FALL",seconds:0)
                } else {
                    origin.y = floor
                    if mode == "WALK" {
                        origin.x += direction*speed*CGFloat(dt)
                        if origin.x < screen.minX || origin.x > screen.maxX-200 {
                            origin.x = min(screen.maxX-200,max(screen.minX,origin.x))
                            direction *= -1
                            play(direction > 0 ? "WALK_r" : "WALK_l",mode:"WALK",seconds:5)
                        }
                    }
                    if deadline > 0 && now >= deadline {
                        advance()
                    }
                }
            }
            panel.setFrameOrigin(origin)
        }
        updateFollowingBadge()
        let frame = clips[clipName]!.frame(at:Int((now-clipStart)*1000*playbackSpeed))
        if frame != shown {
            shown = frame
            view.show(images[frame]!)
        }
    }
    func perform(_ action: String) {
        pressed = false
        if action == "QUIT" { NSApp.terminate(nil); return }
        if mode == "SLEEP" && action != "SLEEP" { flushSleepQueue() }
        if action == "AUTOPLAY" {
            autoplay.toggle()
            UserDefaults.standard.set(autoplay,forKey:"Autoplay")
            if mode != "SLEEP" && mode != "FALL" { play("IDLE",mode:"IDLE",seconds:4) }
            return
        }
        if action == "PIN" {
            pinned.toggle()
            UserDefaults.standard.set(pinned,forKey:"Pinned")
            velocity = 0
            play(pinned ? "IDLE" : "FALL",mode:pinned ? "IDLE" : "FALL",seconds:pinned ? 6 : 0)
            return
        }
        if action == "RUN" {
            direction = Bool.random() ? 1 : -1
            speed = 90
            manualUntil = ProcessInfo.processInfo.systemUptime + 7
            play(direction > 0 ? "RUN_r" : "RUN_l",mode:"WALK",seconds:6)
        } else if action == "SLEEP" { play("SLEEP",mode:"SLEEP",seconds:0) }
        else if action == "IDLE" { play("IDLE",mode:"IDLE",seconds:6) }
        else if let clip = clips[action] {
            manualUntil = ProcessInfo.processInfo.systemUptime + Double(clip.total)/1000 + 1.0
            play(action,mode:"ACTION",seconds:Double(clip.total)/1000)
        }
    }
    @objc private func menuAction(_ item: NSMenuItem) { perform(item.representedObject as! String) }
    func contextMenu() -> NSMenu {
        let menu = NSMenu()
        let heading = NSMenuItem(title:"Iven Pet · 独立桌宠",action:nil,keyEquivalent:"")
        heading.isEnabled = false
        menu.addItem(heading)
        menu.addItem(.separator())
        let pin = NSMenuItem(title:"固定在当前位置",action:#selector(menuAction),keyEquivalent:"")
        pin.target = self
        pin.representedObject = "PIN"
        pin.state = pinned ? .on : .off
        menu.addItem(pin)
        let auto = NSMenuItem(title:"自动轮播动作",action:#selector(menuAction),keyEquivalent:"")
        auto.target = self
        auto.representedObject = "AUTOPLAY"
        auto.state = autoplay ? .on : .off
        menu.addItem(auto)
        for (title,action) in [("伸懒腰","STRETCH"),("打瞌睡","DOZE"),("玩魔方","RUBIK"),("等待","WAITING"),("工作","WORK"),("检查","REVIEW"),("失落","FAILED"),("挥手打招呼","GREET"),("弹跳","BOUNCE"),("开心","HAPPY"),
                               ("打板","CHEER"),("观察四周","SPIN"),("小跳快走","RUN"),
                               ("害羞","SHY"),("睡觉","SLEEP"),("唤醒","IDLE"),("退出独立版","QUIT")] {
            let item = NSMenuItem(title:title,action:#selector(menuAction),keyEquivalent:"")
            item.target = self
            item.representedObject = action
            menu.addItem(item)
        }
        return menu
    }
}

if CommandLine.arguments.contains("--self-test") {
    let display = NSRect(x:-800,y:32,width:1440,height:868)
    for x in [display.minX, display.midX, display.maxX-200] {
        for y in [display.minY-7,display.maxY-240,display.maxY-100] {
            for height in [70.0,100.0,128.0] {
                let size = NSSize(width:286,height:height)
                let layout = statusCardPlacement(pet:NSRect(x:x,y:y,width:200,height:200),screen:display,card:size)
                precondition(layout.bubble.y >= layout.pet.y+148, "Status card must remain above the head")
                precondition(layout.bubble.y+height <= display.maxY-8, "Card must fit below top edge")
                precondition(layout.bubble.x >= display.minX+8 && layout.bubble.x+286 <= display.maxX-8, "Card fits side edges")
            }
        }
    }
    let start = NSPoint(x:300,y:100)
    let anchor = NSPoint(x:350,y:150)
    let up = draggedOrigin(start:start,pointerStart:anchor,pointer:NSPoint(x:360,y:450))
    precondition(up == NSPoint(x:310,y:400), "Upward drag must move upward")
    let down = draggedOrigin(start:start,pointerStart:anchor,pointer:NSPoint(x:250,y:50))
    precondition(down == NSPoint(x:200,y:0), "Downward drag delta must not flip")
    let clip = Clip(frames:["a","b","c"],durations:[280,110,320])
    precondition(clip.frame(at:280)=="b" && clip.frame(at:390)=="c" && clip.frame(at:710)=="a")
    var deck = ActionDeck()
    let pool: Set<String> = ["GREET", "BOUNCE", "WALK_r", "WALK_l"]
    let cycle = (0..<4).map { _ in deck.next(available:pool,pinned:false) }
    precondition(Set(cycle) == pool, "Each available action appears once per cycle")
    for _ in 0..<20 { precondition(!deck.next(available:pool,pinned:true).hasPrefix("WALK_")) }
    precondition(deck.next(available:[],pinned:true) == "IDLE")
    // 宿主桥接归约器：主场景重放（与 tests/test_host_bridge.py 同语义）
    do {
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("iven-selftest-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmp) }
        let epoch = 1_800_000_000.0
        var tick = epoch
        let bridge = HostBridge(directory: tmp, clock: { tick })
        var emission = 0
        func emit(_ kind: String, session: String = "s1", label: String? = nil, source: String = "test") throws {
            emission += 1
            let iso = ISO8601DateFormatter()
            let text = """
            {"version":1,"event_id":"\(source)-\(kind)-\(session)-\(emission)","source":"\(source)","session_id":"\(session)","turn_id":null,"timestamp":"\(iso.string(from: Date(timeIntervalSince1970: tick)))","kind":"\(kind)","task_label":\(label.map { "\"\($0)\"" } ?? "null"),"summary":null,"tool_name":null,"severity":"info"}
            """
            try text.write(to: tmp.appendingPathComponent("\(tick)-\(String(format:"%06d",emission))-\(kind).json"), atomically: true, encoding: .utf8)
        }
        try emit("session.started"); try emit("turn.started", label: "运行测试")
        _ = bridge.poll()
        precondition(bridge.mode == "working" && bridge.label == "运行测试", "turn.started → working + label")
        try emit("permission.required")
        let ns = bridge.poll()
        precondition(bridge.mode == "waiting" && ns.contains { $0.kind == "permission.required" }, "permission → waiting + notice")
        tick += 2
        try emit("tool.finished")
        _ = bridge.poll()
        precondition(bridge.mode == "working", "tool.finished after approval → back to working")
        try emit("turn.ended")
        let ns2 = bridge.poll()
        precondition(ns2.contains { $0.kind == "turn.ended" } && !ns2.contains { $0.kind == "task.completed" }, "Stop is not success")
        precondition(bridge.mode == nil, "turn end → back to normal rotation")
        try emit("turn.started", session: "a"); try emit("turn.started", session: "b")
        _ = bridge.poll()
        try emit("turn.ended", session: "a")
        _ = bridge.poll()
        precondition(bridge.mode == "working", "parallel sessions stay working until all end")
        tick += HostBridge.sessionQuiet + 1
        _ = bridge.poll()
        precondition(bridge.mode == nil, "quiet session decays to idle (not pinned)")
        tick += HostBridge.staleAfter + 1
        _ = bridge.poll()
        precondition(bridge.mode == nil, "disconnect falls back silently")
        try emit("turn.started",session:"same",source:"zcode")
        try emit("turn.started",session:"same",source:"dsh")
        _ = bridge.poll()
        precondition(bridge.activeSources == ["dsh","zcode"] && bridge.source == "dsh", "Sources must not collide on a shared session id")
        try emit("permission.required",session:"same",source:"zcode")
        _ = bridge.poll()
        precondition(bridge.source == "zcode", "Badge follows the waiting harness")
        try emit("session.ended",session:"same",source:"zcode")
        _ = bridge.poll()
        precondition(bridge.source == "dsh", "Closing one harness does not clear another")
        let leftovers = (try? FileManager.default.contentsOfDirectory(atPath: tmp.path)) ?? ["<unreadable>"]
        precondition(leftovers.isEmpty, "inbox consumed cleanly")
    } catch {
        fputs("bridge self-test threw: \(error)\n", stderr)
        exit(1)
    }
    print("PASS: upward/downward screen-coordinate drag, timed frame boundaries/wrap, host-bridge reduction")
    exit(0)
}

let lockPath = NSTemporaryDirectory()+"iven-desktop-pet-\(getuid()).lock"
let lockFD = open(lockPath,O_CREAT|O_RDWR,0o600)
if lockFD < 0 || flock(lockFD,LOCK_EX|LOCK_NB) != 0 {
    print("Iven Pet independent app is already running.")
    exit(0)
}
let supplied = CommandLine.arguments.dropFirst().first
let environment = ProcessInfo.processInfo.environment["PET_FRAMES_DIR"]
let resources = Bundle.main.resourceURL?.appendingPathComponent("frames3d")
let fallback = URL(fileURLWithPath:FileManager.default.currentDirectoryPath).appendingPathComponent("frames3d")
let directory = supplied.map { URL(fileURLWithPath:$0) }
    ?? environment.map { URL(fileURLWithPath:$0) }
    ?? ((resources != nil && FileManager.default.fileExists(atPath:resources!.path)) ? resources! : fallback)
do {
    let controller = try PetController(directory:directory)
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    app.delegate = controller
    app.run()
    withExtendedLifetime(controller) {}
} catch {
    fputs("Iven Pet: \(error.localizedDescription)\n",stderr)
    exit(1)
}
