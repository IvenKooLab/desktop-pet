/* DSH browser module: deliberately a side-effect script, not an ESM bundle.
 * It uses the host's React and the official shell.overlay slot. */
window.__ModuleLoader__.load({
  id: 'comi-bridge',
  factory(require) {
    const React = require('react')
    const { createElement: h, useEffect, useRef, useState } = React
    const PREFIX = '/comi-pet'
    const SPEED = 0.75
    const navigatorZh = (navigator.language || '').toLowerCase().startsWith('zh')
    const LABEL_PAIRS = {
      IDLE: ['眨眼休息', 'Rest'], GREET: ['挥手', 'Wave'], BOUNCE: ['小跳', 'Bounce'],
      HAPPY: ['开心', 'Happy'], SHY: ['害羞', 'Shy'], CHEER: ['打板', 'Clapperboard'],
      SPIN: ['观察四周', 'Look around'], STRETCH: ['伸懒腰', 'Stretch'],
      DOZE: ['打瞌睡', 'Doze'], RUBIK: ['玩魔方', 'Rubik’s cube'],
      WORK: ['工作', 'Working'], REVIEW: ['检查', 'Reviewing'], WAITING: ['等待', 'Waiting'],
      FAILED: ['失落', 'Sad'], THINKING: ['苦思冥想', 'Deep thinking'], IMPATIENT: ['等待不耐烦', 'Getting impatient'],
      TOKEN_LOW: ['额度不足（表演）', 'Low tokens (performance)'], RELIEVED: ['松口气', 'A sigh of relief'],
      YAWN: ['困倦眨眼', 'Sleepy blink'], STOMP: ['委屈表情', 'Feeling down'],
      CELEBRATE: ['挥手庆祝', 'Celebrate'], SEARCH: ['左右观察', 'Search around'],
      SLEEP: ['睡觉', 'Sleep'], WAKE: ['唤醒', 'Wake up'],
      MOVE_DESKTOP: ['移到独立桌面 ↗', 'Move to desktop ↗'],
      DISPLAY_MODE: ['显示模式', 'Display mode'], DESKTOP: ['独立桌面', 'Desktop'],
      EMBEDDED: ['DSH 界面内', 'Inside DSH'], AUTOPLAY: ['自动轮播动作', 'Automatic animations'],
      ACTIONS: ['动作', 'Actions'], COMPANION: ['陪伴', 'Companion'],
      EVERYDAY: ['日常互动', 'Everyday'], WORK_THEMES: ['工作状态', 'Work themes'],
      LITTLE_BREAKS: ['生活小动作', 'Little breaks'],
      LANGUAGE: ['语言 / Language', 'Language / 语言'], FOLLOW_SYSTEM: ['跟随系统', 'System default'],
      ZH: ['简体中文', '简体中文'], EN: ['English', 'English'],
      ABOUT: ['关于与更新', 'About & updates'], CURRENT_VERSION: ['当前版本', 'Version'],
      GITHUB: ['打开 GitHub 仓库', 'Open GitHub repository'],
    }
    // 菜单分组与桌面端（pet.py / ComiPet.swift）保持同一套分类
    const menuGroups = [
      { key: 'EVERYDAY', items: ['CHEER', 'SPIN', 'BOUNCE', 'HAPPY', 'GREET', 'SHY'] },
      { key: 'WORK_THEMES', items: ['THINKING', 'WORK', 'REVIEW', 'WAITING', 'IMPATIENT', 'TOKEN_LOW', 'RELIEVED', 'FAILED'] },
      { key: 'LITTLE_BREAKS', items: ['STRETCH', 'DOZE', 'RUBIK', 'YAWN', 'STOMP', 'CELEBRATE', 'SEARCH'] },
    ]
    const clientId = (() => {
      try {
        let value = sessionStorage.getItem('comi-pet-client')
        if (!value) { value = `web_${crypto.randomUUID().replaceAll('-', '')}`; sessionStorage.setItem('comi-pet-client', value) }
        return value
      } catch { return `web_${Date.now()}_${Math.random().toString(36).slice(2)}` }
    })()
    const button = { border: '1px solid #ddd5ea', background: '#fff', color: '#514261', borderRadius: 10,
      padding: '7px 11px', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', boxShadow: '0 2px 10px #21132a12' }
    // 甩抛物理：与 throw_physics.py / ComiPet.swift 同一套常量与语义（屏幕坐标 y 向下）
    const PHYS = { G: 1200, RESTITUTION: 0.55, FRICTION: 0.72, LAND_SPEED: 260, THROW_MIN: 280,
      MAX_BOUNCES: 4, WINDOW_MS: 120, MIN_SPAN_MS: 20, MAX_SPEED: 2600 }
    function estimateVelocity(samples, now, windowMs = PHYS.WINDOW_MS, minSpanMs = PHYS.MIN_SPAN_MS, maxSpeed = PHYS.MAX_SPEED) {
      const usable = (samples || []).filter(s => now - s.t <= windowMs).sort((a, b) => a.t - b.t)
      if (usable.length < 2) return null
      const first = usable[0], last = usable[usable.length - 1]
      const dt = last.t - first.t
      if (dt < minSpanMs) return null
      let vx = (last.x - first.x) / dt * 1000, vy = (last.y - first.y) / dt * 1000
      const speed = Math.hypot(vx, vy)
      if (speed < 1e-6) return null
      if (speed > maxSpeed) { const scale = maxSpeed / speed; vx *= scale; vy *= scale }
      return { vx, vy }
    }
    function stepPhysics(x, y, vx, vy, dt, minX, maxX, minY, floorY, size = 200) {
      if (!(dt > 0) || !Number.isFinite(x + y + vx + vy)) return { x, y, vx, vy, event: 'fly' }
      vy += PHYS.G * dt
      x += vx * dt
      y += vy * dt
      let event = 'fly'
      if (x < minX) { x = minX; vx = -vx * PHYS.RESTITUTION }
      else if (x > maxX) { x = maxX; vx = -vx * PHYS.RESTITUTION }
      if (y < minY) { y = minY; vy = -vy * PHYS.RESTITUTION }
      if (y + size >= floorY) {
        if (Math.abs(vy) > PHYS.LAND_SPEED || Math.abs(vx) > PHYS.LAND_SPEED) {
          y = floorY - size
          vy = -vy * PHYS.RESTITUTION
          vx = vx * PHYS.FRICTION
          event = 'bounce'
        } else {
          y = floorY - size
          vx = 0; vy = 0
          event = 'land'
        }
      }
      return { x, y, vx, vy, event }
    }
    const request = async (path, body) => {
      const response = await fetch(`${PREFIX}/api/${path}`, body === undefined
        ? { credentials: 'same-origin', cache: 'no-store' }
        : { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
      const data = await response.json()
      if (!response.ok) { const error = new Error(data.error || `HTTP ${response.status}`); error.data = data; throw error }
      return data
    }
    function Overlay() {
      const [display, setDisplay] = useState({ mode: 'desktop' })
      const [host, setHost] = useState({ phase: 'idle', label: '', tool: '' })
      const [manifest, setManifest] = useState(null)
      const [error, setError] = useState('')
      const [now, setNow] = useState(Date.now())
      const [menu, setMenu] = useState(false)
      const [lang, setLang] = useState('system')
      const [version, setVersion] = useState(null)
      const [autoplay, setAutoplay] = useState(true)
      const image = useRef(null), card = useRef(null), stateRef = useRef(host), manifestRef = useRef(null)
      const behavior = useRef({ actions: {} }), leaseRef = useRef(display), drag = useRef(null)
      const position = useRef({ x: Math.max(0, innerWidth - 235), y: Math.max(100, innerHeight - 235) })
      const action = useRef(null)
      const flying = useRef(null)
      const autoplayRef = useRef(true)
      autoplayRef.current = autoplay
      stateRef.current = host
      leaseRef.current = display
      const embedded = display.mode === 'embedded' && display.client_id === clientId && display.lease_until > now
      const langZh = lang === 'zh' || (lang === 'system' && navigatorZh)
      const text = (cn, en) => langZh ? cn : en
      const label = name => {
        const pair = LABEL_PAIRS[name]
        return pair ? (langZh ? pair[0] : pair[1]) : name
      }
      const selectMode = async mode => {
        if (mode === 'embedded' && !manifestRef.current) return
        try { const data = await request('display', { mode, client_id: clientId }); setDisplay(data.display); setError(''); setMenu(false) }
        catch { setError(text('模式切换失败，请检查 DSH 连接', 'Could not switch modes. Check DSH.')) }
      }
      useEffect(() => {
        let disposed = false
        Promise.all([request('manifest'), request('behaviors')]).then(([data, rules]) => {
          if (!disposed) { manifestRef.current = data; behavior.current = rules; setManifest(data) }
        }).catch(() => { if (!disposed) setError(text('未能读取 Comi 动画素材', 'Could not load Comi’s animations')) })
        const poll = async () => {
          try {
            const data = await request('state')
            if (disposed) return
            setHost(data.state)
            setDisplay(data.display)
            if (data.language) setLang(data.language)
            if (data.version) setVersion(data.version)
            setError('')
            // A native-menu request has no client id. The first visible DSH tab
            // claims it atomically; other tabs cannot prolong that lease.
            if (!document.hidden && manifestRef.current && data.display.mode === 'embedded' && !data.display.client_id) {
              try { const claimed = await request('heartbeat', { client_id: clientId }); if (!disposed) setDisplay(claimed.display) }
              catch { /* another DSH tab won the claim */ }
            }
          } catch { if (!disposed) setError(text('DSH 连接已断开；桌面模式将在 30 秒内恢复', 'DSH disconnected; desktop mode returns within 30 seconds')) }
        }
        poll()
        const pollTimer = setInterval(poll, 1500)
        const expiryTimer = setInterval(() => setNow(Date.now()), 1000)
        const leaseTimer = setInterval(async () => {
          const current = leaseRef.current
          if (document.hidden || current.mode !== 'embedded' || current.client_id !== clientId) return
          try { const data = await request('heartbeat', { client_id: clientId }); if (!disposed) setDisplay(data.display) }
          catch (failure) { if (!disposed && failure.data?.display) setDisplay(failure.data.display) }
        }, 5000)
        const visibility = () => { if (!document.hidden) poll() }
        document.addEventListener('visibilitychange', visibility)
        return () => { disposed = true; clearInterval(pollTimer); clearInterval(leaseTimer); clearInterval(expiryTimer); document.removeEventListener('visibilitychange', visibility) }
      }, [])
      useEffect(() => {
        if (!embedded || !manifest) return
        // 桌面端（pet.py / ComiPet.swift）在运行时合成 FALL/LAND；manifest 只存
        // 素材剪辑。Web 端同样补齐，甩抛物理与落地动画才能工作。
        const clips = { ...manifest.clips }
        if (!clips.FALL) clips.FALL = { frames: ['fall_0'], durations: [1000] }
        if (!clips.LAND) clips.LAND = { frames: ['land_0'], durations: [350] }
        let raf, previous = performance.now(), clip = 'IDLE', elapsed = 0, repeats = 1, shown = '', lastAction = ''
        let previousPhase = 'idle', previousHostKey = '', terminalPlayed = false, direction = Math.random() > .5 ? 1 : -1
        let previousSelected = null
        let squashTimer = 0
        const randomInt = (range, fallback) => {
          const pair = Array.isArray(range) && range.length === 2 ? range : fallback
          return Math.floor(pair[0] + Math.random() * (pair[1] - pair[0] + 1))
        }
        const choose = name => {
          clip = clips[name] ? name : 'IDLE'; elapsed = 0
          const configured = behavior.current.actions?.[clip]?.cycles
          if (['THINKING', 'IMPATIENT', 'TOKEN_LOW', 'RELIEVED', 'LAND', 'FALL'].includes(clip)
            || (stateRef.current.phase === 'working' && clip === 'WORK')) repeats = 1
          else if (clip === 'IDLE') repeats = Math.max(1, Math.round(randomInt(behavior.current.idle_seconds, [3, 5]) * 1000 * SPEED / clips.IDLE.durations.reduce((a, b) => a + b, 0)))
          else if (clip.startsWith('WALK')) repeats = randomInt(behavior.current.walk_cycles, [5, 8])
          else repeats = randomInt(configured, ['GREET', 'BOUNCE', 'HAPPY', 'CHEER'].includes(clip) ? [3, 5] : [2, 3])
        }
        const squash = () => {
          const img = image.current
          if (!img) return
          img.style.transform = 'scale(1.16, 0.82)'
          clearTimeout(squashTimer)
          squashTimer = setTimeout(() => { if (image.current) image.current.style.transform = '' }, 180)
        }
        const next = () => {
          const phase = stateRef.current.phase
          if (phase === 'working') return choose(clip === 'WORK' ? 'THINKING' : 'WORK')
          if (phase === 'waiting') return choose(Date.now() - (stateRef.current.phase_since || Date.now()) >= 30_000 ? 'IMPATIENT' : 'WAITING')
          if (phase === 'success') {
            if (terminalPlayed) return choose('IDLE')
            terminalPlayed = true
            return choose('RELIEVED')
          }
          if (phase === 'failed') return choose('FAILED')
          // TOKEN_LOW is a manual performance, never an inferred account state.
          const playable = name => name !== 'IDLE' && name !== 'TOKEN_LOW' && name !== 'SLEEP' && name !== 'WAKE'
            && !['MOVE_DESKTOP', 'DISPLAY_MODE', 'DESKTOP', 'EMBEDDED', 'AUTOPLAY', 'ACTIONS', 'COMPANION',
                 'EVERYDAY', 'WORK_THEMES', 'LITTLE_BREAKS', 'LANGUAGE', 'FOLLOW_SYSTEM', 'ZH', 'EN',
                 'ABOUT', 'CURRENT_VERSION', 'GITHUB'].includes(name) && clips[name]
          const choices = ['IDLE', 'IDLE', 'IDLE', 'WALK', ...Object.keys(LABEL_PAIRS).filter(name => playable(name) && name !== lastAction)]
          let name = choices[Math.floor(Math.random() * choices.length)]
          if (name === 'WALK') { direction = Math.random() > .5 ? 1 : -1; name = direction > 0 ? 'WALK_r' : 'WALK_l' }
          lastAction = name
          choose(name)
        }
        choose('IDLE')
        const frame = now => {
          const dt = Math.min(100, now - previous); previous = now
          const phase = stateRef.current.phase
          const hostKey = `${stateRef.current.session_id || ''}:${phase}:${stateRef.current.phase_since || ''}`
          if (hostKey !== previousHostKey) {
            previousHostKey = hostKey
            const finishingRelief = phase === 'idle' && previousPhase === 'success' && clip === 'RELIEVED'
            previousPhase = phase
            terminalPlayed = false
            // A 7-second result bubble may expire before this 9-second theme;
            // let its current timeline finish unless another task interrupts.
            if (!finishingRelief) next()
          }
          if (phase === 'waiting' && clip === 'WAITING' && Date.now() - (stateRef.current.phase_since || Date.now()) >= 30_000) choose('IMPATIENT')
          if (action.current) { choose(action.current); action.current = null }
          if (drag.current) {
            if (flying.current) flying.current = null        // 抓住即停飞
            if (clip !== 'GRAB') choose('GRAB')
          } else if (clip === 'GRAB') choose('IDLE')
          elapsed += dt * SPEED
          let selected = clips[clip] || clips.IDLE
          let duration = selected.durations.reduce((a, b) => a + b, 0)
          // 飞行中不做自动轮播：保持 FALL 直到落地
          if (!flying.current && autoplayRef.current && elapsed >= duration * repeats) { next(); selected = clips[clip] || clips.IDLE; duration = selected.durations.reduce((a, b) => a + b, 0) }
          let phaseTime = elapsed % duration, index = 0
          while (index < selected.frames.length - 1 && phaseTime >= selected.durations[index]) { phaseTime -= selected.durations[index]; index++ }
          if (!drag.current && clip.startsWith('WALK')) {
            const pos = position.current
            pos.x += direction * 28 * dt / 1000 * SPEED
            if (pos.x <= 0 || pos.x >= innerWidth - 200) { direction *= -1; choose(direction > 0 ? 'WALK_r' : 'WALK_l') }
          }
          // 甩抛物理：拖拽松手后的抛物线飞行、视口边缘反弹、落地弹跳（Q 弹）。
          // 必须在选帧之前跑：松手第一帧就要显示 FALL，而不是下一帧。
          if (flying.current) {
            if (clip !== 'FALL') choose('FALL')
            const pos = position.current
            const outcome = stepPhysics(pos.x, pos.y, flying.current.vx, flying.current.vy,
              dt / 1000 * SPEED, 0, Math.max(0, innerWidth - 200), 120, innerHeight)
            pos.x = outcome.x; pos.y = outcome.y
            flying.current.vx = outcome.vx; flying.current.vy = outcome.vy
            if (outcome.event === 'bounce') {
              flying.current.bounces++
              squash()
            } else if (outcome.event === 'land' || flying.current.bounces > PHYS.MAX_BOUNCES) {
              flying.current = null
              choose('LAND')
            }
          }
          // 渲染帧：一切状态（含物理改写的 clip）就绪后再上屏
          selected = clips[clip] || clips.IDLE
          if (selected !== previousSelected) { previousSelected = selected; index = 0; phaseTime = 0 }
          const source = `${PREFIX}/frames/${selected.frames[index]}.png`
          if (source !== shown && image.current) { image.current.src = source; shown = source }
          if (image.current) image.current.dataset.animation = clip
          const pos = position.current
          pos.x = Math.max(0, Math.min(Math.max(0, innerWidth - 200), pos.x))
          pos.y = Math.max(Math.min(120, Math.max(0, innerHeight - 200)), Math.min(Math.max(0, innerHeight - 200), pos.y))
          if (card.current) { card.current.style.left = `${pos.x}px`; card.current.style.top = `${pos.y}px` }
          raf = requestAnimationFrame(frame)
        }
        raf = requestAnimationFrame(frame)
        return () => { cancelAnimationFrame(raf); clearTimeout(squashTimer) }
      }, [embedded, manifest])
      const phases = { working: text('工作中', 'Working'), waiting: text('等你确认', 'Needs your input'), success: text('任务完成', 'Task complete'), failed: text('遇到问题', 'Needs attention') }
      const status = phases[host.phase]
      const startDrag = event => {
        if (event.button !== 0) return
        drag.current = { x: event.clientX - position.current.x, y: event.clientY - position.current.y, moved: false,
          samples: [{ t: performance.now(), x: event.clientX, y: event.clientY }] }
        event.currentTarget.setPointerCapture(event.pointerId); setMenu(false)
      }
      const moveDrag = event => {
        if (!drag.current) return
        const x = event.clientX - drag.current.x, y = event.clientY - drag.current.y
        if (Math.abs(x - position.current.x) + Math.abs(y - position.current.y) > 3) drag.current.moved = true
        position.current = { x, y }
        drag.current.samples.push({ t: performance.now(), x: event.clientX, y: event.clientY })
        if (drag.current.samples.length > 6) drag.current.samples.shift()
      }
      const endDrag = event => {
        if (!drag.current) return
        const moved = drag.current.moved, samples = drag.current.samples
        drag.current = null
        if (event.currentTarget?.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
        if (!moved) { action.current = 'BOUNCE'; return }
        // 甩得动就抛出去（与桌面端同一套阈值），温柔放下则原地停住
        const velocity = estimateVelocity(samples, performance.now())
        if (velocity && Math.hypot(velocity.vx, velocity.vy) >= PHYS.THROW_MIN) {
          flying.current = { vx: velocity.vx, vy: velocity.vy, bounces: 0 }
        }
      }
      const renderItem = (entry, depth) => {
      if (entry.sep) return h('div', { key: entry.key, className: 'comi-menu-sep' })
      const item = h('button', { key: entry.key,
        className: 'comi-menu-item' + (entry.hasSub ? ' comi-item-has' : ''),
        style: entry.disabled ? { opacity: .45, cursor: 'default' } : null,
        onClick: entry.disabled ? undefined : entry.onClick },
      h('span', { className: 'comi-check' }, entry.check ? '✓' : ''),
      entry.label, entry.hasSub ? h('span', { className: 'comi-arrow' }, '▸') : null,
      entry.sub ? h('div', { className: 'comi-sub' },
        ...entry.sub.map(child => renderItem(child, depth + 1))) : null)
      return item
    }
    return h('div', { style: { position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1000, fontFamily: 'system-ui, sans-serif' } },
        h('style', null, `
.comi-menu-item{display:block;width:100%;text-align:left;padding:3px 14px;border:none;background:transparent;color:#1d1d1f;font-size:13px;line-height:20px;border-radius:0;cursor:default;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}
.comi-menu-item:hover{background:#2f6bd8;color:#fff}
.comi-menu-section{padding:5px 14px 2px;font-size:11px;line-height:14px;color:#8a8a8e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}
.comi-menu-sep{height:1px;margin:5px 12px;background:#e3e3e3;border:none}
.comi-item-has{position:relative}
.comi-sub{display:none;position:absolute;right:100%;top:-5px;margin-right:2px;padding:5px 0;width:200px;background:#fff;border:1px solid #d9d9de;border-radius:12px;box-shadow:0 10px 34px #0000002e}
.comi-item-has:hover>.comi-sub{display:block}
.comi-arrow{float:right;opacity:.45;font-size:11px;line-height:20px}
.comi-check{display:inline-block;width:16px}
.comi-pet-img{transform-origin:50% 96%;transition:transform .16s cubic-bezier(.2,.7,.4,1.4)}
`),
        h('button', { type: 'button', disabled: !manifest, style: { ...button, position: 'absolute', right: 16, top: 76, pointerEvents: 'auto', opacity: manifest ? 1 : .6 },
          title: error || text('切换 Comi 显示位置', 'Switch Comi’s display mode'),
          onClick: () => selectMode(embedded ? 'desktop' : 'embedded') },
        error ? text('Comi · 连接中断', 'Comi · disconnected') : embedded ? text('Comi · 切到桌面 ↗', 'Comi · move to desktop ↗') : text('Comi · 移入界面 ↙', 'Comi · bring into DSH ↙')),
        embedded && manifest ? h('div', { ref: card, style: { position: 'absolute', width: 200, height: 200, left: position.current.x, top: position.current.y, pointerEvents: 'auto' } },
          status ? h('div', { style: { position: 'absolute', bottom: 160, left: -35, width: 270, boxSizing: 'border-box', background: '#fffffff5', color: '#302638',
            padding: '11px 14px', border: '1px solid #ddd4e7', borderRadius: 16, boxShadow: '0 4px 20px #25122a24', fontSize: 12, pointerEvents: 'none', overflowWrap: 'anywhere' } },
          h('strong', { style: { display: 'block', color: '#7954a2', marginBottom: host.label || host.tool ? 5 : 0 } }, `DSH · ${status}`),
          host.label ? h('div', null, host.label) : null,
          host.tool ? h('div', { style: { marginTop: 3, opacity: .8 } }, `${text('当前工具', 'Tool')} · ${host.tool}`) : null) : null,
          h('img', { ref: image, className: 'comi-pet-img', src: `${PREFIX}/frames/idle_0.png`, draggable: false, alt: 'Comi',
            style: { display: 'block', width: 200, height: 200, userSelect: 'none', touchAction: 'none', cursor: 'grab' },
            onPointerDown: startDrag, onPointerMove: moveDrag, onPointerUp: endDrag, onPointerCancel: endDrag,
            onError: event => {
              // 任何帧加载失败都回落待机帧，绝不显示裂图
              const img = event.currentTarget
              if (!img.src.endsWith('idle_0.png')) img.src = `${PREFIX}/frames/idle_0.png`
            },
            onContextMenu: event => { event.preventDefault(); setMenu(value => !value) } }),
          menu ? h('div', { style: { position: 'absolute', bottom: 180, right: 0, width: 200, padding: '5px 0',
            background: '#fff', border: '1px solid #d9d9de', borderRadius: 12, boxShadow: '0 10px 34px #0000002e' } },
          h('button', { className: 'comi-menu-item', onClick: () => selectMode('desktop') }, label('MOVE_DESKTOP')),
          ...[
            // 层级与桌面端一致：动作 ▸（日常互动/工作状态/生活小动作 + 睡觉/唤醒）
            { key: 'ACTIONS', hasSub: true, label: label('ACTIONS'), sub: [
                ...menuGroups.map(group => ({
                  key: group.key, hasSub: true, label: label(group.key),
                  sub: group.items.filter(name => manifest?.clips[name]).map(name => ({
                    key: name, label: label(name), onClick: () => { action.current = name; setMenu(false) } })),
                })),
                { key: 'sep-sleep', sep: true },
                { key: 'SLEEP', label: label('SLEEP'), onClick: () => { action.current = 'SLEEP'; setMenu(false) } },
                { key: 'WAKE', label: label('WAKE'), onClick: () => { action.current = 'IDLE'; setMenu(false) } },
            ] },
            // 陪伴 ▸（显示模式 / 自动轮播；宿主桥接与系统通知为桌面端专属）
            { key: 'COMPANION', hasSub: true, label: label('COMPANION'), sub: [
                { key: 'DISPLAY_MODE', hasSub: true, label: label('DISPLAY_MODE'), sub: [
                    { key: 'desktop', label: label('DESKTOP'), check: display.mode === 'desktop', onClick: () => selectMode('desktop') },
                    { key: 'embedded', label: label('EMBEDDED'), check: display.mode === 'embedded', onClick: () => selectMode('embedded') },
                ] },
                { key: 'AUTOPLAY', label: label('AUTOPLAY'), check: autoplay, onClick: () => setAutoplay(value => !value) },
            ] },
            // 语言 ▸（与桌面端共用同一份语言偏好文件）
            { key: 'LANGUAGE', hasSub: true, label: label('LANGUAGE'), sub: [
                { key: 'system', label: label('FOLLOW_SYSTEM'), check: lang === 'system',
                  onClick: () => request('language', { value: 'system' }).then(d => setLang(d.language)).catch(() => {}) },
                { key: 'zh', label: label('ZH'), check: lang === 'zh',
                  onClick: () => request('language', { value: 'zh' }).then(d => setLang(d.language)).catch(() => {}) },
                { key: 'en', label: label('EN'), check: lang === 'en',
                  onClick: () => request('language', { value: 'en' }).then(d => setLang(d.language)).catch(() => {}) },
            ] },
            // 关于与更新 ▸
            { key: 'ABOUT', hasSub: true, label: label('ABOUT'), sub: [
                { key: 'ver', label: `${label('CURRENT_VERSION')} v${version || '?.?.?'}`, disabled: true },
                { key: 'GITHUB', label: label('GITHUB'), onClick: () => window.open('https://github.com/IvenKooLab/desktop-pet', '_blank') },
            ] },
          ].map(entry => renderItem(entry, 1))) : null) : null)
    }
    return {
      name: 'comi-pet', inject: ['slots'],
      __physics: { estimateVelocity, stepPhysics, PHYS },
      apply(ctx) {
        ctx.slots.inject('shell.overlay', function* () {
          yield ctx.slots.register({ name: 'shell.overlay', id: 'comi-pet', order: 1000 }, () => h(Overlay))
        })
      },
    }
  },
})
