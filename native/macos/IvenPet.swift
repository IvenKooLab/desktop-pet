import AppKit
import QuartzCore
import Darwin

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
        let candidates = ["GREET", "BOUNCE", "CHEER", "SPIN", "WAITING", "WORK", "REVIEW", "FAILED"]
            .filter { available.contains($0) } + (pinned ? [] : ["WALK_r", "WALK_l"].filter { available.contains($0) })
        remaining = remaining.filter { candidates.contains($0) }
        if remaining.isEmpty { remaining = candidates.shuffled() }
        if remaining.count > 1 && remaining.last == last { remaining.swapAt(0, remaining.count-1) }
        last = remaining.popLast() ?? "IDLE"
        return last
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

    private func advance() {
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
        print("[start] native AppKit | transparent CALayer | \(images.count) PNG frames | drag uses Cocoa screen coordinates")
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
        deadline = seconds > 0 ? clipStart + seconds : 0
        shown = ""
        view?.show(images[clip.frames[0]]!)
    }
    @objc private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        let dt = min(0.05,max(0,now-previous))
        previous = now
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
        let frame = clips[clipName]!.frame(at:Int((now-clipStart)*1000))
        if frame != shown {
            shown = frame
            view.show(images[frame]!)
        }
    }
    func perform(_ action: String) {
        pressed = false
        if action == "QUIT" { NSApp.terminate(nil); return }
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
            play(direction > 0 ? "RUN_r" : "RUN_l",mode:"WALK",seconds:6)
        } else if action == "SLEEP" { play("SLEEP",mode:"SLEEP",seconds:0) }
        else if action == "IDLE" { play("IDLE",mode:"IDLE",seconds:6) }
        else if let clip = clips[action] {
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
        for (title,action) in [("等待","WAITING"),("工作","WORK"),("检查","REVIEW"),("失落","FAILED"),("挥手打招呼","GREET"),("弹跳","BOUNCE"),("开心","HAPPY"),
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
    print("PASS: upward/downward screen-coordinate drag and timed frame boundaries/wrap")
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
