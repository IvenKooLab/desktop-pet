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

struct BehaviorPolicy {
    var idle: ClosedRange<Double> = 3...5
    var walk: ClosedRange<Int> = 5...8
    var actions: [String: ClosedRange<Int>] = Dictionary(uniqueKeysWithValues:
        ["GREET","BOUNCE","HAPPY","SHY","CHEER","WAITING","WORK","REVIEW","FAILED","STRETCH","DOZE","RUBIK"]
            .map { ($0, 4...6) })
    init(directory: URL? = nil) {
        actions["SPIN"] = 2...3
        for name in ["THINKING","IMPATIENT","TOKEN_LOW","RELIEVED"] { actions[name] = 1...1 }
        // 2026-10-23 生活小动作（与 animation_behaviors.py DEFAULT_ACTIONS 同步）
        actions["YAWN"] = 1...1; actions["STOMP"] = 1...1
        actions["CELEBRATE"] = 1...1; actions["SEARCH"] = 1...1
        actions["TRICK_OR_TREAT"] = 1...1
        actions["GHOST_SHEET"] = 1...1
        actions["VAMPIRE_CAPE"] = 1...1; actions["WITCH_SPELL"] = 1...1; actions["BLACK_CAT"] = 1...1
        struct Cycles: Decodable { let cycles: [Int] }
        struct Raw: Decodable {
            let version: Int
            let idle_seconds: [Double]?
            let walk_cycles: [Int]?
            let actions: [String: Cycles]?
        }
        guard let directory, let data = try? Data(contentsOf:directory.appendingPathComponent("animation_behaviors.json")),
              let raw = try? JSONDecoder().decode(Raw.self,from:data), raw.version == 1 else { return }
        if let values = raw.idle_seconds, values.count == 2,
           values[0] > 0, values[0] <= values[1], values[1] <= 30 { idle = values[0]...values[1] }
        if let values = raw.walk_cycles, values.count == 2,
           values[0] > 0, values[0] <= values[1], values[1] <= 16 { walk = values[0]...values[1] }
        for (state, item) in raw.actions ?? [:] {
            let values = item.cycles
            if actions[state] != nil, values.count == 2, values[0] > 0,
               values[0] <= values[1], values[1] <= 16 { actions[state] = values[0]...values[1] }
        }
    }
    func seconds(_ state: String, clip: Clip) -> Double {
        let cycles = state.hasPrefix("WALK_") ? walk : actions[state] ?? 1...1
        return Double(clip.total * Int.random(in:cycles))/1000
    }
}

struct DisplayLease: Codable {
    let version: Int
    let mode: String
    let owner: String
    let lease_until: Double
    var client_id: String?
    func isEmbedded(now: Double) -> Bool {
        version == 1 && mode == "embedded" && owner == "dsh" && lease_until.isFinite
            && now < lease_until && lease_until <= now+90000
    }
    // 两段式租约：请求租约（确认窗口）没有 client_id = 还没有 DSH 网页接手，
    // 桌宠不能藏——否则 dsh 没开时就会白藏一整个租期。
    var isClaimed: Bool {
        if let cid = client_id { return !cid.isEmpty && cid.count <= 128 }
        return false
    }
}
// MARK: - 对话客户端（"和 Comi 说话"，协议见 adapters/dsh/comi-bridge/chat-host.js）
struct ChatReply { let ok: Bool; let text: String; let mood: String?; let reason: String? }
enum ChatClient {
    // 情绪白名单：键与 DSH 插件 chat.js 的 MOODS 对齐，值为桌宠 clip
    static let moodClips = ["happy": "HAPPY", "shy": "SHY", "cheer": "CHEER",
                            "greet": "GREET", "relieved": "RELIEVED"]
    static func cleanText(_ value: Any?, limit: Int) -> String {
        guard let s = value as? String else { return "" }
        let cleaned = String(s.map { c in (c >= " " && c != "\u{7f}") ? c : " " }
                               .prefix(limit)).trimmingCharacters(in: .whitespaces)
        return cleaned
    }
    static func writeRequest(_ dir: URL, text: String, id: String) throws {
        let cleaned = cleanText(text, limit: 2000)
        guard !cleaned.isEmpty else {
            throw NSError(domain: "ComiChat", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "消息为空"])
        }
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let payload: [String: Any] = ["version": 1, "id": id, "text": cleaned]
        let data = try JSONSerialization.data(withJSONObject: payload)
        try data.write(to: dir.appendingPathComponent("request-\(id).json"), options: .atomic)
    }
    static func readReply(_ dir: URL, id: String) -> ChatReply? {
        let path = dir.appendingPathComponent("reply-\(id).json")
        guard let data = try? Data(contentsOf: path),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        try? FileManager.default.removeItem(at: path)      // 读取即消费
        guard (obj["version"] as? Int) == 1, obj["id"] as? String == id else { return nil }
        if (obj["ok"] as? Bool) == true {
            let text = cleanText(obj["text"], limit: 400)
            let mood = obj["mood"] as? String
            return ChatReply(ok: true, text: text.isEmpty ? "……" : text,
                             mood: moodClips[mood ?? ""] != nil ? mood : nil, reason: nil)
        }
        return ChatReply(ok: false, text: "", mood: nil, reason: obj["reason"] as? String)
    }
}

func hostTransitionClip(phase: String, current: String, impatient: Bool) -> String? {
    if phase == "waiting" {
        let target = impatient ? "IMPATIENT" : "WAITING"
        return current == target ? nil : target
    }
    if phase == "working" && ["WAITING","IMPATIENT"].contains(current) { return "WORK" }
    return nil
}
func embeddedDisplayLease(_ path: URL, now: Double) -> DisplayLease? {
    guard let data = try? Data(contentsOf:path), data.count <= 2048,
          let lease = try? JSONDecoder().decode(DisplayLease.self,from:data),
          lease.isEmbedded(now:now) else { return nil }
    return lease
}

func draggedOrigin(start: NSPoint, pointerStart: NSPoint, pointer: NSPoint) -> NSPoint {
    // Cocoa screen coordinates increase upward; never mix them with Tk's y-down coordinates.
    NSPoint(x: start.x + pointer.x - pointerStart.x,
            y: start.y + pointer.y - pointerStart.y)
}

// MARK: - 甩抛物理（与 throw_physics.py 同语义；Cocoa y 向上，重力取负）
// 常量换算一致：G=1200 px/s²、RESTITUTION=0.55、FRICTION=0.72、LAND=260、THROW_MIN=280。
enum ThrowPhysics {
    static let window = 0.12
    static let minSpan = 0.02
    static let maxSpeed: CGFloat = 2600
    static let throwMin: CGFloat = 280
    static let g: CGFloat = 1200
    static let restitution: CGFloat = 0.55
    static let friction: CGFloat = 0.72
    static let landSpeed: CGFloat = 260
    static let maxBounces = 4

    static func estimateVelocity(samples: [(Double, CGFloat, CGFloat)], now: Double) -> (vx: CGFloat, vy: CGFloat)? {
        let usable = samples.filter { now - $0.0 <= window }.sorted { $0.0 < $1.0 }
        guard usable.count >= 2 else { return nil }
        let dt = usable.last!.0 - usable.first!.0
        guard dt >= minSpan else { return nil }
        var vx = (usable.last!.1 - usable.first!.1) / CGFloat(dt)
        var vy = (usable.last!.2 - usable.first!.2) / CGFloat(dt)
        let speed = hypot(vx, vy)
        guard speed > 1e-6 else { return nil }
        if speed > maxSpeed { vx *= maxSpeed/speed; vy *= maxSpeed/speed }
        return (vx, vy)
    }

    /// 推进一投掷步（Cocoa 坐标：y 向上、vy 向上为正）。
    /// floorY 为脚底地面线；返回 (x, y, vx, vy, event)，event ∈ {"fly","bounce","land"}。
    static func step(x: CGFloat, y: CGFloat, vx: CGFloat, vy: CGFloat, dt: Double,
                     minX: CGFloat, maxX: CGFloat, maxY: CGFloat, floorY: CGFloat, size: CGFloat)
        -> (x: CGFloat, y: CGFloat, vx: CGFloat, vy: CGFloat, event: String) {
        guard dt > 0, x.isFinite, y.isFinite, vx.isFinite, vy.isFinite else {
            return (x, y, vx, vy, "fly")
        }
        var nx = x + vx * CGFloat(dt)
        var ny = y + (vy - g * CGFloat(dt)) * CGFloat(dt)
        var nvx = vx, nvy = vy - g * CGFloat(dt)
        var event = "fly"
        // 左右屏幕边缘：水平反弹
        if nx < minX { nx = minX; nvx = -nvx * restitution }
        else if nx > maxX { nx = maxX; nvx = -nvx * restitution }
        // 顶部边缘：撞顶向下
        if ny + size > maxY { ny = maxY - size; nvy = -nvy * restitution }
        // 地面（Mac 独立版没有窗口平台，只有屏幕底边）
        if ny <= floorY {
            if abs(nvy) > landSpeed || abs(nvx) > landSpeed {
                ny = floorY
                nvy = -nvy * restitution
                nvx = nvx * friction
                event = "bounce"
            } else {
                ny = floorY
                nvx = 0; nvy = 0
                event = "land"
            }
        }
        return (nx, ny, nvx, nvy, event)
    }
}

// MARK: - 数据根目录（与 comi_home.py 同语义：旧 ~/.iven-pet 存在即优先沿用）
enum ComiHome {
    static func root(environment: [String: String] = ProcessInfo.processInfo.environment,
                     accountHome: URL = FileManager.default.homeDirectoryForCurrentUser) -> URL {
        // HOME 环境变量优先于系统账号目录：测试与多实例隔离都依赖它
        let home = environment["HOME"].map { URL(fileURLWithPath: $0) }
            ?? accountHome
        if let override = env("COMI_HOME", environment: environment) {
            if override == "~" { return home }
            if override.hasPrefix("~/") { return home.appendingPathComponent(String(override.dropFirst(2))) }
            return URL(fileURLWithPath: override)
        }
        // 旧目录一旦存在就优先沿用：老用户数据不迁走，也不会被误建的新目录抢走
        let legacy = home.appendingPathComponent(".iven-pet")
        var isDirectory: ObjCBool = false
        if FileManager.default.fileExists(atPath: legacy.path, isDirectory: &isDirectory), isDirectory.boolValue { return legacy }
        return home.appendingPathComponent(".comi-pet")
    }
    static func env(_ name: String, environment: [String: String] = ProcessInfo.processInfo.environment) -> String? {
        if let value = environment[name], !value.isEmpty { return value }
        if name.hasPrefix("COMI_") {
            let legacy = "IVEN_" + name.dropFirst("COMI_".count)
            if let value = environment[legacy], !value.isEmpty { return value }
        }
        return nil
    }
}

// MARK: - 本地配置（~/.comi-pet/config.json，与 pet_config.py 共用；cs=cocoa 为本端坐标系）
enum PetConfig {
    static let notifyKinds: Set<String> = ["permission.required", "turn.failed", "task.completed"]

    static func fileURL() -> URL {
        ComiHome.root().appendingPathComponent("config.json")
    }
    static func load() -> [String: Any] {
        guard let data = try? Data(contentsOf: fileURL()),
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return [:] }
        return obj
    }
    static func save(_ obj: [String: Any]) {
        let merged = obj
        if let data = try? JSONSerialization.data(withJSONObject: merged, options: [.sortedKeys]) {
            let url = fileURL()
            try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? data.write(to: url, options: .atomic)
        }
    }
    static func notifyMode(_ obj: [String: Any]) -> String {
        let mode = obj["notifications"] as? String
        return (mode == "always" || mode == "off") ? mode! : "auto"
    }
    static func updateCheckEnabled(_ obj: [String: Any]) -> Bool {
        (obj["update_check"] as? String) != "off"
    }
    static func position(_ obj: [String: Any]) -> (x: CGFloat, y: CGFloat)? {
        guard let pos = obj["position"] as? [String: Any], (pos["cs"] as? String) == "cocoa",
              let x = pos["x"] as? Double, let y = pos["y"] as? Double else { return nil }
        return (CGFloat(x), CGFloat(y))
    }
}

// MARK: - 系统通知（osascript；失败静默，绝不影响桌宠本体）
enum SystemNotify {
    static var lastAt: Double = 0
    static let minInterval: Double = 8.0

    static func gate(_ kind: String, petHidden: Bool, mode: String) -> Bool {
        guard notifyKindAllowed(kind) else { return false }
        if mode == "off" { return false }
        if mode == "always" { return true }
        return petHidden                        // auto
    }
    static func notifyKindAllowed(_ kind: String) -> Bool { PetConfig.notifyKinds.contains(kind) }

    static func send(title: String, body: String) {
        let now = ProcessInfo.processInfo.systemUptime
        if now - lastAt < minInterval { return }
        lastAt = now
        let escaped = { (s: String) in s.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"") }
        let script = "display notification \"\(escaped(String(body.prefix(120))))\" with title \"\(escaped(String(title.prefix(64))))\""
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", script]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try? process.run()
    }
    static func text(_ kind: String, label: String?, zh: Bool) -> String {
        let suffix = label.map { (zh ? "：" : ": ") + String($0.prefix(80)) } ?? ""
        switch kind {
        case "permission.required": return (zh ? "等你确认权限" : "Approval needed") + suffix
        case "turn.failed": return (zh ? "出问题了" : "Something failed") + suffix
        case "task.completed": return (zh ? "任务完成" : "Task completed") + suffix
        default: return label ?? ""
        }
    }
}

// MARK: - 更新检查（与 update_check.py 同语义；只请求 GitHub releases 跳转，不上传内容）
enum UpdateCheck {
    static let releasesURL = URL(string: "https://github.com/IvenKooLab/desktop-pet/releases/latest")!

    static func parseVersion(_ text: String) -> [Int]? {
        var value = text.trimmingCharacters(in: .whitespaces)
        if value.hasPrefix("v") { value.removeFirst() }
        let parts = value.split(separator: ".", omittingEmptySubsequences: false)
        guard !parts.isEmpty else { return nil }
        var numbers: [Int] = []
        for part in parts {
            guard let number = Int(part) else { return nil }
            numbers.append(number)
        }
        return numbers
    }

    static func isNewer(_ latest: [Int], _ current: [Int]) -> Bool {
        let width = max(latest.count, current.count)
        for index in 0..<width {
            let l = index < latest.count ? latest[index] : 0
            let c = index < current.count ? current[index] : 0
            if l != c { return l > c }
        }
        return false
    }

    static func tag(from url: URL) -> String? {
        let components = url.pathComponents
        guard let index = components.firstIndex(of: "tag"), index + 1 < components.count else { return nil }
        let tag = components[index + 1]
        guard let parsed = parseVersion(tag) else { return nil }
        return parsed.map(String.init).joined(separator: ".")
    }

    static func check(completion: @escaping (String?) -> Void) {
        var request = URLRequest(url: releasesURL)
        request.httpMethod = "HEAD"                // 只要跳转后的地址，不下载页面正文
        request.timeoutInterval = 6
        request.setValue("ComiPet-update-check/1 (+https://github.com/IvenKooLab/desktop-pet)",
                         forHTTPHeaderField: "User-Agent")
        URLSession.shared.dataTask(with: request) { _, response, _ in
            let latest = response?.url.flatMap { tag(from: $0) }
            DispatchQueue.main.async { completion(latest) }
        }.resume()
    }
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
    private var dragSamples: [(Double, CGFloat, CGFloat)] = []
    override var isOpaque: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with event: NSEvent) {
        if event.modifierFlags.contains(.control) { rightMouseDown(with: event); return }
        guard let window, let owner else { return }
        pointerStart = NSEvent.mouseLocation
        originStart = window.frame.origin
        moved = false
        doubleClick = event.clickCount >= 2
        dragSamples = [(ProcessInfo.processInfo.systemUptime, pointerStart.x, pointerStart.y)]
        owner.pressed = true
    }
    override func mouseDragged(with event: NSEvent) {
        guard let window, let owner else { return }
        let pointer = NSEvent.mouseLocation
        if hypot(pointer.x-pointerStart.x, pointer.y-pointerStart.y) > 4 {
            if !moved { owner.play("GRAB", mode: "DRAG", seconds: 0) }
            moved = true
            dragSamples.append((ProcessInfo.processInfo.systemUptime, pointer.x, pointer.y))
            if dragSamples.count > 6 { dragSamples.removeFirst(dragSamples.count - 6) }
            window.setFrameOrigin(draggedOrigin(start: originStart, pointerStart: pointerStart, pointer: pointer))
        }
    }
    override func mouseUp(with event: NSEvent) {
        guard let owner else { return }
        owner.pressed = false
        if moved {
            owner.velocity = 0
            // 甩得动就抛出去（THROW 模式接管），温柔放下则重力接管
            let v = ThrowPhysics.estimateVelocity(samples: dragSamples, now: ProcessInfo.processInfo.systemUptime)
            if let v, hypot(v.vx, v.vy) >= ThrowPhysics.throwMin, !owner.pinned {
                owner.beginThrow(vx: v.vx, vy: v.vy)
            } else {
                owner.play(owner.pinned ? "IDLE" : "FALL", mode: owner.pinned ? "IDLE" : "FALL", seconds: owner.pinned ? 6 : 0)
            }
            owner.savePosition()
            dragSamples.removeAll()
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
        let candidates = ["GREET", "BOUNCE", "CHEER", "SPIN", "WAITING", "WORK", "REVIEW", "FAILED", "HAPPY", "SHY", "STRETCH", "DOZE", "RUBIK", "THINKING", "IMPATIENT", "RELIEVED", "YAWN", "STOMP", "CELEBRATE", "SEARCH", "TRICK_OR_TREAT", "GHOST_SHEET", "VAMPIRE_CAPE", "WITCH_SPELL", "BLACK_CAT"]
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
    var selectedSource: String? { didSet { recomputeMode() } }
    func sourceStatus(_ source: String) -> String {
        let matching = sessions.values.filter { $0.source == source }
        if matching.contains(where: { $0.phase == "waiting" }) { return "等你确认" }
        if matching.contains(where: { $0.phase == "working" }) { return "工作中" }
        return matching.isEmpty ? "未收到事件" : "空闲（已收到事件）"
    }
    private(set) var mode: String?        // nil | "working" | "waiting"
    private(set) var label: String?
    private(set) var source: String?
    private(set) var detail: String?
    var activeSources: [String] {
        Array(Set(sessions.values.filter { $0.phase == "working" || $0.phase == "waiting" }.compactMap { $0.source })).sorted()
    }

    init(directory: URL? = nil, clock: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 }) {
        if let directory { dir = directory }
        else if let env = ComiHome.env("COMI_BRIDGE_DIR") { dir = URL(fileURLWithPath: env) }
        else { dir = ComiHome.root().appendingPathComponent("events") }
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
            var eventNotices: [BridgeNotice] = []
            apply(obj, ts: ts, notices: &eventNotices)
            if selectedSource == nil || obj["source"] as? String == selectedSource { notices += eventNotices }
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
        let eligible = sessions.values.filter { selectedSource == nil || $0.source == selectedSource }
        let active = eligible.filter { $0.phase == "waiting" || $0.phase == "working" }
        let chosen = active.sorted {
            if ($0.phase == "waiting") != ($1.phase == "waiting") { return $0.phase == "waiting" }
            return $0.lastSeen == $1.lastSeen ? $0.order > $1.order : $0.lastSeen > $1.lastSeen
        }.first ?? eligible.max { $0.lastSeen == $1.lastSeen ? $0.order < $1.order : $0.lastSeen < $1.lastSeen }
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
    var throwVX: CGFloat = 0
    var throwVY: CGFloat = 0
    var throwBounces = 0
    private var config: [String: Any] = [:]
    private var welcomePending = false      // 首次启动的玩法提示尚未展示
    private var updateVersion: String?      // 发现的新版本（nil = 未知/无更新）
    private var updateChecked = false
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
    private let behaviors: BehaviorPolicy
    private var waitingIdentity = ""
    private var waitingSince: TimeInterval = 0
    private var chatPendingId: String?
    private var chatDeadline: TimeInterval = 0
    private var chatFrame = 0
    private var chatDir: URL { bridge.dir.deletingLastPathComponent().appendingPathComponent("chat") }
    private var displayHidden = false
    private var displayPollAt: TimeInterval = 0
    private var embeddedRequestedAt: TimeInterval?
    private var displayFile: URL { bridge.dir.deletingLastPathComponent().appendingPathComponent("display.json") }
    private func refreshDisplay(now: TimeInterval) {
        guard now >= displayPollAt else { return }
        displayPollAt = now+0.25
        let lease = embeddedDisplayLease(displayFile,now:Date().timeIntervalSince1970*1000)
        // 两段式租约：只有 DSH 网页 claim（client_id 已写）才真的隐藏
        var hidden = lease?.isClaimed ?? false
        if embeddedRequestedAt != nil {
            if hidden {
                embeddedRequestedAt = nil               // DSH 网页已接手
            } else if lease == nil || now-embeddedRequestedAt! > 6.5 {
                // 确认窗口内没人接手（dsh 没开/页面没开）：回桌面并提示，不白藏
                embeddedRequestedAt = nil
                requestDisplay("desktop")
                showBubble(bridgeZh ? "未连上 DSH：启动 dsh 并打开网页后再试内嵌"
                                    : "DSH not reachable: start dsh and open its web page first",seconds:4)
                displayPollAt = now+0.25
                hidden = false
            }
        }
        if hidden != displayHidden {
            displayHidden = hidden
            print("[display-mode] \(hidden ? "embedded" : "desktop")"); fflush(stdout)
            if !hidden { panel.orderFrontRegardless(); play("IDLE",mode:"IDLE",seconds:3) }
        }
        if hidden { panel.orderOut(nil); followPanel?.orderOut(nil); bubblePanel?.orderOut(nil) }
    }
    private func requestDisplay(_ mode: String) {
        // 内嵌请求只给 6 秒确认窗口；网页客户端 claim 后会写 client_id 并续满租期
        let lease = DisplayLease(version:1,mode:mode,owner:"dsh",
                                 lease_until:mode == "embedded" ? Date().timeIntervalSince1970*1000+6000 : 0,
                                 client_id:nil)
        do {
            try FileManager.default.createDirectory(at:displayFile.deletingLastPathComponent(),withIntermediateDirectories:true)
            try JSONEncoder().encode(lease).write(to:displayFile,options:.atomic)
            embeddedRequestedAt = mode == "embedded" ? ProcessInfo.processInfo.systemUptime : nil
            displayPollAt = 0
        } catch {
            showBubble(bridgeZh ? "显示模式未能切换，请重试" : "Could not change display mode. Please retry.",seconds:4)
        }
    }
    private var autoplay = UserDefaults.standard.object(forKey:"Autoplay") as? Bool ?? true
    // 宿主桥接
    private var bridge = HostBridge()
    private var bridgeEnabled = UserDefaults.standard.object(forKey: "BridgeEnabled") as? Bool ?? true
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
    private var uiLanguage = UserDefaults.standard.string(forKey:"UILanguage") ?? "system"
    private var bridgeZh: Bool {
        uiLanguage == "zh" || (uiLanguage == "system" && Locale.current.language.languageCode?.identifier == "zh")
    }
    private func menuText(_ title: String) -> String {
        if bridgeZh { return title }
        let english = ["Comi Pet · 独立桌宠":"Comi Pet · Desktop companion",
            "跟踪 Harness":"Track Harness", "自动 · 全部已接入":"Automatic · All connected",
            "工作中":"Working", "等你确认":"Needs approval", "未收到事件":"No events received",
            "空闲（已收到事件）":"Idle (events received)", "自动：确认优先 → 最近活动":"Auto: approvals → recent activity",
            "固定在当前位置":"Pin in place", "自动轮播动作":"Automatic animations",
            "系统通知":"System notifications", "自动（桌宠隐藏时）":"Auto (when hidden)",
            "总是通知":"Always notify", "关闭":"Off",
            "伸懒腰":"Stretch", "打瞌睡":"Doze", "玩魔方":"Rubik’s cube", "等待":"Wait",
            "工作":"Work", "检查":"Review", "失落":"Sad", "挥手打招呼":"Wave hello",
            "困倦眨眼":"Sleepy blink", "委屈表情":"Feeling down", "挥手庆祝":"Celebrate", "左右观察":"Look around", "不给糖就捣蛋":"Trick or treat", "白布幽灵":"Ghost sheet", "吸血鬼披风亮相":"Vampire cape", "小女巫施法":"Witch spell", "黑猫":"Black cat",
            "弹跳":"Bounce", "开心":"Happy", "打板":"Clapperboard", "观察四周":"Look around",
            "小跳快走":"Quick walk", "害羞":"Shy", "睡觉":"Sleep", "唤醒":"Wake up",
            "节日":"Holidays",
            "退出独立版":"Quit Comi Pet", "语言 / Language":"Language / 语言", "打开 GitHub 仓库":"Open GitHub repository", "启动时检查更新":"Check for updates on launch", "检查更新…":"Check for updates…", "动作":"Actions", "陪伴":"Companion", "关于与更新":"About & updates", "日常互动":"Everyday", "工作状态":"Work themes", "生活小动作":"Little breaks", "宿主桥接":"Host bridge", "显示模式":"Display mode", "苦思冥想":"Thinking hard", "等待不耐烦":"Getting impatient", "额度不足（表演）":"Low token budget (performance)", "松口气":"Relieved",
            "和 Comi 说话…":"Talk to Comi…", "独立桌面":"Desktop", "DSH 界面内":"Inside DSH",
            "内嵌需 DSH 网页接手；约 6 秒未接手自动回桌面":"Inside DSH needs its web page to take over; falls back to desktop after ~6s",
            "未连上 DSH：启动 dsh 并打开网页后再试内嵌":"DSH not reachable: start dsh and open its web page first"]
        return english[title] ?? title
    }

    private func advance() {
        if let hostMode = bridge.mode, hostAvailable(hostMode), !hostSuppressed() {
            if hostMode == "waiting" {
                play("WAITING", mode: "HOST", seconds: 0)
            } else if clipName == "WORK" && mode == "HOST" {
                // 工作不无限连打板：打一轮板喘口气，到点再打
                if let thinking = clips["THINKING"] {
                    play("THINKING", mode:"HOST", seconds:Double(thinking.total)/1000)
                } else { play("IDLE", mode: "HOST", seconds: Double.random(in: 1.2...2.2)) }
            } else {
                play("WORK", mode: "HOST", seconds: Double(clips["WORK"]!.total)/1000)
            }
            return
        }
        if mode != "IDLE" || !autoplay {
            play("IDLE",mode:"IDLE",seconds:Double.random(in:behaviors.idle))
            return
        }
        let action = deck.next(available:Set(clips.keys),pinned:pinned)
        if action.hasPrefix("WALK_") {
            direction = action == "WALK_r" ? 1 : -1
            speed = 50
            play(action,mode:"WALK",seconds:behaviors.seconds(action,clip:clips[action]!))
        } else {
            play(action,mode:"ACTION",seconds:behaviors.seconds(action,clip:clips[action]!))
        }
    }

    // ---------- 宿主桥接 ----------
    private func hostAvailable(_ hostMode: String) -> Bool {
        clips[hostMode == "waiting" ? "WAITING" : "WORK"] != nil
    }
    private func hostSuppressed() -> Bool {
        let now = ProcessInfo.processInfo.systemUptime
        return pressed || mode == "DRAG" || mode == "FALL" || mode == "THROW" || mode == "SLEEP" || now < manualUntil
    }
    // ---------- 甩抛物理 ----------
    func beginThrow(vx: CGFloat, vy: CGFloat) {
        throwVX = vx; throwVY = vy; throwBounces = 0
        play("FALL", mode: "THROW", seconds: 0)     // 空中帧；运动由 THROW 分支接管
    }
    /// 落地/弹跳瞬间的 Q 弹挤压（CALayer 关键帧，不改素材帧）
    private func squash(_ amount: CGFloat) {
        guard let layer = view.layer else { return }
        let height = layer.bounds.height
        let squashed = CATransform3DConcat(
            CATransform3DMakeTranslation(0, height*(1-amount), 0),
            CATransform3DMakeScale(1.0 + (1-amount)*0.6, amount, 1))
        let anim = CAKeyframeAnimation(keyPath: "transform")
        anim.values = [layer.transform, squashed, layer.transform]
        anim.keyTimes = [0, 0.35, 1]
        anim.duration = 0.3
        layer.add(anim, forKey: "comi-squash")
    }
    // ---------- 本地配置与系统通知 ----------
    func savePosition() {
        guard let panel else { return }
        config["position"] = ["x": Double(panel.frame.minX), "y": Double(panel.frame.minY), "cs": "cocoa"] as [String: Any]
        PetConfig.save(config)
    }
    private func maybeNotify(_ n: BridgeNotice) {
        guard SystemNotify.gate(n.kind, petHidden: displayHidden,
                                mode: PetConfig.notifyMode(config)) else { return }
        SystemNotify.send(title: "Comi · " + hostName(),
                          body: SystemNotify.text(n.kind, label: n.label, zh: bridgeZh))
    }
    func applicationWillTerminate(_ notification: Notification) { savePosition() }
    private func hostTick() {
        guard bridgeEnabled else { return }
        bridgeFrame += 1
        if bridgeFrame >= 60 {                       // 每秒轮询一次收件箱
            bridgeFrame = 0
            for notice in bridge.poll() { handleNotice(notice) }
        }
        hostAssert()
    }
    private func hostAssert() {
        let identity = bridge.mode == "waiting" ? (bridge.source ?? "unknown") : ""
        if identity != waitingIdentity { waitingIdentity = identity; waitingSince = ProcessInfo.processInfo.systemUptime }
        let waitingClip = !identity.isEmpty && ProcessInfo.processInfo.systemUptime-waitingSince >= 30 && clips["IMPATIENT"] != nil ? "IMPATIENT" : "WAITING"
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
            if let target = hostTransitionClip(phase:bridge.mode!,current:clipName,impatient:waitingClip == "IMPATIENT") {
                play(target, mode:"HOST", seconds:target == "WORK" ? Double(clips[target]!.total)/1000 : 0)
            }
            return
        }
        if bridge.mode == "waiting" {
            play(waitingClip, mode: "HOST", seconds: 0)
        } else {
            play("WORK", mode: "HOST", seconds: Double(clips["WORK"]!.total)/1000)

        }
    }
    private func handleNotice(_ n: BridgeNotice) {
        maybeNotify(n)
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
                manualUntil = ProcessInfo.processInfo.systemUptime + Double(clip.total)/1000/playbackSpeed
                play("FAILED", mode: "ACTION", seconds: Double(clip.total)/1000)
            }
        case "turn.failed":
            if let clip = clips["FAILED"] { play("FAILED", mode: "ACTION", seconds: Double(clip.total)/1000) }
            showBubble(n.label.map { bridgeZh ? "出问题了：\($0)" : "Failed: \($0)" }
                       ?? (bridgeZh ? "出问题了…" : "Something failed…"), seconds: 6, title: hostName()+" · "+(bridgeZh ? "遇到问题" : "Needs attention"), tone: "error")
        case "task.completed":
            let pick = clips["RELIEVED"] != nil ? "RELIEVED" : (clips["CHEER"] != nil ? "CHEER" : (clips["HAPPY"] != nil ? "HAPPY" : nil))
            if let pick {
                manualUntil = ProcessInfo.processInfo.systemUptime + (Double(clips[pick]!.total)/1000 + 1.0)/playbackSpeed + 0.5
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
            badge.title = "Comi · 当前跟随"
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
        if bridge.source == nil, let selected = bridge.selectedSource {
            let names = ["dsh":"DSH","zcode":"ZCode","codex":"Codex","claude-code":"Claude Code","cursor":"Cursor","opencode":"OpenCode"]
            text = (names[selected] ?? selected)+(bridgeZh ? " · 未收到事件" : " · No events")
        }
        if let source = bridge.source {
            text = (bridge.mode == nil ? (bridgeZh ? "最近 · " : "Last · ") : (bridgeZh ? "跟随 · " : "Following · "))+hostName()
            let others = max(0,bridge.activeSources.count-1)
            if bridge.mode != nil && bridge.selectedSource == nil && others > 0 { text += "  +\(others)" }
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
            card.title = "Comi · 任务状态"
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
        if ProcessInfo.processInfo.environment["COMI_BRIDGE_DEBUG"] == "1", !persistent || bubbleKey == key {
            if let id = bubblePanel?.windowNumber { print("[status-card] window=\(id)"); fflush(stdout) }
        }
    }

    init(directory: URL) throws {
        behaviors = BehaviorPolicy(directory:directory.deletingLastPathComponent())
        let manifest = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: directory.appendingPathComponent("animation.json")))
        guard manifest.version == 1 else { throw NSError(domain:"ComiPet",code:1,userInfo:[NSLocalizedDescriptionKey:"Unsupported animation manifest"]) }
        clips = manifest.clips
        super.init()
        for (state, clip) in clips {
            guard !clip.frames.isEmpty, clip.frames.count == clip.durations.count,
                  clip.durations.allSatisfy({ $0 > 0 }) else {
                throw NSError(domain:"ComiPet",code:2,userInfo:[NSLocalizedDescriptionKey:"Invalid clip: \(state)"])
            }
        }
        clips["FALL"] = Clip(frames:["fall_0"],durations:[1000])
        clips["LAND"] = Clip(frames:["land_0"],durations:[350])
        for name in Set(clips.values.flatMap { $0.frames }) {
            let path = directory.appendingPathComponent(name+".png")
            guard let source = NSImage(contentsOf: path),
                  let image = source.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                throw NSError(domain:"ComiPet",code:3,userInfo:[NSLocalizedDescriptionKey:"Missing transparent PNG: \(path.path)"])
            }
            images[name] = image
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main!.visibleFrame
        panel = PetPanel(contentRect: NSRect(x:screen.maxX-320,y:screen.maxY-240,width:200,height:200),
                         styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
        panel.title = "Comi Pet · 独立桌宠"
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
        // 位置记忆：恢复上次离开时的位置（Cocoa 坐标，cs=cocoa）
        config = PetConfig.load()
        welcomePending = !(config["welcomed"] as? Bool ?? false)
        if let pos = PetConfig.position(config) {
            let visible = (NSScreen.screens.first {
                $0.visibleFrame.insetBy(dx: -200, dy: -200).contains(NSPoint(x: pos.x+100, y: pos.y+100))
            } ?? NSScreen.main)?.visibleFrame ?? screen
            panel.setFrameOrigin(NSPoint(x: min(max(pos.x, visible.minX), visible.maxX-200),
                                         y: min(max(pos.y, visible.minY-7), visible.maxY-240)))
        }
        // A pinned pet must start idle; FALL has no deadline and suppresses host UI.
        play(pinned ? "IDLE" : "FALL",mode:pinned ? "IDLE" : "FALL",seconds:pinned ? 4 : 0)
        scheduleWelcome()
        previous = ProcessInfo.processInfo.systemUptime
        timer = Timer(timeInterval:1.0/60.0,target:self,selector:#selector(tick),userInfo:nil,repeats:true)
        RunLoop.main.add(timer!, forMode:.common)
        print("[start] native AppKit | transparent CALayer | \(images.count) PNG frames | drag uses Cocoa screen coordinates | bridge=\(bridge.dir.path)")
        fflush(stdout)
        DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in
            self?.autoUpdateCheck()
        }
    }

    // ---------- 更新检查 ----------
    private var currentVersion: String {
        (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "0.0.0"
    }
    private func autoUpdateCheck() {
        guard PetConfig.updateCheckEnabled(config), !updateChecked else { return }
        updateChecked = true
        checkForUpdate(manual: false)
    }
    private func checkForUpdate(manual: Bool) {
        if manual {
            showBubble(bridgeZh ? "正在检查更新…" : "Checking for updates…", seconds: 1.6)
        }
        UpdateCheck.check { [weak self] latest in
            self?.handleUpdate(latest: latest, manual: manual)
        }
    }
    private func handleUpdate(latest: String?, manual: Bool) {
        guard let latest,
              let latestParsed = UpdateCheck.parseVersion(latest),
              let currentParsed = UpdateCheck.parseVersion(currentVersion) else {
            if manual {
                showBubble(bridgeZh ? "检查更新失败：网络不可用或被拦截"
                                    : "Update check failed: network unavailable", seconds: 4)
            }
            return
        }
        if UpdateCheck.isNewer(latestParsed, currentParsed) {
            updateVersion = latest
            let text = bridgeZh
                ? "发现新版本 v\(latest)（当前 v\(currentVersion)）：右键 → 下载新版本"
                : "Update v\(latest) available (current v\(currentVersion)): right-click → Download"
            if displayHidden {
                SystemNotify.send(title: "Comi · " + (bridgeZh ? "发现新版本" : "Update available"),
                                  body: text)
            }
            showBubble(text, seconds: 9,
                       title: bridgeZh ? "发现新版本" : "Update available", tone: "done")
        } else if manual {
            showBubble(bridgeZh ? "已是最新版本 v\(currentVersion)"
                                : "You are up to date (v\(currentVersion))", seconds: 4)
        }
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
    private func scheduleWelcome() {
        guard welcomePending else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.2) { [weak self] in
            guard let self, welcomePending else { return }
            if displayHidden || bubbleIsHost || (bridgeEnabled && bridge.mode != nil)
                || ["FALL", "THROW", "DRAG", "SLEEP"].contains(mode) || clipName == "LAND" {
                scheduleWelcome()
                return
            }
            showBubble(bridgeZh ? "单击跳一下，拖我走，甩出去会飞；右键有菜单"
                                : "Click to hop, drag to move, flick to throw — right-click for the menu",
                       seconds: 7, title: bridgeZh ? "你好，我是 Comi" : "Hi, I'm Comi", tone: "info")
            welcomePending = false
            config["welcomed"] = true
            PetConfig.save(config)
        }
    }

    // ---------- 本机控制接口（control_api.py 协议的 Swift 执行端） ----------
    private var apiFrame = 0
    private var apiDir: URL { bridge.dir.deletingLastPathComponent().appendingPathComponent("api") }
    private var stateFile: URL { bridge.dir.deletingLastPathComponent().appendingPathComponent("state.json") }
    private func stateSnapshot() -> [String: Any] {
        let formatter = ISO8601DateFormatter()
        var snap: [String: Any] = ["updated": formatter.string(from: Date()),
            "state": clipName, "mode": mode,
            "x": Double(panel?.frame.minX ?? 0), "y": Double(panel?.frame.minY ?? 0),
            "display": displayHidden ? "embedded" : "desktop",
            "host_mode": bridge.mode ?? NSNull()]
        snap["following"] = bridge.source ?? NSNull()
        return snap
    }
    private func writeStateSnapshot() {
        let payload = stateSnapshot().merging(["version": 1]) { current, _ in current }
        if let data = try? JSONSerialization.data(withJSONObject: payload) {
            try? data.write(to: stateFile, options: .atomic)
        }
    }
    private func pollControlApi() {
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: apiDir.path) else { return }
        for name in names.sorted() where name.hasPrefix("request-") && name.hasSuffix(".json") {
            let url = apiDir.appendingPathComponent(name)
            // 与 Python 端一致的校验；请求文件处理即取走
            guard let data = try? Data(contentsOf: url),
                  let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  (obj["version"] as? Int) == 1,
                  let id = obj["id"] as? String, !id.isEmpty, id.count <= 64 else {
                try? FileManager.default.removeItem(at: url); continue
            }
            let action = obj["action"] as? String ?? ""
            var reply: [String: Any]
            switch action {
            case "say":
                let text = ChatClient.cleanText(obj["text"], limit: 2000)
                if text.isEmpty {
                    reply = ["ok": false, "reason": "bad-request"]
                } else {
                    if !displayHidden { showBubble(text, seconds: min(9, 2.6 + Double(text.count)*0.024)) }
                    reply = ["ok": true, "shown": !displayHidden]
                }
            case "play":
                let state = obj["state"] as? String ?? ""
                let builtin: Set<String> = ["IDLE","WALK","RUN","SLEEP","BOUNCE","HAPPY","SHY","SPIN"]
                if builtin.contains(state) || clips[state] != nil {
                    perform(state == "WALK" ? (Bool.random() ? "WALK_r" : "WALK_l") : state)
                    reply = ["ok": true, "state": clipName]
                } else {
                    reply = ["ok": false, "reason": "unsupported"]
                }
            case "sleep":
                perform("SLEEP")
                reply = ["ok": true]
            case "wake":
                let asleep = mode == "SLEEP"
                if asleep { perform("IDLE") }
                reply = ["ok": true, "was_asleep": asleep]
            case "state":
                reply = stateSnapshot()
            default:
                reply = ["ok": false, "reason": "bad-request"]
            }
            let payload = reply.merging(["version": 1, "id": id]) { current, _ in current }
            if let out = try? JSONSerialization.data(withJSONObject: payload) {
                try? out.write(to: apiDir.appendingPathComponent("reply-\(id).json"), options: .atomic)
            }
            try? FileManager.default.removeItem(at: url)
        }
    }

    // ---------- 和 Comi 说话 ----------
    @objc private func chatInput() {
        if chatPendingId != nil {
            showBubble(bridgeZh ? "Comi 还在想上一个问题…" : "Comi is still thinking…", seconds: 2.2)
            return
        }
        let alert = NSAlert()
        alert.messageText = bridgeZh ? "和 Comi 说话" : "Talk to Comi"
        alert.informativeText = bridgeZh ? "说点什么（需要 DSH 在线并安装适配器）"
                                         : "Say something (needs DSH running with its adapter)"
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 260, height: 24))
        input.placeholderString = bridgeZh ? "聊点什么…" : "Say something…"
        alert.accessoryView = input
        alert.addButton(withTitle: bridgeZh ? "发送" : "Send")
        alert.addButton(withTitle: bridgeZh ? "取消" : "Cancel")
        alert.window.initialFirstResponder = input
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let text = input.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        do {
            let id = "pet-\(getpid())-\(UUID().uuidString.prefix(8))"
            try ChatClient.writeRequest(chatDir, text: text, id: id)
            chatPendingId = id
            chatDeadline = Date().timeIntervalSince1970 + 65
            manualUntil = chatDeadline + 2      // 等回复期间宿主状态不抢
            if clips["THINKING"] != nil { play("THINKING", mode: "ACTION", seconds: 0) }
        } catch {
            showBubble(bridgeZh ? "消息没有发出去" : "Could not send the message", seconds: 3)
        }
    }
    private func handleChatReply(_ reply: ChatReply) {
        chatPendingId = nil
        if reply.ok {
            if let mood = reply.mood, let clip = ChatClient.moodClips[mood], clips[clip] != nil {
                play(clip, mode: "ACTION", seconds: Double(clips[clip]!.total)/1000)
            } else {
                play("IDLE", mode: "IDLE", seconds: 4)
            }
            showBubble(reply.text, seconds: min(9, 2.6 + Double(reply.text.count) * 0.024))
        } else {
            play("IDLE", mode: "IDLE", seconds: 3)
            let message: String
            switch reply.reason {
            case "provider-missing":
                message = bridgeZh ? "需要 DSH 在线且配置了模型才能对话"
                                   : "Chat needs DSH running with a model configured"
            case "bad-request":
                message = bridgeZh ? "消息没有发出去" : "The message was not sent"
            default:
                message = bridgeZh ? "生成失败，稍后再试" : "Generation failed, try again later"
            }
            showBubble(message, seconds: 4.2)
        }
    }
    @objc private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        let dt = min(0.05,max(0,now-previous)) * playbackSpeed
        previous = now
        refreshDisplay(now:now)
        // 本机文件控制接口（docs/API.md）：~0.5s 轮询请求 + 写状态快照
        apiFrame += 1
        if apiFrame >= 30 {
            apiFrame = 0
            pollControlApi()
            writeStateSnapshot()
        }
        if displayHidden {
            bridgeFrame += 1
            if bridgeFrame >= 60 { bridgeFrame = 0; _ = bridge.poll() }
            return
        }
        if chatPendingId != nil {
            chatFrame += 1
            if chatFrame >= 30 {                     // ~0.5s @60fps
                chatFrame = 0
                if let reply = ChatClient.readReply(chatDir, id: chatPendingId!) {
                    handleChatReply(reply)
                } else if Date().timeIntervalSince1970 > chatDeadline {
                    chatPendingId = nil
                    play("IDLE", mode: "IDLE", seconds: 3)
                    showBubble(bridgeZh ? "没有等到回复：需要 DSH 在线、装好适配器并配置模型"
                                        : "No reply: DSH must be running with its adapter and a model",
                               seconds: 5)
                }
            }
        }
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
            } else if mode == "THROW" {
                // 甩出后的抛物线：边缘反弹 + 落地 Q 弹，语义同 throw_physics.py
                let r = ThrowPhysics.step(x: origin.x, y: origin.y, vx: throwVX, vy: throwVY, dt: dt,
                                          minX: screen.minX, maxX: screen.maxX-200,
                                          maxY: screen.maxY, floorY: floor, size: 200)
                origin.x = r.x; origin.y = r.y; throwVX = r.vx; throwVY = r.vy
                if r.event == "bounce" {
                    throwBounces += 1
                    squash(0.86)
                } else if r.event == "land" || throwBounces > ThrowPhysics.maxBounces {
                    throwVX = 0; throwVY = 0; throwBounces = 0
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
        if action.hasPrefix("DISPLAY:") {
            let selected = String(action.dropFirst(8))
            if ["desktop","embedded"].contains(selected) { requestDisplay(selected) }
            return
        }
        if action == "GITHUB" {
            NSWorkspace.shared.open(URL(string:"https://github.com/IvenKooLab/desktop-pet")!)
            return
        }
        if action == "TOGGLE_BRIDGE" {
            bridgeEnabled.toggle()
            UserDefaults.standard.set(bridgeEnabled, forKey: "BridgeEnabled")
            if !bridgeEnabled {
                if mode == "HOST" { play("IDLE", mode: "IDLE", seconds: 3) }
                if bubbleIsHost { bubblePanel?.orderOut(nil); bubbleKey = ""; bubbleIsHost = false }
            }
            return
        }
        if action == "CHECK_UPDATE" { checkForUpdate(manual: true); return }
        if action == "DOWNLOAD_UPDATE" { NSWorkspace.shared.open(UpdateCheck.releasesURL); return }
        if action == "TOGGLE_UPDATE_CHECK" {
            let enabled = PetConfig.updateCheckEnabled(config)
            config["update_check"] = enabled ? "off" : "auto"
            PetConfig.save(config)
            return
        }
        if action.hasPrefix("LANG:") {
            let language = String(action.dropFirst(5))
            guard ["system","zh","en"].contains(language) else { return }
            uiLanguage = language
            UserDefaults.standard.set(language,forKey:"UILanguage")
            bubblePanel?.orderOut(nil); bubbleKey = ""; bubbleIsHost = false; bubbleHideAt = 0
            followKey = ""; hostAssert(); updateFollowingBadge()
            return
        }
        if action.hasPrefix("TRACK:") {
            let source = String(action.dropFirst(6))
            bridge.selectedSource = source.isEmpty ? nil : source
            sleepQueue.removeAll()
            bubblePanel?.orderOut(nil); bubbleKey = ""; bubbleIsHost = false; bubbleHideAt = 0
            hostAssert()
            return
        }
        if action.hasPrefix("NOTIFY:") {
            let mode = String(action.dropFirst(7))
            guard ["auto","always","off"].contains(mode) else { return }
            config["notifications"] = mode
            PetConfig.save(config)
            return
        }
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
            throwVX = 0; throwVY = 0; throwBounces = 0
            play(pinned ? "IDLE" : "FALL",mode:pinned ? "IDLE" : "FALL",seconds:pinned ? 6 : 0)
            savePosition()
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
            let seconds = behaviors.seconds(action,clip:clip)
            manualUntil = ProcessInfo.processInfo.systemUptime + seconds/playbackSpeed + 1.0
            play(action,mode:"ACTION",seconds:seconds)
        }
    }
    @objc private func menuAction(_ item: NSMenuItem) { perform(item.representedObject as! String) }
    private func clipItem(_ title: String, _ action: String) -> NSMenuItem {
        let item = NSMenuItem(title: menuText(title), action: #selector(menuAction), keyEquivalent: "")
        item.target = self
        item.representedObject = action
        return item
    }

    /// 动作按类别分组；节日演出直接放在“节日”下。
    private func actionsSubmenu() -> NSMenu {
        let actions = NSMenu()
        let everyday = NSMenu()
        for (title, action) in [("打板","CHEER"),("观察四周","SPIN"),("小跳快走","RUN"),
                                ("害羞","SHY"),("弹跳","BOUNCE"),("开心","HAPPY"),
                                ("挥手打招呼","GREET")] {
            if clips[action] != nil { everyday.addItem(clipItem(title, action)) }
        }
        everyday.addItem(.separator())
        everyday.addItem(clipItem("睡觉", "SLEEP"))
        everyday.addItem(clipItem("唤醒", "IDLE"))
        let everydayItem = NSMenuItem(title: menuText("日常互动"), action: nil, keyEquivalent: "")
        everydayItem.submenu = everyday
        actions.addItem(everydayItem)

        let work = NSMenu()
        for (title, action) in [("苦思冥想","THINKING"),("工作","WORK"),("检查","REVIEW"),
                                ("等待","WAITING"),("等待不耐烦","IMPATIENT"),
                                ("额度不足（表演）","TOKEN_LOW"),("松口气","RELIEVED"),
                                ("失落","FAILED")] {
            if clips[action] != nil { work.addItem(clipItem(title, action)) }
        }
        if work.numberOfItems > 0 {
            let workItem = NSMenuItem(title: menuText("工作状态"), action: nil, keyEquivalent: "")
            workItem.submenu = work
            actions.addItem(workItem)
        }

        let life = NSMenu()
        for (title, action) in [("伸懒腰","STRETCH"),("打瞌睡","DOZE"),("玩魔方","RUBIK"),
                                ("困倦眨眼","YAWN"),("委屈表情","STOMP"),
                                ("挥手庆祝","CELEBRATE"),("左右观察","SEARCH")] {
            if clips[action] != nil { life.addItem(clipItem(title, action)) }
        }
        if life.numberOfItems > 0 {
            let lifeItem = NSMenuItem(title: menuText("生活小动作"), action: nil, keyEquivalent: "")
            lifeItem.submenu = life
            actions.addItem(lifeItem)
        }
        let holidays = NSMenu()
        for (title, action) in [("不给糖就捣蛋","TRICK_OR_TREAT"),("白布幽灵","GHOST_SHEET"),
                                ("吸血鬼披风亮相","VAMPIRE_CAPE"),("小女巫施法","WITCH_SPELL"),("黑猫","BLACK_CAT")] {
            if clips[action] != nil { holidays.addItem(clipItem(title, action)) }
        }
        if holidays.numberOfItems > 0 {
            let holidaysItem = NSMenuItem(title: menuText("节日"), action: nil, keyEquivalent: "")
            holidaysItem.submenu = holidays
            actions.addItem(holidaysItem)
        }
        return actions
    }

    /// 陪伴：显示位置 / 跟踪来源 / 固定 / 桥接 / 轮播 / 通知。
    private func companionSubmenu() -> NSMenu {
        let companion = NSMenu()
        let displayItem = NSMenuItem(title:menuText("显示模式"),action:nil,keyEquivalent:"")
        let displays = NSMenu()
        for (code,title) in [("desktop","独立桌面"),("embedded","DSH 界面内")] {
            let item = NSMenuItem(title:menuText(title),action:#selector(menuAction),keyEquivalent:"")
            item.target = self; item.representedObject = "DISPLAY:"+code
            item.state = (displayHidden ? "embedded" : "desktop") == code ? .on : .off
            displays.addItem(item)
        }
        let displayHint = NSMenuItem(title:menuText("内嵌需 DSH 网页接手；约 6 秒未接手自动回桌面"),action:nil,keyEquivalent:"")
        displayHint.isEnabled = false; displays.addItem(.separator()); displays.addItem(displayHint)
        displayItem.submenu = displays; companion.addItem(displayItem)

        let tracking = NSMenuItem(title:menuText("跟踪 Harness"),action:nil,keyEquivalent:"")
        let sources = NSMenu()
        sources.minimumWidth = 320
        for (source,name) in [("","自动 · 全部已接入"),("dsh","DSH"),("zcode","ZCode"),("codex","Codex"),("claude-code","Claude Code"),("cursor","Cursor"),("opencode","OpenCode")] {
            let title = source.isEmpty ? menuText(name) : name+" · "+menuText(bridge.sourceStatus(source))
            let item = NSMenuItem(title:title,action:#selector(menuAction),keyEquivalent:"")
            item.target = self
            item.representedObject = "TRACK:"+source
            item.state = (bridge.selectedSource ?? "") == source ? .on : .off
            let textWidth = (title as NSString).size(withAttributes: [.font: NSFont.menuFont(ofSize: 0)]).width
            sources.minimumWidth = max(sources.minimumWidth, ceil(textWidth)+72)
            sources.addItem(item)
        }
        sources.addItem(.separator())
        let hint = NSMenuItem(title:menuText("自动：确认优先 → 最近活动"),action:nil,keyEquivalent:"")
        hint.isEnabled = false
        sources.addItem(hint)
        tracking.submenu = sources
        companion.addItem(tracking)

        let pin = NSMenuItem(title:menuText("固定在当前位置"),action:#selector(menuAction),keyEquivalent:"")
        pin.target = self
        pin.representedObject = "PIN"
        pin.state = pinned ? .on : .off
        companion.addItem(pin)

        let auto = NSMenuItem(title:menuText("自动轮播动作"),action:#selector(menuAction),keyEquivalent:"")
        auto.target = self
        auto.representedObject = "AUTOPLAY"
        auto.state = autoplay ? .on : .off
        companion.addItem(auto)

        let notifyItem = NSMenuItem(title:menuText("系统通知"),action:nil,keyEquivalent:"")
        let notifyMenu = NSMenu()
        let currentNotify = PetConfig.notifyMode(config)
        for (code,title) in [("auto","自动（桌宠隐藏时）"),("always","总是通知"),("off","关闭")] {
            let item = NSMenuItem(title:menuText(title),action:#selector(menuAction),keyEquivalent:"")
            item.target = self
            item.representedObject = "NOTIFY:"+code
            item.state = currentNotify == code ? .on : .off
            notifyMenu.addItem(item)
        }
        notifyItem.submenu = notifyMenu
        companion.addItem(notifyItem)

        let bridgeItem = NSMenuItem(title:menuText("宿主桥接"),action:#selector(menuAction),keyEquivalent:"")
        bridgeItem.target = self
        bridgeItem.representedObject = "TOGGLE_BRIDGE"
        bridgeItem.state = bridgeEnabled ? .on : .off
        companion.addItem(bridgeItem)
        return companion
    }

    /// 关于与更新：版本 / 检查更新 / 下载 / GitHub。
    private func aboutSubmenu() -> NSMenu {
        let about = NSMenu()
        let version = NSMenuItem(title: menuText("当前版本 v\(currentVersion)"), action: nil, keyEquivalent: "")
        version.isEnabled = false
        about.addItem(version)
        about.addItem(.separator())

        let autoUpdate = NSMenuItem(title: menuText("启动时检查更新"), action: #selector(menuAction), keyEquivalent: "")
        autoUpdate.target = self
        autoUpdate.representedObject = "TOGGLE_UPDATE_CHECK"
        autoUpdate.state = PetConfig.updateCheckEnabled(config) ? .on : .off
        about.addItem(autoUpdate)
        let checkUpdate = NSMenuItem(title: menuText("检查更新…"), action: #selector(menuAction), keyEquivalent: "")
        checkUpdate.target = self
        checkUpdate.representedObject = "CHECK_UPDATE"
        about.addItem(checkUpdate)
        if let updateVersion {
            let download = NSMenuItem(title: bridgeZh ? "下载新版本 v\(updateVersion)…" : "Download v\(updateVersion)…", action: #selector(menuAction), keyEquivalent: "")
            download.target = self
            download.representedObject = "DOWNLOAD_UPDATE"
            about.addItem(download)
        }
        let github = NSMenuItem(title:menuText("打开 GitHub 仓库"),action:#selector(menuAction),keyEquivalent:"")
        github.target = self; github.representedObject = "GITHUB"; about.addItem(github)
        return about
    }

    func contextMenu() -> NSMenu {
        let menu = NSMenu()
        let heading = NSMenuItem(title:menuText("Comi Pet · 独立桌宠"),action:nil,keyEquivalent:"")
        heading.isEnabled = false
        menu.addItem(heading)
        menu.addItem(.separator())
        if clips["THINKING"] != nil {
            let chat = NSMenuItem(title:menuText("和 Comi 说话…"),action:#selector(chatInput),keyEquivalent:"")
            chat.target = self
            menu.addItem(chat)
        }
        let actionsItem = NSMenuItem(title: menuText("动作"), action: nil, keyEquivalent: "")
        actionsItem.submenu = actionsSubmenu()
        menu.addItem(actionsItem)
        let companionItem = NSMenuItem(title: menuText("陪伴"), action: nil, keyEquivalent: "")
        companionItem.submenu = companionSubmenu()
        menu.addItem(companionItem)
        let languageItem = NSMenuItem(title:menuText("语言 / Language"),action:nil,keyEquivalent:"")
        let languages = NSMenu()
        for (code,name) in [("system",bridgeZh ? "跟随系统" : "System default"),("zh","简体中文"),("en","English")] {
            let item = NSMenuItem(title:name,action:#selector(menuAction),keyEquivalent:"")
            item.target = self; item.representedObject = "LANG:"+code
            item.state = uiLanguage == code ? .on : .off
            languages.addItem(item)
        }
        languageItem.submenu = languages; menu.addItem(languageItem)
        let aboutItem = NSMenuItem(title: menuText("关于与更新"), action: nil, keyEquivalent: "")
        aboutItem.submenu = aboutSubmenu()
        menu.addItem(aboutItem)
        menu.addItem(.separator())
        let quit = NSMenuItem(title:menuText("退出独立版"),action:#selector(menuAction),keyEquivalent:"")
        quit.target = self; quit.representedObject = "QUIT"; menu.addItem(quit)
        return menu
    }
}

if CommandLine.arguments.contains("--self-test") {
    let homeFixture = URL(fileURLWithPath: "/tmp/comi-home-" + UUID().uuidString)
    precondition(ComiHome.root(environment: ["HOME":homeFixture.path, "IVEN_HOME":homeFixture.appendingPathComponent("old").path]).lastPathComponent == "old")
    precondition(ComiHome.root(environment: ["HOME":homeFixture.path, "IVEN_HOME":"/old", "COMI_HOME":"~/new"]).path == homeFixture.appendingPathComponent("new").path)
    precondition(ComiHome.root(environment: ["HOME":homeFixture.path]).path == homeFixture.appendingPathComponent(".comi-pet").path)

    precondition(hostTransitionClip(phase:"working",current:"IMPATIENT",impatient:false) == "WORK")
    precondition(hostTransitionClip(phase:"working",current:"WAITING",impatient:false) == "WORK")
    precondition(hostTransitionClip(phase:"working",current:"THINKING",impatient:false) == nil)
    precondition(hostTransitionClip(phase:"waiting",current:"WAITING",impatient:true) == "IMPATIENT")
    precondition(hostTransitionClip(phase:"waiting",current:"IMPATIENT",impatient:true) == nil)
    let now = 100000.0
    precondition(DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now+30000).isEmbedded(now:now))
    precondition(!DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now).isEmbedded(now:now))
    // 租约上限 90 秒（v2.1.0 起，为后台定时器节流留余量）：60 秒合法、超过上限拒绝
    precondition(DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now+60000).isEmbedded(now:now))
    precondition(DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now+90000).isEmbedded(now:now))
    precondition(!DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now+90001).isEmbedded(now:now))
    precondition(!DisplayLease(version:1,mode:"embedded",owner:"other",lease_until:now+30000).isEmbedded(now:now))
    // 两段式租约：请求（client_id 空）不隐藏，claim 后才隐藏
    precondition(!DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now+30000,client_id:nil).isClaimed)
    precondition(!DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now+30000,client_id:"").isClaimed)
    precondition(DisplayLease(version:1,mode:"embedded",owner:"dsh",lease_until:now+30000,client_id:"web-1").isClaimed)
    // 对话文件协议：请求写入 → 回复往返 → 读取即删 → 情绪白名单
    do {
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("comi-chat-selftest-\(UUID().uuidString)")
        try ChatClient.writeRequest(tmp, text: "在吗", id: "t1")
        let reqObj = try JSONSerialization.jsonObject(with: Data(contentsOf: tmp.appendingPathComponent("request-t1.json"))) as? [String: Any]
        precondition(reqObj?["text"] as? String == "在吗", "request sanitized")
        let replyPayload: [String: Any] = ["version": 1, "id": "t1", "ok": true, "text": "在的呀", "mood": "happy"]
        try JSONSerialization.data(withJSONObject: replyPayload).write(to: tmp.appendingPathComponent("reply-t1.json"))
        let reply = ChatClient.readReply(tmp, id: "t1")
        precondition(reply?.ok == true && reply?.mood == "happy" && reply?.text == "在的呀", "reply round-trip")
        precondition(ChatClient.readReply(tmp, id: "t1") == nil, "reply consumed on read")
        precondition(ChatClient.moodClips["unicorn"] == nil, "mood whitelist enforced")
        try? FileManager.default.removeItem(at: tmp)
    } catch {
        fputs("chat self-test threw: \(error)\n", stderr)
        exit(1)
    }
    let behavior = BehaviorPolicy()
    let tiny = Clip(frames:["a"],durations:[1000])
    precondition((4...6).contains(behavior.seconds("GREET",clip:tiny)))
    precondition(behavior.seconds("THINKING",clip:tiny) == 1)
    for name in ["YAWN", "STOMP", "CELEBRATE", "SEARCH", "TRICK_OR_TREAT", "GHOST_SHEET", "VAMPIRE_CAPE", "WITCH_SPELL", "BLACK_CAT"] {
        precondition(behavior.seconds(name,clip:tiny) == 1)
    }
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
            .appendingPathComponent("comi-selftest-\(UUID().uuidString)")
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
        bridge.selectedSource = "dsh"
        precondition(bridge.source == "dsh" && bridge.mode == "working", "Explicit source overrides other waiting hosts")
        precondition(bridge.sourceStatus("zcode") == "等你确认" && bridge.sourceStatus("codex") == "未收到事件", "Menu shows actual received state")
        try emit("turn.ended",session:"same",source:"zcode")
        precondition(bridge.poll().isEmpty && bridge.source == "dsh", "Other hosts cannot interrupt selected source")
        bridge.selectedSource = "codex"
        precondition(bridge.mode == nil && bridge.source == nil, "Unconnected selection cannot inherit another host")
        bridge.selectedSource = nil
        try emit("session.ended",session:"same",source:"zcode")
        _ = bridge.poll()
        precondition(bridge.source == "dsh", "Closing one harness does not clear another")
        let leftovers = (try? FileManager.default.contentsOfDirectory(atPath: tmp.path)) ?? ["<unreadable>"]
        precondition(leftovers.isEmpty, "inbox consumed cleanly")
    } catch {
        fputs("bridge self-test threw: \(error)\n", stderr)
        exit(1)
    }
    // 甩抛物理（与 tests/test_throw_physics.py 同语义；Cocoa y 向上）
    do {
        let v = ThrowPhysics.estimateVelocity(samples: [(10.0,0,0),(10.1,500,0),(10.15,550,0)], now: 10.15)
        precondition(v != nil && abs(v!.vx - 1000) < 0.01, "stale samples outside the window are ignored")
        precondition(ThrowPhysics.estimateVelocity(samples: [(10.0,0,0),(10.005,30,0)], now: 10.005) == nil,
                     "span shorter than minSpan has no velocity")
        let fly = ThrowPhysics.step(x: 500, y: 400, vx: 100, vy: 800, dt: 0.05,
                                    minX: 0, maxX: 1800, maxY: 1000, floorY: 0, size: 200)
        precondition(fly.event == "fly" && fly.y > 400, "still rising")
        let hit = ThrowPhysics.step(x: 500, y: 2, vx: 0, vy: -1500, dt: 0.05,
                                    minX: 0, maxX: 1800, maxY: 1000, floorY: 0, size: 200)
        precondition(hit.event == "bounce" && hit.y == 0 && hit.vy > 0 && hit.vy < 1560,
                     "floor bounce reflects upward with energy loss")
        let soft = ThrowPhysics.step(x: 500, y: 0, vx: 50, vy: -100, dt: 0.05,
                                     minX: 0, maxX: 1800, maxY: 1000, floorY: 0, size: 200)
        precondition(soft.event == "land" && soft.vx == 0 && soft.vy == 0, "soft contact settles in place")
        let wall = ThrowPhysics.step(x: 1790, y: 500, vx: 3000, vy: 0, dt: 0.05,
                                     minX: 0, maxX: 1800, maxY: 1000, floorY: 0, size: 200)
        precondition(wall.x == 1800 && wall.vx < 0, "right edge reflects the throw")
        let ceiling = ThrowPhysics.step(x: 500, y: 799, vx: 0, vy: 2000, dt: 0.05,
                                        minX: 0, maxX: 1800, maxY: 1000, floorY: 0, size: 200)
        precondition(ceiling.y + 200 == 1000 && ceiling.vy < 0, "top edge bounces downward")
    }
    // 系统通知门控 + 配置解析（不触真实通知与真实配置文件）
    precondition(SystemNotify.gate("permission.required", petHidden: true, mode: "auto"))
    precondition(!SystemNotify.gate("permission.required", petHidden: false, mode: "auto"))
    precondition(!SystemNotify.gate("turn.ended", petHidden: true, mode: "always"))
    precondition(!SystemNotify.gate("task.completed", petHidden: true, mode: "off"))
    precondition(PetConfig.notifyMode(["notifications":"always"]) == "always")
    precondition(PetConfig.notifyMode(["notifications":"yolo"]) == "auto")
    precondition(PetConfig.notifyMode([:]) == "auto")
    precondition(PetConfig.position(["position":["x":10.0,"y":20.0,"cs":"cocoa"]]) != nil)
    precondition(PetConfig.position(["position":["x":10.0,"y":20.0,"cs":"topleft"]]) == nil)
    precondition(PetConfig.position([:]) == nil)
    // 更新检查：版本解析/比较与跳转 tag 提取（与 tests/test_update_check.py 同语义）
    precondition(UpdateCheck.parseVersion("v1.0.1") == [1,0,1])
    precondition(UpdateCheck.isNewer(UpdateCheck.parseVersion("1.0.10")!, UpdateCheck.parseVersion("1.0.9")!))
    precondition(UpdateCheck.isNewer([1,0,2], [1,0,1]))
    precondition(!UpdateCheck.isNewer([1,0,1], [1,0,1]))
    precondition(!UpdateCheck.isNewer([1,0], [1,0,0]))
    precondition(UpdateCheck.isNewer([1,1], [1,0,9]))
    precondition(UpdateCheck.parseVersion("bad") == nil && UpdateCheck.parseVersion("") == nil)
    precondition(UpdateCheck.tag(from: URL(string:"https://github.com/IvenKooLab/desktop-pet/releases/tag/v1.0.1")!) == "1.0.1")
    precondition(UpdateCheck.tag(from: URL(string:"https://github.com/IvenKooLab/desktop-pet/releases")!) == nil)
    precondition(PetConfig.updateCheckEnabled([:]))
    precondition(PetConfig.updateCheckEnabled(["update_check":"auto"]))
    precondition(!PetConfig.updateCheckEnabled(["update_check":"off"]))
    print("PASS: upward/downward screen-coordinate drag, timed frame boundaries/wrap, host-bridge reduction")
    exit(0)
}

let lockPath = NSTemporaryDirectory()+"comi-desktop-pet-\(getuid()).lock"
let lockFD = open(lockPath,O_CREAT|O_RDWR,0o600)
if lockFD < 0 || flock(lockFD,LOCK_EX|LOCK_NB) != 0 {
    print("Comi Pet independent app is already running.")
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
    fputs("Comi Pet: \(error.localizedDescription)\n",stderr)
    exit(1)
}
