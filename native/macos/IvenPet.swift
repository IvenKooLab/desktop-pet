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
        "task.completed","interrupted","session.ended"]
    static let staleAfter = 120.0
    static let eventMaxAge = 180.0
    static let maxPerPoll = 64
    static let maxBacklog = 500

    let dir: URL
    private var clock: () -> TimeInterval
    private var sessions: [String: (phase: String, label: String?)] = [:]
    private var seen: [String: TimeInterval] = [:]
    private var lastEventTs: TimeInterval?
    private(set) var mode: String?        // nil | "working" | "waiting"
    private(set) var label: String?

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
        }
        recomputeMode()
        return notices
    }

    private func apply(_ obj: [String: Any], ts: TimeInterval, notices: inout [BridgeNotice]) {
        let kind = obj["kind"] as! String
        let sid = (obj["session_id"] as? String ?? "unknown").prefix(64).description
        if sessions[sid] == nil {
            if kind == "session.ended" { return }
            sessions[sid] = (phase: "idle", label: nil)
            if kind != "session.started" { notices.append(BridgeNotice(kind: "session.started", label: nil)) }
        }
        var sess = sessions[sid]!
        let label = HostBridge.cleanText(obj["task_label"], limit: 80)
        if let label { sess.label = label; self.label = label }
        switch kind {
        case "turn.started", "tool.started":
            sess.phase = "working"
        case "permission.required":
            sess.phase = "waiting"
            notices.append(BridgeNotice(kind: "permission.required",
                                        label: sess.label ?? HostBridge.cleanText(obj["tool_name"], limit: 48)))
        case "tool.failed":
            notices.append(BridgeNotice(kind: "tool.failed", label: sess.label))
        case "turn.ended":
            sess.phase = "idle"
            notices.append(BridgeNotice(kind: "turn.ended", label: sess.label))
        case "turn.failed":
            sess.phase = "idle"
            notices.append(BridgeNotice(kind: "turn.failed", label: sess.label))
        case "task.completed":
            sess.phase = "idle"
            notices.append(BridgeNotice(kind: "task.completed", label: sess.label))
        case "interrupted", "session.ended":
            sessions.removeValue(forKey: sid)
            return
        default: break                    // session.started / tool.finished 无可见变化
        }
        sessions[sid] = sess
    }

    private func recomputeMode() {
        let phases = sessions.values.map { $0.phase }
        if phases.contains("waiting") { mode = "waiting" }
        else if phases.contains("working") { mode = "working" }
        else {
            mode = nil
            label = sessions.values.compactMap { $0.label }.first
        }
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
    private var bubbleLayer: CATextLayer?
    private var bubbleHideAt: TimeInterval = 0
    private let bridgeZh = (Locale.current.languageCode == "zh")

    private func advance() {
        if let hostMode = bridge.mode, hostAvailable(hostMode), !hostSuppressed() {
            play(hostMode == "waiting" ? "WAITING" : "WORK", mode: "HOST", seconds: 0)
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
            return
        }
        guard hostAvailable(bridge.mode!), !hostSuppressed() else { return }
        let target = bridge.mode == "waiting" ? "WAITING" : "WORK"
        if clipName != target || mode != "HOST" {
            play(target, mode: "HOST", seconds: 0)
            if target == "WORK", let l = bridge.label, l != labelShown {
                labelShown = l
                showBubble(l, seconds: 2.2)
            }
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
                showBubble(n.label.map { bridgeZh ? "等你确认：\($0)" : "Waiting: \($0)" }
                           ?? (bridgeZh ? "等你确认～" : "Waiting for you~"), seconds: 3.0)
            }
        case "tool.failed":
            if bridge.mode == "working", let clip = clips["FAILED"] {
                play("FAILED", mode: "ACTION", seconds: Double(clip.total)/1000)
            }
        case "turn.failed":
            if let clip = clips["FAILED"] { play("FAILED", mode: "ACTION", seconds: Double(clip.total)/1000) }
            showBubble(n.label.map { bridgeZh ? "出问题了：\($0)" : "Failed: \($0)" }
                       ?? (bridgeZh ? "出问题了…" : "Something failed…"), seconds: 3.0)
        case "task.completed":
            let pick = clips["CHEER"] != nil ? "CHEER" : (clips["HAPPY"] != nil ? "HAPPY" : nil)
            if let pick {
                manualUntil = ProcessInfo.processInfo.systemUptime + Double(clips[pick]!.total)/1000 + 1.5
                play(pick, mode: "ACTION", seconds: Double(clips[pick]!.total)/1000 + 1.0)
            }
            showBubble(bridgeZh ? "任务完成！" : "Task done!", seconds: 2.4)
        case "turn.ended":
            if mode == "HOST" {
                play("IDLE", mode: "IDLE", seconds: 3)
                showBubble(bridgeZh ? "本轮回复结束" : "Turn finished", seconds: 1.8)
            }
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
    private func showBubble(_ text: String, seconds: Double) {
        if bubbleLayer == nil {
            let layer = CATextLayer()
            layer.contentsScale = 2
            layer.cornerRadius = 8
            layer.masksToBounds = true
            layer.backgroundColor = NSColor(calibratedWhite: 1, alpha: 0.94).cgColor
            layer.foregroundColor = NSColor.darkGray.cgColor
            layer.alignmentMode = .center
            layer.fontSize = 12
            layer.font = NSFont.systemFont(ofSize: 12)
            view.layer?.addSublayer(layer)
            bubbleLayer = layer
        }
        let trimmed = String(text.prefix(64))
        bubbleLayer?.string = trimmed
        let width = min(196, max(92, CGFloat(trimmed.count) * 7 + 18))
        bubbleLayer?.frame = CGRect(x: (200-width)/2, y: 158, width: width, height: 30)
        bubbleLayer?.isHidden = false
        bubbleHideAt = ProcessInfo.processInfo.systemUptime + seconds
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
        play("FALL",mode:"FALL",seconds:0)
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
        if let bubble = bubbleLayer, !bubble.isHidden, now >= bubbleHideAt { bubble.isHidden = true }
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
        func emit(_ kind: String, session: String = "s1", label: String? = nil) throws {
            let iso = ISO8601DateFormatter()
            let text = """
            {"version":1,"event_id":"\(kind)-\(session)-\(tick)","source":"test","session_id":"\(session)","turn_id":null,"timestamp":"\(iso.string(from: Date(timeIntervalSince1970: tick)))","kind":"\(kind)","task_label":\(label.map { "\"\($0)\"" } ?? "null"),"summary":null,"tool_name":null,"severity":"info"}
            """
            try text.write(to: tmp.appendingPathComponent("\(tick)-\(kind).json"), atomically: true, encoding: .utf8)
        }
        try emit("session.started"); try emit("turn.started", label: "运行测试")
        _ = bridge.poll()
        precondition(bridge.mode == "working" && bridge.label == "运行测试", "turn.started → working + label")
        try emit("permission.required")
        let ns = bridge.poll()
        precondition(bridge.mode == "waiting" && ns.contains { $0.kind == "permission.required" }, "permission → waiting + notice")
        tick += 2
        try emit("tool.started"); try emit("tool.finished")
        _ = bridge.poll()
        precondition(bridge.mode == "working", "approve → back to working")
        try emit("turn.ended")
        let ns2 = bridge.poll()
        precondition(ns2.contains { $0.kind == "turn.ended" } && !ns2.contains { $0.kind == "task.completed" }, "Stop is not success")
        precondition(bridge.mode == nil, "turn end → back to normal rotation")
        try emit("turn.started", session: "a"); try emit("turn.started", session: "b")
        _ = bridge.poll()
        try emit("turn.ended", session: "a")
        _ = bridge.poll()
        precondition(bridge.mode == "working", "parallel sessions stay working until all end")
        tick += HostBridge.staleAfter + 1
        _ = bridge.poll()
        precondition(bridge.mode == nil, "disconnect falls back silently")
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
